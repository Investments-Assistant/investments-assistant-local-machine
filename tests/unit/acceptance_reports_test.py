from datetime import UTC, datetime

import pytest

from src.scheduler.reporter import _safe_json, _report_period, _period_records, _history_evidence


def test_report_period_is_half_open_and_undated_records_are_not_facts():
    rows = [
        {"created_at": value}
        for value in [
            "2026-01-01T00:00:00Z",
            "2026-01-31T23:59:59Z",
            "2026-02-01T00:00:00Z",
            None,
            "2026-01-15T00:00:00",
        ]
    ]
    assert (
        _period_records(rows, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 31, tzinfo=UTC))
        == rows[:2]
    )


def test_report_never_truncates_json_into_a_broken_document():
    assert _safe_json({"large": "x" * 200}, 100)["status"] == "evidence_budget_exceeded"


@pytest.mark.parametrize("invalid", [
    "2026-01-01T23:00:00-05:00", "2026-01-01T00:00:00Z", "20260101", "2026-W01-4", "2026-02-30",
])
def test_report_rejects_non_calendar_date_boundaries(invalid):
    with pytest.raises(ValueError):
        _report_period(invalid, "2026-12-31")
    with pytest.raises(ValueError):
        _report_period("2026-01-01", invalid)


def test_report_inclusive_calendar_day_compares_offset_evidence_as_instants():
    start, end = _report_period("2026-01-01", "2026-01-01")
    rows = [{"filled_at": stamp} for stamp in [
        "2025-12-31T23:30:00-01:00", "2026-01-01T23:30:00-01:00", "2026-01-02T00:30:00+01:00",
    ]]
    assert _period_records(rows, start, end) == [rows[0], rows[2]]


@pytest.mark.parametrize("records", [
    [{"error": "private broker failure"}],
    [{"status": "unavailable", "created_at": "2026-01-01T00:00:00Z"}],
    [{"created_at": "2026-01-01T00:00:00"}],
    [None],
])
def test_history_failures_cannot_be_filtered_into_successful_empty_history(records):
    from src.scheduler.reporter import _collection_errors

    start, end = _report_period("2026-01-01", "2026-01-31")
    result = _history_evidence(records, start, end)
    assert result["status"] == "partial_failure"
    assert result["orders"] == []
    assert result["rejected_records"] == 1
    assert "private broker" not in str(result)
    assert _collection_errors({"broker_trade_history": [result]})


def test_empty_and_out_of_period_history_are_distinct_from_failed_history():
    from src.scheduler.reporter import _collection_errors

    start, end = _report_period("2026-01-01", "2026-01-31")
    for records in ([], [{"created_at": "2025-12-31T00:00:00Z"}]):
        result = _history_evidence(records, start, end)
        assert result["orders"] == [] and result["status"] == "complete"
        assert not _collection_errors({"broker_trade_history": [result]})
    for records in ({"error": "private broker failure"}, [{}] * 2001):
        result = _history_evidence(records, start, end)
        assert result["status"] == "unavailable"
        assert "private broker" not in str(result)


@pytest.mark.parametrize("source,payload", [
    ("portfolio", {"available": False}),
    ("portfolio", {"valuation_status": "partial", "positions": []}),
    ("portfolio", {"valuation_status": "unavailable"}),
    ("portfolio", {"valuation_status": "unverified"}),
    ("stored_news", {"status": "blocked", "articles": []}),
])
def test_explicit_missing_source_states_make_report_partial(source, payload):
    from src.scheduler.reporter import _collection_errors

    assert _collection_errors({source: payload}) == [
        {"stage": "collection", "source": source, "code": "SOURCE_INCOMPLETE"}
    ]


def test_available_empty_sources_do_not_create_report_failure():
    from src.scheduler.reporter import _collection_errors

    assert _collection_errors({
        "portfolio": {"available": True, "valuation_status": "complete", "positions": []},
        "stored_news": {"status": "complete", "articles": []},
    }) == []


def test_fallback_report_preserves_exact_account_currency_and_valuation_limits():
    from src.scheduler.reporter import _fallback_report

    context = {
        "period": {"start": "2026-01-01", "end": "2026-01-31"},
        "as_of": "2026-02-01T00:00:00Z", "base_currency": "USD",
        "portfolio": {"positions": [
            {"symbol": "FIXTURE", "account_id": "synthetic-a", "quantity_exact": "0.0040000000001",
             "quantity": 0, "currency": "EUR", "price": "100", "market_value": "0.40000000001"},
            {"symbol": "FIXTURE", "account_id": "synthetic-b", "quantity": "1", "market_value": "999"},
        ], "total_market_value_usd_exact": "1.00000000000000000001", "total_market_value_usd": 1.0},
    }
    text = _fallback_report(context)
    assert "synthetic-a" in text and "synthetic-b" in text
    assert "0.0040000000001" in text and "source currency EUR" in text
    assert "0.40000000001" in text and "1.00000000000000000001" in text
    assert "999" not in text  # Unknown-currency values cannot become authoritative amounts.
    assert "Source valuation timestamp: unavailable" in text
    assert "Evidence collected at: 2026-02-01T00:00:00Z" in text
    assert "Internal audit records are not reconciled fills" in text
    assert "Realized P&L, external flows" in text


def test_report_heading_closes_previous_list_and_escapes_source_markup():
    from src.scheduler.reporter import _markdown_to_html

    rendered = _markdown_to_html('''- first
## <script>alert(1)</script>
- second''')
    assert '</li>\n</ul>\n<h2>' in rendered
    assert rendered.count('<ul>') == rendered.count('</ul>') == 2
    assert '<script>' not in rendered
    assert '&lt;script&gt;' in rendered
