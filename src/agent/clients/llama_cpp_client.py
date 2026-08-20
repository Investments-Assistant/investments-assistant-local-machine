"""llama-cpp-python backend — loads GGUF models directly into process memory.

No server, no HTTP calls. The model file lives on disk; this client maps it
into RAM and runs inference in a thread pool so the async event loop stays free.

Recommended for Raspberry Pi 5 (ARM64, CPU-only):
  - GGUF is a quantised format designed for CPU inference
  - llama-cpp-python uses hand-optimised GGML/BLAS kernels (ARM NEON on Pi 5)
  - The Q4_K_M 7B model is currently two shards totaling ~4.7 GB, leaving room
    for the rest of the stack

Install
-------
    pip install llama-cpp-python
    # ARM64 / Pi 5 pre-built wheel:
    pip install llama-cpp-python \\
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

Download a model
----------------
    python3 scripts/download_model.py          # interactive picker
    python3 scripts/download_model.py qwen2.5-7b

Tested models on Pi 5 (8 GB RAM)
---------------------------------
    qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf + shard  ~4.7 GB  best quality/speed
    llama-3.2-3b-instruct-q8_0.gguf   ~3.4 GB  faster, lighter
    mistral-7b-instruct-q4_k_m.gguf   ~4.4 GB  solid all-rounder
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
import json
import queue
import re
from typing import Any

from src.agent.clients.base import BaseLLMClient
from src.agent.utils.logger import get_logger
from src.config import settings
from src.tools import dispatch_tool
from src.tools.definitions import TOOL_DEFINITIONS, to_openai_tools

logger = get_logger(__name__)

_TOOLS = to_openai_tools(TOOL_DEFINITIONS)
_TOOLS_BY_NAME = {tool["function"]["name"]: tool for tool in _TOOLS}

# Sending every schema on every turn makes the 7B model spend most of its
# context and CPU budget describing tools the user did not ask about. Keep a
# small market-oriented default and add focused groups from the latest request.
_CORE_TOOL_NAMES = (
    "get_market_overview",
    "get_stock_data",
    "get_crypto_data",
    "get_technical_indicators",
    "search_market_news",
)
_TOOL_GROUPS = (
    (
        ("full market", "market overview", "market snapshot", "overall market"),
        (
            "get_forex_rates",
            "get_central_bank_rates",
            "get_latest_news",
            "get_earnings_calendar",
        ),
    ),
    (
        ("portfolio", "holdings", "position", "rebalance", "broker account", "cash", "p&l"),
        ("get_portfolio_summary", "get_account_info", "get_trade_history"),
    ),
    (
        ("trade", "buy", "sell", "order", "execute", "cancel", "confirm", "trading mode"),
        ("execute_trade", "cancel_order", "confirm_trade", "set_trading_mode"),
    ),
    (
        ("simulation", "simulate", "backtest", "back-test"),
        ("run_simulation",),
    ),
    (("report", "weekly report"), ("generate_report",)),
    (("option", "options", "call", "put", "strike"), ("get_options_chain",)),
    (
        ("forex", "fx", "currency", "eur/usd", "gbp/usd", "usd/jpy", "central bank", "pip"),
        ("get_forex_data", "get_forex_rates", "get_central_bank_rates"),
    ),
    (
        ("news", "headline", "sentiment", "fed", "earnings", "reuters"),
        ("search_market_news", "search_stored_news", "get_latest_news", "get_earnings_calendar"),
    ),
    (("nft", "non-fungible"), ("assess_nft_risk",)),
    (("ticker", "company name", "find symbol"), ("search_ticker",)),
)

_PREFETCH_MARKET_KEYWORDS = (
    "market",
    "overview",
    "snapshot",
    "indices",
    "s&p",
    "nasdaq",
    "dow jones",
    "vix",
    "treasury",
    "gold",
    "crude oil",
)
_PREFETCH_NEWS_KEYWORDS = (
    "news",
    "headline",
    "sentiment",
    "federal reserve",
    "fed ",
    "reuters",
)
_INTERMEDIATE_RESPONSE_RE = re.compile(
    r"^(?:i(?:'|’)m going to|i am going to|i(?:'|’)ll|i will|"
    r"i(?:'|’)m analyzing|i am analyzing|let me|allow me to|"
    r"please wait|one moment|hold on)\b",
    re.IGNORECASE,
)
_FINAL_ANSWER_REPAIR_PROMPT = (
    "Return the completed final answer to the original user request now. The previous "
    "assistant text was only an internal progress update, not an answer. Do not mention "
    "waiting, analysis-in-progress, tools, prompts, or this instruction. Use the factual "
    "context already provided. If the evidence is insufficient, state that limitation "
    "clearly and give the best supported answer. Start directly with the answer."
)


def _tools_for_messages(messages: list[dict[str, Any]]) -> list[dict]:
    """Select a compact, intent-matched tool catalog for the current turn."""
    latest = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            latest = str(message.get("content", "")).lower()
            break

    names = set(_CORE_TOOL_NAMES)
    for keywords, group_names in _TOOL_GROUPS:
        if any(keyword in latest for keyword in keywords):
            names.update(group_names)
    return [tool for tool in _TOOLS if tool["function"]["name"] in names]


def _prefetch_request(messages: list[dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    """Return a deterministic live-data request for common market questions."""
    latest = _latest_user_message(messages)
    lowered = latest.lower()
    if any(keyword in lowered for keyword in _PREFETCH_NEWS_KEYWORDS):
        query_match = re.search(
            r"\b(?:news|headlines?)\s+(?:about|on|regarding|for)\s+(.+?)"
            r"(?:\s+(?:and|then)\s+(?:analyse|analyze|summari[sz]e|assess|review).*)?$",
            latest,
            re.IGNORECASE,
        )
        query = query_match.group(1) if query_match else latest
        query = re.sub(
            r"\s+(?:and\s+)?(?:analyse|analyze|summari[sz]e|assess|review)\b.*$",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip(" .?!")
        return "search_market_news", {"query": query[:160] or "Federal Reserve", "max_articles": 10}
    if any(keyword in lowered for keyword in _PREFETCH_MARKET_KEYWORDS):
        return "get_market_overview", {}
    return None


def _looks_like_intermediate_response(text: str | None) -> bool:
    """Identify progress/status text that must never be shown as the answer."""
    normalized = " ".join((text or "").split()).strip()
    if not normalized:
        return True
    return bool(_INTERMEDIATE_RESPONSE_RE.search(normalized)) or "please wait" in normalized.lower()


def _format_news_result(result_str: str) -> str:
    """Provide a factual final answer if the small model cannot synthesize one."""
    try:
        result = json.loads(result_str)
    except json.JSONDecodeError:
        return (
            "I could not complete the news analysis because the news source returned "
            "invalid data."
        )
    if not isinstance(result, dict):
        return (
            "I could not complete the news analysis because the news source returned "
            "an invalid result."
        )
    articles = result.get("articles") if isinstance(result.get("articles"), list) else []
    lines = [
        f"# News analysis: {result.get('query', 'requested topic')}",
        "",
        (
            f"**Overall sentiment:** {result.get('overall_sentiment', 'neutral')} "
            f"(average score {result.get('avg_sentiment_score', 0.0)})"
        ),
        f"**Articles reviewed:** {result.get('articles_found', len(articles))}",
        "",
    ]
    if not articles:
        lines.append("No matching articles were returned by the configured news sources.")
    else:
        lines.append("## Headlines and sentiment")
        for article in articles[:10]:
            if not isinstance(article, dict):
                continue
            sentiment = article.get("sentiment") or {}
            label = sentiment.get("label", "neutral")
            score = sentiment.get("score", 0.0)
            title = str(article.get("title") or "Untitled article")
            source = str(article.get("source") or "Unknown source")
            published = str(article.get("published_at") or "date unavailable")
            lines.append(f"- **{title}** — {source}, {published}; {label} ({score})")
            summary = str(article.get("summary") or "").strip()
            if summary:
                lines.append(f"  {summary}")
    lines.extend(
        [
            "",
            "Sentiment is a keyword-based triage signal from the configured sources, not "
            "a trading signal. Verify the original articles before acting.",
        ]
    )
    return "\n".join(lines)


def _format_market_overview_result(result_str: str) -> str:
    """Format every market snapshot row without relying on model token budget."""
    try:
        result = json.loads(result_str)
    except json.JSONDecodeError:
        return "I could not complete the market overview because the market data was invalid."
    if not isinstance(result, dict):
        return "I could not complete the market overview because the market data was invalid."

    markets = result.get("markets") if isinstance(result.get("markets"), dict) else {}
    lines = [
        "# Market overview",
        "",
        f"**Snapshot time:** {result.get('timestamp', 'unavailable')}",
        "",
        "| Market | Price / yield | Change |",
        "|---|---:|---:|",
    ]
    for name, values in markets.items():
        if not isinstance(values, dict):
            continue
        if values.get("error"):
            lines.append(f"| {name} | unavailable | unavailable |")
            continue
        price = values.get("price")
        change = values.get("change_pct")
        price_text = (
            "unavailable"
            if price is None
            else f"{float(price):,.4f}".rstrip("0").rstrip(".")
        )
        change_text = "unavailable" if change is None else f"{float(change):+.2f}%"
        lines.append(f"| {name} | {price_text} | {change_text} |")
    lines.extend(
        [
            "",
            "Positive changes indicate gains versus the previous close; negative changes "
            "indicate declines. This is a point-in-time snapshot, not investment advice.",
        ]
    )
    return "\n".join(lines)


def _latest_user_message(messages: list[dict[str, Any]]) -> str:
    """Return the latest user message for deterministic local workflows."""
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _report_request(messages: list[dict[str, Any]]) -> dict[str, str] | None:
    """Recognise report requests before the small local model can answer generically."""
    latest = _latest_user_message(messages).lower()
    if not any(word in latest for word in ("report", "investment review", "portfolio review")):
        return None
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", latest)
    if not dates and not any(
        word in latest for word in ("weekly", "week", "7 days", "seven days", "past")
    ):
        return None
    end = datetime.now(UTC).date()
    if len(dates) >= 2:
        return {"period_start": dates[0], "period_end": dates[1]}
    if len(dates) == 1:
        return {"period_start": dates[0], "period_end": end.isoformat()}
    return {
        "period_start": (end - timedelta(days=7)).isoformat(),
        "period_end": end.isoformat(),
    }


def _simulation_request(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Parse the common simulation prompt used by the quick action and chat."""
    latest = _latest_user_message(messages)
    lowered = latest.lower()
    if not any(word in lowered for word in ("simulation", "simulate", "backtest", "back-test")):
        return None

    strategy_type = "buy_and_hold"
    if "sma" in lowered or "moving average" in lowered:
        strategy_type = "sma_crossover"
    elif "rsi" in lowered or "mean reversion" in lowered:
        strategy_type = "rsi_mean_reversion"
    elif "momentum" in lowered:
        strategy_type = "momentum"

    scope_match = re.search(
        r"\b(?:on|for)\s+(.+?)(?:\s+from\s+|\s+between\s+|\s+with\s+|$)",
        latest,
        re.I,
    )
    scope = scope_match.group(1) if scope_match else latest
    symbols = re.findall(r"\b[A-Z][A-Z0-9.-]{0,9}\b", scope.upper())
    ignored = {"RUN", "A", "BUY", "AND", "HOLD", "SIMULATION", "SIMULATE", "BACKTEST"}
    symbols = list(dict.fromkeys(symbol for symbol in symbols if symbol not in ignored))
    if not symbols:
        return None

    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", latest)
    start = dates[0] if dates else (datetime.now(UTC).date() - timedelta(days=365)).isoformat()
    end = dates[1] if len(dates) > 1 else None
    capital_match = re.search(r"(?:\$|capital(?:\s+of)?\s*)([0-9][0-9,]*(?:\.\d+)?)", lowered)
    capital = float(capital_match.group(1).replace(",", "")) if capital_match else 10_000.0
    return {
        "name": f"{strategy_type.replace('_', ' ').title()} — {', '.join(symbols)}",
        "symbols": symbols,
        "strategy": {"type": strategy_type},
        "initial_capital": capital,
        "period_start": start,
        "period_end": end,
    }


