"""Evidence-linked report commentary; financial statements are rendered separately."""

import json
from typing import Literal

from pydantic import Field, BaseModel, ConfigDict, model_validator

from src.agent.clients.news_analysis import Observation, prepare_news, instruction_quote, factual_candidates


class ReportAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["supported_extracts", "abstain"]
    observations: list[Observation] = Field(max_length=3)

    @model_validator(mode="after")
    def consistent_status(self):
        if bool(self.observations) != (self.status == "supported_extracts"):
            raise ValueError("Report extract status does not match observations")
        return self


def report_analysis_schema(sources):
    schema = ReportAnalysis.model_json_schema()
    candidates = factual_candidates(sources)
    if candidates:
        schema["$defs"]["Observation"]["properties"]["source_id"]["enum"] = list(candidates)
        schema["$defs"]["Observation"]["properties"]["quote"]["enum"] = list(dict.fromkeys(
            quote for source in candidates.values() for quote in source["eligible_quotes"]))
    else:
        schema["properties"]["status"]["enum"] = ["abstain"]
        schema["properties"]["observations"]["maxItems"] = 0
    return schema


def report_sources(context):
    sources, _ = prepare_news({
        "search_market_news": json.dumps(context.get("live_news", {}), default=str),
        "search_stored_news": json.dumps(context.get("stored_news", {}), default=str),
    })
    return sources


def validate_report_analysis(raw, sources):
    if len(raw) > 16000:
        raise ValueError("REPORT_MODEL_OUTPUT_INVALID")
    analysis = ReportAnalysis.model_validate_json(raw)
    candidates = factual_candidates(sources)
    seen = set()
    for observation in analysis.observations:
        source = sources.get(observation.source_id)
        if source is None or observation.quote not in source["excerpt"]:
            raise ValueError("REPORT_MODEL_OUTPUT_INVALID")
        if observation.quote not in candidates.get(observation.source_id, {}).get("eligible_quotes", []):
            raise ValueError("REPORT_QUOTE_NOT_ELIGIBLE_SOURCE_SENTENCE")
        if instruction_quote(observation.quote):
            raise ValueError("SOURCE_INSTRUCTION_NOT_REPORT_OBSERVATION")
        identity = (observation.source_id, observation.quote)
        if identity in seen:
            raise ValueError("REPORT_MODEL_OUTPUT_INVALID")
        seen.add(identity)
    return analysis


def render_report_analysis(analysis, sources):
    lines = ["", "## Attributed news evidence", "Source statements below are unverified quotations, "
             "not reconciled account executions, independent corroboration or trading signals."]
    if not analysis.observations:
        lines.append("The model abstained from selecting supported source extracts.")
    for observation in analysis.observations:
        source = sources[observation.source_id]
        # JSON encoding keeps source newlines from creating report headings or bullets.
        citation = json.dumps({key: source.get(key) for key in (
            "title", "source", "url", "published_at", "available_at"
        )}, ensure_ascii=False)
        lines.append(f"- Source {observation.source_id}: {citation}; "
                     f"quoted text: {json.dumps(observation.quote, ensure_ascii=False)}")
    return "\n".join(lines)


async def infer_report_analysis(client, *, prompt, system, schema, sources, max_tokens):
    """At most two tool-free attempts; never reuse rejected model prose as evidence."""
    from contextlib import aclosing

    messages = [{"role": "user", "content": prompt}]
    reason = "MODEL_INCOMPLETE"
    for attempt in range(1, 3):
        raw = ""
        completed = False
        invalid = False
        try:
            async with aclosing(client.stream_response(
                messages=messages, system=system, max_tokens=max_tokens, response_schema=schema,
            )) as events:
                async for event in events:
                    if event["type"] == "error":
                        return None, "MODEL_UNAVAILABLE", attempt
                    if event["type"] in {"tool_call", "tool_result"}:
                        return None, "REPORT_MODEL_CONTRACT_VIOLATION", attempt
                    if event["type"] == "final_answer":
                        if raw or not isinstance(event.get("text"), str):
                            invalid = True
                            break
                        raw = event["text"]
                        if len(raw) > 16000:
                            invalid = True
                            break
                    if event["type"] == "done":
                        completed = True
                        break
        except Exception:
            return None, "MODEL_UNAVAILABLE", attempt
        if invalid:
            reason = "REPORT_MODEL_OUTPUT_INVALID"
        elif not completed or not raw.strip():
            reason = "MODEL_INCOMPLETE"
        else:
            try:
                return validate_report_analysis(raw, sources), None, attempt
            except ValueError:
                reason = "REPORT_MODEL_OUTPUT_INVALID"
        if attempt == 1:
            messages.append({"role": "user", "content": (
                "The prior attempt failed validation. Return only the requested JSON, using the original "
                "source IDs and exact source excerpts, or abstain with no observations. "
                "The original evidence remains the sole source of facts."
            )})
    return None, reason, 2
