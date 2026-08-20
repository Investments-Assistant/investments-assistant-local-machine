"""Report generator for weekly investment reports."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import json
import os
import uuid

from sqlalchemy import select

from src.agent.utils.logger import get_logger
from src.config import settings

logger = get_logger(__name__)


def _report_period(period_start: str, period_end: str) -> tuple[datetime, datetime]:
    """Parse and validate an inclusive report period."""
    start = datetime.fromisoformat(period_start).replace(tzinfo=UTC)
    end = datetime.fromisoformat(period_end).replace(tzinfo=UTC)
    if end < start:
        raise ValueError("period_end must be on or after period_start")
    if end - start > timedelta(days=366):
        raise ValueError("report period cannot exceed 366 days")
    return start, end


def _safe_json(value: object, max_chars: int = 2_500) -> object:
    """Keep provider responses small enough for the local model context."""
    try:
        encoded = json.dumps(value, default=str, ensure_ascii=False)
        if len(encoded) <= max_chars:
            return value
        return encoded[:max_chars] + "…[truncated]"
    except Exception:
        return str(value)[:max_chars]


async def _collect_report_context(period_start: str, period_end: str) -> dict:
    """Gather evidence before asking the model to write the report.

    The local CPU-safe model cannot reliably discover tools from a large JSON
    schema. Reports therefore use an explicit evidence-gathering workflow and
    give the writer real, user-scoped data with clear availability markers.
    """
    from src.db.database import async_session
    from src.db.models import SimulationResult, Trade, User
    from src.tools.dispatcher import _load_current_user_accounts, _tool_user_id
    from src.tools.market_data import get_market_overview
    from src.tools.news import search_market_news
    from src.tools.news_memory import search_stored_news
    from src.tools.portfolio import get_portfolio_summary

    user_id = _tool_user_id.get()
    context: dict = {
        "period": {"start": period_start, "end": period_end},
        "data_policy": (
            "Use only the evidence below. If a field is unavailable, say so explicitly; "
            "never estimate portfolio performance or invent holdings, prices, trades, or news."
        ),
        "portfolio": {"available": False, "reason": "No broker snapshot was returned."},
        "broker_accounts": [],
        "broker_trade_history": [],
        "internal_trade_audit": [],
        "simulations": [],
        "market_overview": {},
        "live_news": {},
        "stored_news": {},
    }

    accounts, account_error = await _load_current_user_accounts()
    if account_error:
        context["portfolio"] = account_error
    elif accounts is None:
        context["portfolio"] = await asyncio.to_thread(get_portfolio_summary)
    elif accounts:
        context["broker_accounts"] = [account.public for account in accounts]
        context["portfolio"] = await asyncio.to_thread(
            get_portfolio_summary, accounts=accounts
        )
        for account in accounts:
            try:
                from src.tools.portfolio import get_trade_history

                history = await asyncio.to_thread(
                    get_trade_history,
                    broker=account.broker,
                    days=7,
                    account=account,
                )
                context["broker_trade_history"].append(
                    {
                        "broker": account.broker,
                        "account_id": account.id,
                        "account_name": account.display_name,
                        "orders": _safe_json(history),
                    }
                )
            except Exception as exc:
                context["broker_trade_history"].append(
                    {"broker": account.broker, "account_id": account.id, "error": str(exc)}
                )
    else:
        context["portfolio"] = {
            "available": False,
            "reason": "No active brokerage account is configured for this user.",
        }

    # These sources are independent. Keep a report useful even when one feed
    # or broker adapter is unavailable.
    market_task = asyncio.to_thread(get_market_overview)
    live_news_task = asyncio.to_thread(
        search_market_news,
        "stock ETF crypto forex macro markets",
        max_articles=12,
    )
    stored_news_task = search_stored_news(
        query="stock ETF crypto forex macro markets central bank earnings",
        days_back=7,
        limit=20,
    )
    market_result: object
    live_news_result: object
    stored_news_result: object
    market_result, live_news_result, stored_news_result = await asyncio.gather(
        market_task,
        live_news_task,
        stored_news_task,
        return_exceptions=True,
    )
    context["market_overview"] = (
        {"error": str(market_result)}
        if isinstance(market_result, Exception)
        else _safe_json(market_result, 4_000)
    )
    context["live_news"] = (
        {"error": str(live_news_result)}
        if isinstance(live_news_result, Exception)
        else _safe_json(live_news_result, 4_000)
    )
    context["stored_news"] = (
        {"error": str(stored_news_result)}
        if isinstance(stored_news_result, Exception)
        else _safe_json(stored_news_result, 4_000)
    )

    try:
        start_dt, end_dt = _report_period(period_start, period_end)
        user_filter = Trade.user_id == user_id if user_id else Trade.user_id.is_(None)
        sim_filter = (
            SimulationResult.user_id == user_id
            if user_id
            else SimulationResult.user_id.is_(None)
        )
        async with async_session() as session:
            trades = (
                await session.execute(
                    select(Trade)
                    .where(
                        user_filter,
                        Trade.created_at >= start_dt,
                        Trade.created_at <= end_dt + timedelta(days=1),
                    )
                    .order_by(Trade.created_at.asc())
                )
            ).scalars().all()
            simulations = (
                await session.execute(
                    select(SimulationResult)
                    .where(
                        sim_filter,
                        SimulationResult.created_at >= start_dt,
                        SimulationResult.created_at <= end_dt + timedelta(days=1),
                    )
                    .order_by(SimulationResult.created_at.desc())
                    .limit(10)
                )
            ).scalars().all()
            context["internal_trade_audit"] = [
                {
                    "broker": trade.broker,
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "quantity": trade.quantity,
                    "price": trade.price,
                    "status": trade.status,
                    "mode": trade.mode,
                    "pnl_usd": trade.pnl_usd,
                    "created_at": trade.created_at.isoformat(),
                }
                for trade in trades
            ]
            context["simulations"] = [
                {
                    "id": sim.id,
                    "name": sim.name,
                    "strategy": sim.strategy,
                    "initial_capital": sim.initial_capital,
                    "final_value": sim.final_value,
                    "total_return_pct": sim.total_return_pct,
                    "sharpe_ratio": sim.sharpe_ratio,
                    "max_drawdown_pct": sim.max_drawdown_pct,
                    "trades_count": sim.trades_count,
                    "period_start": sim.period_start,
                    "period_end": sim.period_end,
                    "created_at": sim.created_at.isoformat(),
                }
                for sim in simulations
            ]
    except Exception as exc:
        context["internal_data_error"] = str(exc)

    try:
        async with async_session() as session:
            if user_id:
                user = await session.scalar(select(User).where(User.id == user_id))
                if user:
                    context["user_profile"] = {
                        "display_name": user.display_name,
                        "description": user.description,
                        "preferences": user.preferences,
                        "trading_mode": user.trading_mode,
                    }
    except Exception as exc:
        context["user_profile_error"] = str(exc)

    return context


def _fallback_report(context: dict) -> str:
    """Return an honest report if the local writer cannot produce text."""
    period = context["period"]
    portfolio = context.get("portfolio") or {}
    positions = portfolio.get("positions") or []
    market = context.get("market_overview", {}).get("markets", {})
    lines = [
        f"# Weekly Investment Report — {period['start']} to {period['end']}",
        "",
        "## Executive summary",
        "This evidence-backed report was generated locally. Values not returned by a "
        "broker or market source are marked unavailable.",
        "",
        "## Portfolio",
    ]
    if positions:
        lines.extend(
            f"- {p.get('symbol', 'Unknown')}: quantity {p.get('qty', p.get('quantity', 'n/a'))}, "
            f"market value {p.get('market_value', 'n/a')}, "
            f"unrealized P&L {p.get('unrealized_pnl', 'n/a')}"
            for p in positions
        )
    else:
        lines.append(f"- Unavailable: {portfolio.get('reason', 'no positions returned')}.")
    lines.extend(["", "## Market snapshot"])
    for name, item in list(market.items())[:12]:
        lines.append(
            f"- {name}: {item.get('price', 'unavailable')} "
            f"({item.get('change_pct', 'n/a')}%)."
        )
    lines.extend(
        [
            "",
            "## Trades and simulations",
            f"- Internal trade records in the period: "
            f"{len(context.get('internal_trade_audit', []))}.",
            f"- Saved simulations: {len(context.get('simulations', []))}.",
            "",
            "## Limitations and risks",
            "Weekly portfolio P&L requires broker history or valuation snapshots; "
            "it is not estimated here.",
            "Past performance is not a guarantee of future results. This is not financial advice.",
        ]
    )
    return "\n".join(lines)


async def generate_report(
    period_start: str,
    period_end: str | None = None,
) -> dict:
    """Generate a comprehensive investment report using the configured LLM."""
    from src.agent.clients import create_llm_client
    from src.agent.prompts import WEEKLY_REPORT_PROMPT

    end = period_end or datetime.now(UTC).strftime("%Y-%m-%d")

    context = await _collect_report_context(period_start, end)
    prompt = (
        WEEKLY_REPORT_PROMPT.format(period_start=period_start, period_end=end)
        + "\n\n## Evidence gathered by the local agent\n"
        + json.dumps(context, default=str, ensure_ascii=False)[:14_000]
        + "\n\nWrite the report now. Do not ask the user for more details. Clearly "
        "distinguish broker-reported facts, market data, and unavailable fields."
    )
    system = (
        "You are the report-writing stage of a local investment agent. Use only the evidence "
        "included in the user message, write a thorough report, and never invent missing data. "
        "NO_TOOL_CALLING"
    )

    client = create_llm_client()
    full_text = ""
    async for event in client.stream_response(
        messages=[{"role": "user", "content": prompt}],
        system=system,
        max_tokens=settings.report_max_tokens,
    ):
        if event["type"] == "final_answer":
            full_text += event["text"]

    if not full_text.strip():
        full_text = _fallback_report(context)

    # Wrap in HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Investment Report {period_start} to {end}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 900px; margin: 40px auto; padding: 0 20px;
         color: #1a1a2e; line-height: 1.7; }}
  h1 {{ color: #0f3460; border-bottom: 3px solid #e94560; padding-bottom: 10px; }}
  h2 {{ color: #16213e; margin-top: 40px; }}
  h3 {{ color: #0f3460; }}
  table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
  th {{ background: #0f3460; color: white; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
  .positive {{ color: #28a745; font-weight: bold; }}
  .negative {{ color: #dc3545; font-weight: bold; }}
  .disclaimer {{ font-size: 0.85em; color: #666; border-top: 1px solid #ddd;
                 margin-top: 40px; padding-top: 20px; }}
</style>
</head>
<body>
{_markdown_to_html(full_text)}
<div class="disclaimer">
  <strong>Disclaimer:</strong> This report is generated by an AI assistant for informational
  purposes only. It does not constitute financial advice. Always consult a qualified financial
  advisor before making investment decisions. Past performance does not guarantee future results.
</div>
</body>
</html>"""

    # Save PDF
    pdf_path = None
    try:
        import weasyprint

        os.makedirs(settings.reports_dir, exist_ok=True)
        pdf_filename = f"report_{period_start}_{end}_{uuid.uuid4().hex[:12]}.pdf"
        pdf_path = os.path.join(settings.reports_dir, pdf_filename)
        weasyprint.HTML(string=html_content).write_pdf(pdf_path)
        logger.info("Report PDF saved: %s", pdf_path)
    except Exception as exc:
        logger.warning("PDF generation failed (weasyprint): %s", exc)

    # Persist to DB
    try:
        from src.db.database import async_session
        from src.db.models import Report, User
        from src.tools.dispatcher import _tool_user_id

        async with async_session() as session:
            user_id = _tool_user_id.get()
            if not user_id and settings.auth_username:
                user_id = await session.scalar(
                    select(User.id).where(User.username == settings.auth_username)
                )
            report = Report(
                user_id=user_id,
                title=f"Weekly Investment Report {period_start} – {end}",
                period_start=datetime.fromisoformat(period_start).replace(tzinfo=UTC),
                period_end=datetime.fromisoformat(end).replace(tzinfo=UTC),
                html_content=html_content,
                pdf_path=pdf_path,
            )
            session.add(report)
            await session.commit()
            report_id = report.id
    except Exception as exc:
        logger.warning("Failed to persist report: %s", exc)
        report_id = None

    return {
        "success": True,
        "report_id": report_id,
        "period_start": period_start,
        "period_end": end,
        "pdf_path": pdf_path,
        "report_text": full_text,
        "preview": full_text[:500] + "..." if len(full_text) > 500 else full_text,
    }