def _format_simulation_result(result: dict[str, Any]) -> str:
    """Turn a simulation result into a useful answer without another model turn."""
    if result.get("error"):
        return f"I could not run the simulation: {result['error']}"
    return (
        f"# Simulation complete — {result.get('name', 'Paper simulation')}\n\n"
        f"- **Symbols:** {', '.join(result.get('symbols', []))}\n"
        f"- **Period:** {result.get('period_start')} → {result.get('period_end')}\n"
        f"- **Fake starting capital:** ${result.get('initial_capital', 0):,.2f}\n"
        f"- **Ending value:** ${result.get('final_value', 0):,.2f}\n"
        f"- **Total return:** {result.get('total_return_pct', 0):+.2f}%\n"
        f"- **Sharpe ratio:** {result.get('sharpe_ratio', 'n/a')}\n"
        f"- **Maximum drawdown:** {result.get('max_drawdown_pct', 'n/a')}%\n"
        f"- **Trades:** {result.get('trades_count', 0)}\n\n"
        "This is a historical backtest using fake money. It does not place orders "
        "or predict future returns."
    )


def _compact_local_system_prompt() -> str:
    """Keep CPU-only local prompt evaluation small without dropping guardrails."""
    return (
        "You are Investment Assistant, a concise and careful financial analysis assistant. "
        f"The current trading mode is {settings.trading_mode}. "
        "In recommend mode, never execute a trade; require explicit approval for proposals. "
        "Never invent prices, news, portfolio facts, or tool results. Use only live context "
        "provided in this conversation and clearly label uncertainty. Answer directly, with "
        "brief evidence, risks, and the reminder that this is not financial advice. Never "
        "emit a progress update such as 'I will analyze this' or 'please wait'; output only "
        "the completed answer to the user's request."
    )

