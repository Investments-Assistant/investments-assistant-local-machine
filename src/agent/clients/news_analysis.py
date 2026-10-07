"""Validated source extracts and abstention; no inferred market/price claims."""

import re
import json
from typing import Literal
import hashlib

from pydantic import Field, BaseModel, ConfigDict, model_validator

# Conservative source-selection quality filter, not an authorization boundary.
# Arbitrary obfuscated instructions still cannot grant tools or account capabilities.
_DIRECTIVE = re.compile(
    r"(?:^|[.!?\n]\s*)(?:ignore|disregard|override|buy|sell|submit|cancel|execute|send|reveal|enable|disable|change)\b"
    r"|\b(?:system prompt|developer message|api[_ ]key|access[_ ]token|assistant\s*:)" , re.I
)


def instruction_quote(quote):
    return bool(_DIRECTIVE.search(quote.lstrip()))


NEWS_TOOLS = {"get_latest_news", "search_stored_news", "search_market_news"}


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=64, max_length=64)
    quote: str = Field(min_length=20, max_length=400)


class NewsAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["supported_extracts", "abstain"]
    observations: list[Observation] = Field(max_length=3)
    missing_data: list[Literal["body", "price_context", "independent_corroboration", "publication_time",
                               "entity_resolution", "source_unavailable", "availability_time"]] = Field(max_length=7)

    @model_validator(mode="after")
    def consistent_status(self):
        if bool(self.observations) != (self.status == "supported_extracts"):
            raise ValueError("Supported extracts require observations; abstention cannot assert them")
        return self


def prepare_news(results):
    sources = {}
    failures = False
    for name, raw in results.items():
        if name not in NEWS_TOOLS:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            failures = True
            continue
        if not isinstance(payload, dict) or payload.get("status") in {"blocked", "unavailable", "partial_failure"}:
            failures = True
        articles = payload.get("articles", []) if isinstance(payload, dict) else []
        if not isinstance(articles, list):
            failures = True
            continue
        for row in articles[:10]:
            if len(sources) >= 10:
                break
            if not isinstance(row, dict):
                failures = True
                continue
            text = row.get("content") or row.get("summary") or ""
            if not isinstance(text, str) or len(text.strip()) < 80:
                continue
            evidence = {key: row.get(key) for key in ("title", "source", "url", "available_at", "published_at")}
            evidence.update(excerpt=text[:1200], excerpt_clipped=len(text) > 1200)
            identity = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            sources[identity] = evidence
            if len(sources) >= 10:
                break
    return sources, failures


def factual_candidates(sources):
    """Bounded exact source sentences; filter recognized directives from model input.

    This reduces exposure and improves selection, but cannot prove arbitrary text
    true or instruction-free. Tool/authority isolation remains mandatory.
    """
    eligible = {}
    for identity, source in sources.items():
        quotes = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n+", source["excerpt"])
                  if 20 <= len(sentence.strip()) <= 400 and not instruction_quote(sentence.strip())]
        if quotes:
            eligible[identity] = {"eligible_quotes": quotes[:6]}
    return eligible


def validate_assessment(raw, sources):
    assessment = NewsAssessment.model_validate_json(raw)
    candidates = factual_candidates(sources)
    seen = set()
    for item in assessment.observations:
        if item.source_id not in sources or item.quote not in sources[item.source_id]["excerpt"]:
            raise ValueError("UNSUPPORTED_NEWS_EXTRACT")
        if item.quote not in candidates.get(item.source_id, {}).get("eligible_quotes", []):
            raise ValueError("NEWS_QUOTE_NOT_ELIGIBLE_SOURCE_SENTENCE")
        if instruction_quote(item.quote):
            raise ValueError("SOURCE_INSTRUCTION_NOT_NEWS_OBSERVATION")
        identity = (item.source_id, item.quote)
        if identity in seen:
            raise ValueError("DUPLICATE_NEWS_EXTRACT")
        seen.add(identity)
    return assessment


def render_assessment(assessment, sources, *, reason=None):
    result = assessment.model_dump()
    result["authority"] = "source_extracts_only_not_independent_corroboration_or_trading_signal"
    result["sources"] = {item.source_id: {key: value for key, value in sources[item.source_id].items()
                                        if key not in {"excerpt", "excerpt_clipped"}}
                         for item in assessment.observations}
    if reason:
        result["reason"] = reason
    return "News evidence assessment\n\n```json\n" + json.dumps(result, ensure_ascii=False, indent=2) \
        .replace("`", "\\u0060") + "\n```"
