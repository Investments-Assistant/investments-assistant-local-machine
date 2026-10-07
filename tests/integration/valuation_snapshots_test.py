"""Observed marks must be immutable, scoped, and cannot impersonate historical prices."""

from decimal import Decimal
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.execution.models import ValuationSnapshot, SimulatorInstrument
from src.execution.policy import PolicyDenied
from src.execution.valuation import capture_valuation, period_performance
from src.execution.account_events import record_cash_flow, record_dividend_payment
from tests.integration.simulator_sales_test import owned

pytestmark = pytest.mark.integration


async def capture(session, ids, key):
    return await capture_valuation(session, user_id=ids[0], account_id=ids[1], snapshot_key=key)


async def test_period_marks_separate_flows_income_and_unrealized_changes(db_session):
    ids, account, _ = await owned(db_session)
    opening = await capture(db_session, ids, "opening")
    await record_cash_flow(
        db_session,
        user_id=ids[0],
        account_id=ids[1],
        event_key="deposit",
        amount_base="100",
        currency="EUR",
        effective_at=datetime.now(UTC),
        source_reference="synthetic",
        fixture_event=True,
    )
    await record_dividend_payment(
        db_session,
        user_id=ids[0],
        account_id=ids[1],
        instrument_id=ids[2],
        allocation_id="manual",
        event_key="dividend",
        gross_base="10",
        withholding_base="2.5",
        currency="EUR",
        effective_at=datetime.now(UTC),
        source_reference="synthetic",
        fixture_event=True,
    )
    instrument = await db_session.get(SimulatorInstrument, ids[2])
    instrument.price, instrument.as_of = Decimal(130), datetime.now(UTC)
    closing = await capture(db_session, ids, "closing")
    assert (await capture(db_session, ids, "opening"))["snapshot_id"] == opening["snapshot_id"]
    result = await period_performance(
        db_session,
        user_id=ids[0],
        account_id=ids[1],
        start=datetime.fromisoformat(opening["as_of"]),
        end=datetime.fromisoformat(closing["as_of"]),
    )
    assert result["status"] == "complete"
    assert Decimal(result["allocations"][0]["portfolio_pnl"]) == Decimal("27.5")
    assert Decimal(result["portfolio_pnl"]) == Decimal("27.5")
    assert Decimal(result["net_external_flows"]) == 100
    assert Decimal(result["unrealized_change"]) == 20 and Decimal(result["realized_change"]) == 0
    assert Decimal(result["dividend_net"]) == Decimal("7.5")
    assert Decimal(result["fx_effect"]) == 0 and result["benchmark_return"] is None
    assert Decimal(result["price_effect"]) == 20
    assert Decimal(result["allocation_attribution"][0]["income"]) == Decimal("7.5")
    await db_session.refresh(account)
    assert account.cash == Decimal("907.5")


async def test_unavailable_boundaries_never_use_current_quotes_as_past_marks(db_session):
    ids, _, _ = await owned(db_session)
    snapshot = await capture(db_session, ids, "current")
    now = datetime.fromisoformat(snapshot["as_of"])
    result = await period_performance(
        db_session, user_id=ids[0], account_id=ids[1], start=now - timedelta(days=1), end=now
    )
    assert result["status"] == "unavailable" and result["portfolio_pnl"] is None
    quote = await db_session.get(SimulatorInstrument, ids[2])
    quote.as_of = now - timedelta(minutes=2)
    with pytest.raises(PolicyDenied, match="VALUATION_STALE"):
        await capture(db_session, ids, "stale")
    assert (
        len((await db_session.scalars(select(ValuationSnapshot).where(ValuationSnapshot.account_id == ids[1]))).all())
        == 1
    )


async def test_snapshot_tamper_and_other_owner_are_rejected(db_session):
    ids, _, _ = await owned(db_session)
    snapshot = await capture(db_session, ids, "original")
    other, _, _ = await owned(db_session)
    with pytest.raises(PolicyDenied, match="ACCOUNT_NOT_OWNED"):
        await capture_valuation(db_session, user_id=other[0], account_id=ids[1], snapshot_key="foreign")
    row = await db_session.get(ValuationSnapshot, snapshot["snapshot_id"])
    row.payload = dict(row.payload, equity="999999")
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="VALUATION_EVIDENCE_INVALID"):
        await capture(db_session, ids, "original")


