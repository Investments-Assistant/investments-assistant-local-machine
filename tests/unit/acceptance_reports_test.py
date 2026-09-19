from datetime import UTC, datetime

from src.scheduler.reporter import _safe_json, _period_records


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
