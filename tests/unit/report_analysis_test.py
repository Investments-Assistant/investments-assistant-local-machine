import json

import pytest

from src.scheduler.report_analysis import report_sources, render_report_analysis, validate_report_analysis


def fixture_sources():
    return report_sources({"stored_news": {"articles": [{
        "title": "Fixture source", "source": "Synthetic", "url": "https://example.invalid/news",
        "content": "An attributable source statement about the synthetic market. " * 3,
        "published_at": "2026-01-01T00:00:00Z", "available_at": "2026-01-01T00:01:00Z",
    }]}})


def test_valid_report_extract_retains_exact_text_and_attribution():
    sources = fixture_sources()
    source_id = next(iter(sources))
    quote = "An attributable source statement about the synthetic market."
    analysis = validate_report_analysis(json.dumps({
        "status": "supported_extracts", "observations": [{"source_id": source_id, "quote": quote}],
    }), sources)
    rendered = render_report_analysis(analysis, sources)
    assert quote in rendered and source_id in rendered
    assert "2026-01-01T00:01:00Z" in rendered and "example.invalid" in rendered
    assert "unverified quotations" in rendered and "not reconciled account executions" in rendered


@pytest.mark.parametrize("case", ["invented", "foreign_source", "duplicate", "extra", "inconsistent", "oversized"])
def test_invalid_report_analysis_is_rejected(case):
    sources = fixture_sources()
    source_id = next(iter(sources))
    observation = {"source_id": source_id, "quote": "An attributable source statement about the synthetic market."}
    payload = {"status": "supported_extracts", "observations": [observation]}
    if case == "invented":
        observation["quote"] = "Your portfolio profit was USD 999999."
    elif case == "foreign_source":
        observation["source_id"] = "a" * 64
    elif case == "duplicate":
        payload["observations"].append(observation.copy())
    elif case == "extra":
        payload["profit"] = "999999"
    elif case == "inconsistent":
        payload["status"] = "abstain"
    raw = json.dumps(payload)
    if case == "oversized":
        raw += " " * 16000
    with pytest.raises(ValueError):
        validate_report_analysis(raw, sources)


def test_report_abstention_is_explicit_without_false_source_claims():
    analysis = validate_report_analysis('{"status":"abstain","observations":[]}', {})
    assert "abstained" in render_report_analysis(analysis, {})


def test_report_schema_restricts_known_source_ids_and_forces_abstention_without_sources():
    from src.scheduler.report_analysis import report_analysis_schema

    empty = report_analysis_schema({})
    assert empty["properties"]["status"]["enum"] == ["abstain"]
    assert empty["properties"]["observations"]["maxItems"] == 0
    sources = fixture_sources()
    available = report_analysis_schema(sources)
    assert available["$defs"]["Observation"]["properties"]["source_id"]["enum"] == list(sources)
    assert available["properties"]["observations"]["maxItems"] == 3