async def test_report_uses_snapshot_boundaries_and_survives_late_fee_restatement(db_session):
    from src.scheduler.reporter import _fallback_report
    from src.execution.reporting import collect_execution_period
    from src.execution.commissions import record_commission
    from tests.integration.commissions_test import callback

    ids, _, buy = await owned(db_session)
    opening = await capture(db_session, ids, "start")
    await record_commission(
        db_session, **callback(ids, buy["order_id"], datetime.now(UTC), execution_id="buy", amount="0.20")
    )
    closing = await capture(db_session, ids, "end")
    report = await collect_execution_period(
        db_session,
        user_id=ids[0],
        start=datetime.fromisoformat(opening["as_of"]),
        end=datetime.fromisoformat(closing["as_of"]),
    )
    row = report["accounts"][0]
    assert Decimal(row["portfolio_period_pnl"]) == Decimal("-0.20")
    assert Decimal(row["period_performance"]["fees_change"]) == Decimal("0.20")
    assert row["execution_count"] == 0  # The purchase predates this observed period.
    rendered = _fallback_report(
        {"period": {"start": opening["as_of"], "end": closing["as_of"]}, "simulator_execution_period": report}
    )
    assert opening["snapshot_id"] in rendered and closing["snapshot_id"] in rendered
    assert "Observed period portfolio P&L" in rendered
    assert "Price contribution" in rendered and "FX contribution" in rendered
    assert Decimal(row["period_performance"]["fx_effect"]) == 0
    assert Decimal(row["period_performance"]["price_effect"]) == 0


@pytest.mark.parametrize("sale_quantity, stale", [("0", False), ("1", False), ("2", False), ("2", True)])
async def test_foreign_execution_price_fx_and_fees_reconcile_for_open_and_closed_positions(
    db_session, sale_quantity, stale
):
    from src.execution.models import SimulatorAccount
    from src.execution.service import record_fill
    from tests.integration.execution_test import seed, proposal, confirmation
    from tests.integration.simulator_sales_test import sell

    ids = await seed(db_session)
    account = await db_session.get(SimulatorAccount, ids[1])
    account.mandate = dict(account.mandate, fixture=True, manual_sales=True, fee_bps="20")
    quote = await db_session.get(SimulatorInstrument, ids[2])
    quote.currency, quote.fx_to_base = "USD", Decimal("0.9")
    opening = await capture(db_session, ids, "before-foreign-buy")
    purchase = await proposal(db_session, ids, quantity="2")
    await confirmation(db_session, ids, purchase)
    await record_fill(db_session, user_id=ids[0], account_id=ids[1], order_id=purchase["order_id"],
                      execution_id="foreign-buy", quantity="2", price="100", fee="0.2")
    if sale_quantity != "0":
        quote.price, quote.fx_to_base, quote.as_of = Decimal(120), Decimal("0.95"), datetime.now(UTC)
        sale = await sell(db_session, ids, sale_quantity)
        await confirmation(db_session, ids, sale)
        await record_fill(db_session, user_id=ids[0], account_id=ids[1], order_id=sale["order_id"],
                          execution_id="foreign-sale", quantity=sale_quantity, price="120", fee="0.1")
    quote.price, quote.fx_to_base, quote.as_of = Decimal(110), Decimal(1), datetime.now(UTC)
    if stale:
        quote.as_of -= timedelta(minutes=2)
    closing = await capture(db_session, ids, "after-foreign-trades")
    result = await period_performance(db_session, user_id=ids[0], account_id=ids[1],
                                     start=datetime.fromisoformat(opening["as_of"]),
                                     end=datetime.fromisoformat(closing["as_of"]))
    price, fx, fees = {"0": ("20", "20", "0.2"), "1": ("30", "14", "0.3"),
                       "2": ("40", "8", "0.3")}[sale_quantity]
    if stale:
        assert result["status"] == "complete" and Decimal(result["portfolio_pnl"]) == Decimal("47.7")
        assert result["fx_effect"] is None and result["fx_attribution_reason"] == "CLOSING_FX_MARK_UNAVAILABLE"
        later = await capture(db_session, ids, "dormant-closed-position")
        unchanged = await period_performance(db_session, user_id=ids[0], account_id=ids[1],
                                            start=datetime.fromisoformat(closing["as_of"]),
                                            end=datetime.fromisoformat(later["as_of"]))
        assert unchanged["fx_attribution_status"] == "complete" and Decimal(unchanged["fx_effect"]) == 0
        return
    assert result["fx_attribution_status"] == "complete"
    assert Decimal(result["price_effect"]) == Decimal(price)
    assert Decimal(result["fx_effect"]) == Decimal(fx)
    assert Decimal(result["attribution_fees"]) == Decimal(fees)
    assert Decimal(result["portfolio_pnl"]) == Decimal(price) + Decimal(fx) - Decimal(fees)
    assert result["allocation_attribution"][0]["allocation_id"] == "manual"


