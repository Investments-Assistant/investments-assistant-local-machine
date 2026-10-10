"""Retained order callbacks cannot silently certify cancellation or filled quantity."""

from src.execution.policy import digest
from src.execution.broker_review import review_observations


def observation(kind, identity, **fields):
    payload = dict(client_id=77, order_id=1, permanent_id=9, **fields)
    return dict(kind=kind, identity_sha256=identity, payload=payload, payload_sha256=digest(payload))


def status(value, filled="0", remaining="1", **overrides):
    row = observation("order_status", "order", status=value, filled=filled, remaining=remaining)
    row["payload"].update(overrides)
    row["payload_sha256"] = digest(row["payload"])
    return row


def execution(identity="fill1", quantity="1", family="family1"):
    return observation("execution", identity, quantity=quantity, correction_family=family)


def commission(identity="fill1"):
    return observation("commission", identity, amount="0.1", correction_family="family1")


def test_cancel_fill_conflict_is_visible_regardless_of_arrival_order():
    rows = [status("Cancelled"), status("Filled", "1", "0"), execution(), commission()]
    for values in (rows, list(reversed(rows))):
        result = review_observations(values)
        assert "ORDER_TERMINAL_STATUS_CONFLICT" in result["reason_codes"]
        assert result["status"] == "needs_review" and result["execution_authority"] == "none"
        order = result["order_lifecycle"]["orders"][0]
        assert order["statuses_observed"] == ["Cancelled", "Filled"]
        assert order["current_state"] == "not_established"


def test_reported_fill_without_execution_is_an_evidence_gap():
    result = review_observations([status("Filled", "0.004", "0")])
    assert "ORDER_FILL_EXECUTION_GAP" in result["reason_codes"]
    assert result["order_lifecycle"]["orders"][0]["execution_quantity"] == "0"


def test_partial_fills_and_duplicate_statuses_are_not_added_twice():
    rows = [status("Submitted", "0.004", "0.006"), status("Submitted", "0.0040", "0.0060"),
            status("Filled", "0.010", "0"), execution("a", "0.004", "a"),
            execution("b", "0.006", "b"), commission("a"), commission("b")]
    result = review_observations(rows)
    assert result["reason_codes"] == []
    order = result["order_lifecycle"]["orders"][0]
    assert order["execution_quantity"] == "0.010"
    assert order["current_state"] == "not_established"
    assert result["order_lifecycle"]["complete_reconciliation"] is False


def test_pending_cancel_is_not_confirmed_cancel_and_same_client_id_can_have_new_permanent_id():
    result = review_observations([status("PendingCancel"), status("Submitted", permanent_id=10)])
    assert result["reason_codes"] == []
    orders = result["order_lifecycle"]["orders"]
    assert len(orders) == 2
    assert any(order["pending_cancel_observed"] for order in orders)
    assert all(order["current_state"] == "not_established" for order in orders)



def test_corrections_or_cross_order_execution_conflicts_do_not_produce_a_fill_total():
    first = execution()
    correction = execution("fill2", "2", "family1")
    conflicting = execution()
    conflicting["payload"]["permanent_id"] = 10
    conflicting["payload_sha256"] = digest(conflicting["payload"])
    for rows in ([first, correction], [first, conflicting]):
        result = review_observations([status("Filled", "1", "0"), *rows])
        order = result["order_lifecycle"]["orders"][0]
        assert order["execution_quantity"] is None
        assert "ORDER_EXECUTION_VERSION_UNRESOLVED" in order["reason_codes"]


def test_unknown_identity_invalid_quantity_and_partial_pages_stay_unverified():
    result = review_observations([status("Filled", "1", "2", permanent_id=0)])
    assert "ORDER_PERMANENT_ID_UNAVAILABLE" in result["reason_codes"]
    assert "ORDER_FILLED_STATUS_INCONSISTENT" in result["reason_codes"]
    result = review_observations([status("Submitted", "NaN")])
    assert "ORDER_QUANTITY_EVIDENCE_INVALID" in result["reason_codes"]
    assert "ORDER_REVIEW_WINDOW_TRUNCATED" in review_observations([status("Submitted")], truncated=True)["reason_codes"]


def test_execution_ahead_of_old_status_is_not_silently_marked_cancelled():
    result = review_observations([status("Cancelled", "0.004", "0.006"), execution(quantity="0.01"), commission()])
    assert "ORDER_TERMINAL_EXECUTION_MISMATCH" in result["reason_codes"]
    assert result["order_lifecycle"]["orders"][0]["current_state"] == "not_established"


def test_review_details_are_bounded_but_all_selected_orders_are_counted():
    result = review_observations([status("Submitted", permanent_id=index + 1) for index in range(101)])
    review = result["order_lifecycle"]
    assert len(review["orders"]) == 100 and review["orders_checked"] == 101
    assert review["details_truncated"] is True