_HEADING_PREFIXES = (("### ", 3), ("## ", 2), ("# ", 1))


def _match_heading(line: str) -> str | None:
    for prefix, level in _HEADING_PREFIXES:
        if line.startswith(prefix):
            import html

            return f"<h{level}>{html.escape(line[len(prefix) :])}</h{level}>"
    return None


def _process_text_line(line: str, in_ul: bool, html_lines: list[str], re_module) -> bool:
    """Handle a non-heading, non-list line. Returns the new in_ul state."""
    if in_ul:
        html_lines.append("</ul>")
        in_ul = False
    if line.strip():
        import html

        line = html.escape(line)
        line = re_module.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        html_lines.append(f"<p>{line}</p>")
    else:
        html_lines.append("")
    return in_ul


def _markdown_to_html(text: str) -> str:
    """Very basic markdown → HTML conversion."""
    import re

    lines = text.split("\n")
    html_lines: list[str] = []
    in_ul = False
    for line in lines:
        heading = _match_heading(line)
        if heading is not None:
            html_lines.append(heading)
        elif line.startswith("- ") or line.startswith("* "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            import html

            html_lines.append(f"<li>{html.escape(line[2:])}</li>")
        else:
            in_ul = _process_text_line(line, in_ul, html_lines, re)
    if in_ul:
        html_lines.append("</ul>")
    return "\n".join(html_lines)