async def test_legacy_snapshot_keeps_period_pnl_but_cannot_invent_fx_history(db_session):
    from src.execution.policy import digest
    from src.execution.valuation import evidence

    ids, _, _ = await owned(db_session)
    opening = await capture(db_session, ids, "legacy")
    row = await db_session.get(ValuationSnapshot, opening["snapshot_id"])
    legacy = dict(row.payload)
    del legacy["execution_totals"]
    del legacy["fx_marks"]
    legacy["schema"] = 1
    row.payload = legacy
    row.evidence_hash = digest(evidence(row))  # Faithful fixture of previously emitted schema1.
    closing = await capture(db_session, ids, "new")
    result = await period_performance(db_session, user_id=ids[0], account_id=ids[1],
                                     start=datetime.fromisoformat(opening["as_of"]),
                                     end=datetime.fromisoformat(closing["as_of"]))
    assert result["status"] == "complete" and Decimal(result["portfolio_pnl"]) == 0
    assert result["fx_effect"] is None and result["fx_attribution_reason"] == "ATTRIBUTION_HISTORY_UNAVAILABLE"


async def test_future_bookings_and_invalid_fx_cannot_create_historical_marks(db_session):
    from src.execution.models import ExecutionEvent

    ids, _, buy = await owned(db_session)
    quote = await db_session.get(SimulatorInstrument, ids[2])
    quote.fx_to_base = Decimal("1.1")
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="VALUATION_FX_UNAVAILABLE"):
        await capture(db_session, ids, "bad-fx")
    quote.fx_to_base = Decimal(1)
    event = await db_session.scalar(
        select(ExecutionEvent).where(ExecutionEvent.order_id == buy["order_id"], ExecutionEvent.kind == "fill")
    )
    event.observed_at = datetime.now(UTC) + timedelta(hours=1)
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="VALUATION_CLOCK_REGRESSION"):
        await capture(db_session, ids, "clock-regressed")
    assert not (await db_session.scalars(select(ValuationSnapshot).where(ValuationSnapshot.account_id == ids[1]))).all()


async def test_capacity_and_corrupt_boundary_do_not_invent_period_pnl(db_session, monkeypatch):
    from src.execution import valuation
    from src.execution.reporting import collect_execution_period

    ids, _, _ = await owned(db_session)
    opening = await capture(db_session, ids, "opening")
    closing = await capture(db_session, ids, "closing")
    monkeypatch.setattr(valuation, "MAX_SNAPSHOTS", 2)
    with pytest.raises(PolicyDenied, match="VALUATION_CAPACITY"):
        await capture(db_session, ids, "extra")
    row = await db_session.get(ValuationSnapshot, opening["snapshot_id"])
    row.payload = dict(row.payload, cash="0")
    await db_session.flush()
    result = await collect_execution_period(
        db_session,
        user_id=ids[0],
        start=datetime.fromisoformat(opening["as_of"]),
        end=datetime.fromisoformat(closing["as_of"]),
    )
    assert result["status"] == "partial_failure"
    assert result["accounts"][0]["portfolio_period_pnl"] is None
    assert result["accounts"][0]["period_performance"]["reason"] == "VALUATION_EVIDENCE_INVALID"


async def test_opening_foreign_holding_attributes_interaction_to_closing_rate_price(db_session):
    from src.execution.service import record_fill
    from tests.integration.execution_test import seed, proposal, confirmation

    ids = await seed(db_session)
    quote = await db_session.get(SimulatorInstrument, ids[2])
    quote.currency, quote.fx_to_base = "USD", Decimal("0.9")
    purchase = await proposal(db_session, ids, quantity="2")
    await confirmation(db_session, ids, purchase)
    await record_fill(db_session, user_id=ids[0], account_id=ids[1], order_id=purchase["order_id"],
                      execution_id="foreign-buy", quantity="2", price="100")
    opening = await capture(db_session, ids, "held-opening")
    quote.price, quote.fx_to_base, quote.as_of = Decimal(110), Decimal("0.95"), datetime.now(UTC)
    closing = await capture(db_session, ids, "held-closing")
    result = await period_performance(db_session, user_id=ids[0], account_id=ids[1],
                                     start=datetime.fromisoformat(opening["as_of"]),
                                     end=datetime.fromisoformat(closing["as_of"]))
    assert Decimal(result["portfolio_pnl"]) == 29
    assert Decimal(result["price_effect"]) == 19
    assert Decimal(result["fx_effect"]) == 10
    assert Decimal(result["attribution_fees"]) == 0