# Singleton — the model is large; load it once and share across all sessions.
_instance: LlamaCppClient | None = None


class LlamaCppClient(BaseLLMClient):
    """In-process GGUF inference via llama-cpp-python."""

    def __init__(self) -> None:
        try:
            from llama_cpp import Llama  # noqa: F401 — checked at init time

            self._Llama = Llama
        except ImportError as exc:
            raise ImportError(
                "llama-cpp-python is required for the llama_cpp backend.\n"
                "Install:  pip install llama-cpp-python\n"
                "ARM64/Pi 5:  pip install llama-cpp-python "
                "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu"
            ) from exc

        logger.info(
            "Loading GGUF model: %s  (n_ctx=%d, n_gpu_layers=%d, n_threads=%d, n_batch=%d)",
            settings.llm_model_path,
            settings.llm_context_size,
            settings.llm_n_gpu_layers,
            settings.llm_n_threads,
            settings.llm_n_batch,
        )
        self._llm = self._Llama(
            model_path=settings.llm_model_path,
            n_ctx=settings.llm_context_size,
            n_gpu_layers=settings.llm_n_gpu_layers,
            n_threads=settings.llm_n_threads,
            n_batch=settings.llm_n_batch,
            verbose=False,
        )
        self._inference_lock = asyncio.Lock()
        logger.info("GGUF model loaded")

    async def _stream_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict],
        max_tokens: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Bridge llama-cpp's synchronous iterator into the async event loop."""
        loop = asyncio.get_running_loop()
        chunks: queue.Queue[tuple[str, Any]] = queue.Queue()

        def infer() -> None:
            try:
                request: dict[str, Any] = {
                    "messages": messages,
                    "max_tokens": max_tokens or settings.agent_max_tokens,
                    "temperature": settings.agent_temperature,
                    "stream": True,
                }
                if tools:
                    request["tools"] = tools
                    request["tool_choice"] = "auto"
                response = self._llm.create_chat_completion(**request)
                for chunk in response:
                    chunks.put(("chunk", chunk))
            except BaseException as exc:  # propagate inference failures to the async caller
                chunks.put(("error", exc))
            finally:
                chunks.put(("done", None))

        inference = loop.run_in_executor(None, infer)
        while True:
            kind, item = await asyncio.to_thread(chunks.get)
            if kind == "chunk":
                yield item
            elif kind == "error":
                await inference
                raise item
            else:
                break
        await inference

    async def _ensure_final_answer(
        self,
        candidate: str | None,
        context_messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        fallback: str | None = None,
        truncated: bool = False,
    ) -> str:
        """Return only a completed answer, repairing progress-only model output."""
        candidate_text = (candidate or "").strip()
        if (
            candidate_text
            and not truncated
            and not _looks_like_intermediate_response(candidate_text)
        ):
            return candidate_text

        # Deterministic tool responses are already complete and avoid asking a
        # small local model to repeat a long table after it hit its token cap.
        if truncated and fallback:
            return fallback

        repair_messages = list(context_messages)
        if candidate_text:
            repair_messages.append({"role": "assistant", "content": candidate_text})
        repair_messages.append({"role": "user", "content": _FINAL_ANSWER_REPAIR_PROMPT})
        repaired_parts: list[str] = []
        repair_finish_reason: str | None = None
        try:
            async with self._inference_lock:
                async for response_chunk in self._stream_completion(
                    repair_messages,
                    [],
                    max_tokens=max(max_tokens or settings.agent_max_tokens, 512),
                ):
                    choices = response_chunk.get("choices") or []
                    if not choices:
                        continue
                    if choices[0].get("finish_reason") is not None:
                        repair_finish_reason = choices[0]["finish_reason"]
                    content = (choices[0].get("delta") or {}).get("content")
                    if content:
                        repaired_parts.append(str(content))
        except Exception as exc:
            logger.warning("Final-answer repair failed: %s", exc)

        repaired = "".join(repaired_parts).strip()
        if (
            repaired
            and repair_finish_reason != "length"
            and not _looks_like_intermediate_response(repaired)
        ):
            return repaired
        if fallback:
            return fallback
        return "I could not produce a completed answer for this request. Please try again."

    async def stream_response(
        self,
        messages: list[dict[str, Any]],
        system: str,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Run the agentic tool-use loop, dispatching tools until the model stops."""
        deterministic_enabled = "NO_TOOL_CALLING" not in system
        report_request = _report_request(messages) if deterministic_enabled else None
        simulation_request = (
            _simulation_request(messages)
            if deterministic_enabled and not report_request
            else None
        )
        deterministic_request = (
            ("generate_report", report_request)
            if report_request
            else ("run_simulation", simulation_request) if simulation_request else None
        )
        if deterministic_request:
            tool_name, tool_input = deterministic_request
            tool_id = "workflow-1"
            yield {"type": "tool_call", "name": tool_name, "input": tool_input, "id": tool_id}
            result_str = await dispatch_tool(tool_name, tool_input)
            yield {"type": "tool_result", "name": tool_name, "result": result_str, "id": tool_id}
            try:
                result = json.loads(result_str)
            except json.JSONDecodeError:
                result = {"error": result_str}
            if tool_name == "generate_report":
                answer = result.get("report_text") or result.get("error") or result.get("preview")
            else:
                answer = _format_simulation_result(result)
            workflow_fallback = (
                _format_news_result(result_str) if tool_name == "search_market_news" else None
            )
            answer = await self._ensure_final_answer(
                str(answer or ""),
                [
                    {"role": "system", "content": system},
                    *messages,
                    {"role": "system", "content": f"Workflow result:\n{result_str}"},
                ],
                max_tokens=max_tokens,
                fallback=workflow_fallback,
            )
            if answer:
                yield {"type": "final_answer", "text": answer}
            yield {"type": "done"}
            return

        full_messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    system
                    if settings.llm_native_tool_calling
                    else _compact_local_system_prompt() + "\n\n" + system
                ),
            },
            *messages,
        ]
        tools_disabled = "NO_TOOL_CALLING" in system
        selected_tools = (
            _tools_for_messages(messages)
            if settings.llm_native_tool_calling and not tools_disabled
            else []
        )

        # Qwen's llama.cpp JSON-schema grammar can spend minutes compiling on
        # CPU before emitting its first token. For the default local path,
        # fetch the most common live market context deterministically and let
        # the model answer from that context without a native tool schema.
        prefetch = None if tools_disabled else _prefetch_request(messages)
        fallback_answer: str | None = None
        if prefetch and not settings.llm_native_tool_calling:
            tool_name, tool_input = prefetch
            tool_id = "prefetch-1"
            yield {"type": "tool_call", "name": tool_name, "input": tool_input, "id": tool_id}
            result_str = await dispatch_tool(tool_name, tool_input)
            if len(result_str) > settings.agent_max_tool_result_chars:
                result_str = (
                    result_str[: settings.agent_max_tool_result_chars]
                    + "\n[tool result truncated for local context budget]"
                )
            yield {"type": "tool_result", "name": tool_name, "result": result_str, "id": tool_id}
            if tool_name == "search_market_news":
                fallback_answer = _format_news_result(result_str)
            elif tool_name == "get_market_overview":
                fallback_answer = _format_market_overview_result(result_str)
            full_messages.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "Live market data was fetched for this request. Use it as the factual "
                        "basis for your answer; do not claim you fetched anything else:\n"
                        f"{result_str}"
                    ),
                },
            )

        completed = False
        max_rounds = max(1, settings.agent_max_tool_rounds)
        for _round_number in range(max_rounds):
            content_parts: list[str] = []
            tool_calls_by_index: dict[int, dict[str, Any]] = {}
            legacy_function_call: dict[str, str] | None = None
            finish_reason: str | None = None

            # llama-cpp is synchronous — consume its iterator in a worker thread
            # and buffer content until we know it is the final answer.
            async with self._inference_lock:
                async for response_chunk in self._stream_completion(
                    full_messages, selected_tools, max_tokens=max_tokens
                ):
                    choices = response_chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    if choice.get("finish_reason") is not None:
                        finish_reason = choice["finish_reason"]
                    delta = choice.get("delta") or {}

                    content = delta.get("content")
                    if content:
                        content_parts.append(content)

                    for tool_call_delta in delta.get("tool_calls") or []:
                        index = int(tool_call_delta.get("index", 0))
                        tool_call = tool_calls_by_index.setdefault(
                            index,
                            {
                                "id": tool_call_delta.get("id") or f"call_{index}",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        if tool_call_delta.get("id"):
                            tool_call["id"] = tool_call_delta["id"]
                        function_delta = tool_call_delta.get("function") or {}
                        if function_delta.get("name"):
                            tool_call["function"]["name"] = function_delta["name"]
                        if function_delta.get("arguments"):
                            tool_call["function"]["arguments"] += function_delta["arguments"]

                    function_delta = delta.get("function_call")
                    if function_delta:
                        if legacy_function_call is None:
                            legacy_function_call = {"name": "", "arguments": ""}
                        if function_delta.get("name"):
                            legacy_function_call["name"] = function_delta["name"]
                        if function_delta.get("arguments"):
                            legacy_function_call["arguments"] += function_delta["arguments"]

            tool_calls = [tool_calls_by_index[index] for index in sorted(tool_calls_by_index)]
            if legacy_function_call:
                tool_calls = [
                    {
                        "id": "call_0",
                        "type": "function",
                        "function": legacy_function_call,
                    }
                ]

            assistant_content = "".join(content_parts) or None

            if finish_reason != "tool_calls" or not tool_calls:
                final_answer = await self._ensure_final_answer(
                    assistant_content,
                    full_messages,
                    max_tokens=max_tokens,
                    fallback=fallback_answer,
                    truncated=finish_reason == "length",
                )
                full_messages.append({"role": "assistant", "content": final_answer})
                yield {"type": "final_answer", "text": final_answer}
                yield {"type": "done"}
                completed = True
                break

            # Keep any model-generated progress text internal when it is
            # attached to a tool call. Only the later no-tool-call turn can
            # become the user-visible final answer.
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": tool_calls,
            }
            full_messages.append(assistant_msg)

            # Dispatch every tool call and feed results back.
            tool_result_messages: list[dict[str, Any]] = []
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                tool_id = tc["id"]
                try:
                    tool_input = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    tool_input = {}

                yield {"type": "tool_call", "name": tool_name, "input": tool_input, "id": tool_id}
                result_str = await dispatch_tool(tool_name, tool_input)
                if len(result_str) > settings.agent_max_tool_result_chars:
                    result_str = (
                        result_str[: settings.agent_max_tool_result_chars]
                        + "\n[tool result truncated for local context budget]"
                    )
                yield {
                    "type": "tool_result",
                    "name": tool_name,
                    "result": result_str,
                    "id": tool_id,
                }
                if tool_name == "search_market_news":
                    fallback_answer = _format_news_result(result_str)
                elif tool_name == "get_market_overview":
                    fallback_answer = _format_market_overview_result(result_str)

                tool_result_messages.append(
                    {"role": "tool", "tool_call_id": tool_id, "content": result_str}
                )

            full_messages.extend(tool_result_messages)

        if not completed:
            logger.warning("Agent stopped after %d tool rounds", max_rounds)
            yield {
                "type": "final_answer",
                "text": "I stopped the tool loop after reaching the local safety limit. "
                "Please narrow the request or ask me to continue.",
            }
            yield {"type": "done"}


def get_llama_cpp_client() -> LlamaCppClient:
    """Return the singleton LlamaCppClient, loading the model on first call."""
    global _instance
    if _instance is None:
        _instance = LlamaCppClient()
    return _instance
