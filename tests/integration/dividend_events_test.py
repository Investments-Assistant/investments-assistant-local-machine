"""Synthetic received dividends are income, not deposits or disposal PnL."""

from decimal import Decimal
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.execution.models import SimulatorPosition, AccountLedgerEvent, SimulatorInstrument
from src.execution.policy import PolicyDenied
from src.scheduler.reporter import _fallback_report
from src.execution.reporting import collect_execution_period
from src.execution.account_events import record_dividend_payment
from src.execution.reconciliation import reconcile_account
from tests.integration.simulator_sales_test import owned

pytestmark = pytest.mark.integration


async def dividend(session, ids, **overrides):
    args = dict(
        user_id=ids[0],
        account_id=ids[1],
        instrument_id=ids[2],
        allocation_id="manual",
        event_key="dividend",
        gross_base="10",
        withholding_base="2.5",
        currency="EUR",
        effective_at=datetime.now(UTC),
        source_reference="synthetic-dividend-payment",
        fixture_event=True,
    )
    return await record_dividend_payment(session, **(args | overrides))


async def test_payment_is_attributed_income_and_net_cash_without_basis_change(db_session):
    ids, account, _ = await owned(db_session)
    at = datetime.now(UTC)
    receipt = await dividend(db_session, ids, effective_at=at)
    assert (await dividend(db_session, ids, effective_at=at))["deduplicated"]
    await db_session.flush()
    await db_session.refresh(account)
    checked = await reconcile_account(db_session, account, _include_execution_evidence=True)
    assert checked["status"] == "consistent" and Decimal(checked["net_external_flows"]) == 0
    assert Decimal(checked["dividend_gross"]) == 10 and Decimal(checked["dividend_withholding"]) == Decimal("2.5")
    assert account.cash == Decimal("807.5") and account.realized_pnl == 0
    position = await db_session.scalar(select(SimulatorPosition).where(SimulatorPosition.account_id == ids[1]))
    assert position.quantity == 2 and position.cost_basis == 200
    assert checked["reconciled_dividends"][0]["event_id"] == receipt["event_id"]
    report = await collect_execution_period(
        db_session, user_id=ids[0], start=at - timedelta(seconds=1), end=datetime.now(UTC)
    )
    row = report["accounts"][0]
    assert Decimal(row["dividend_net"]) == Decimal("7.5") and Decimal(row["attributed_fees"]) == 0
    rendered = _fallback_report(
        {"period": {"start": at.date().isoformat(), "end": at.date().isoformat()}, "simulator_execution_period": report}
    )
    assert "Dividend cash" in rendered and receipt["event_id"] in rendered


@pytest.mark.parametrize(
    "change,code",
    [
        ({"withholding_base": "11"}, "INVALID_DIVIDEND_AMOUNT"),
        ({"gross_base": "NaN"}, "INVALID_DIVIDEND_AMOUNT"),
        ({"gross_base": "0.00000000001"}, "INVALID_DIVIDEND_AMOUNT"),
        ({"currency": "USD"}, "DIVIDEND_CURRENCY_MISMATCH"),
        ({"allocation_id": "other-strategy"}, "DIVIDEND_OWNERSHIP_UNVERIFIED"),
        ({"fixture_event": False}, "SIMULATOR_EVENT_REQUIRED"),
    ],
)
async def test_invalid_or_unowned_payment_does_not_change_cash(db_session, change, code):
    ids, account, _ = await owned(db_session)
    with pytest.raises(PolicyDenied, match=code):
        await dividend(db_session, ids, **change)
    assert account.cash == 800
    assert not (
        await db_session.scalars(select(AccountLedgerEvent).where(AccountLedgerEvent.account_id == ids[1]))
    ).all()


async def test_protected_income_halts_consumption_and_conflicting_receipts_fail(db_session):
    ids, account, _ = await owned(db_session)
    quote = await db_session.get(SimulatorInstrument, ids[2])
    quote.protected = True
    await dividend(db_session, ids)
    assert account.halted and account.halt_reason == "PROTECTED_INCOME_REVIEW_REQUIRED"
    with pytest.raises(PolicyDenied, match="CONFLICTING_ACCOUNT_EVENT"):
        await dividend(db_session, ids, gross_base="12")
    assert account.cash == Decimal("807.5")


async def test_payment_survives_late_fee_and_report_interval_excludes_other_receipts(db_session):
    from src.execution.commissions import record_commission
    from tests.integration.commissions_test import callback

    ids, account, buy = await owned(db_session)
    at = datetime.now(UTC)
    receipt = await dividend(db_session, ids, effective_at=at)
    await record_commission(
        db_session, **callback(ids, buy["order_id"], datetime.now(UTC), execution_id="buy", amount="0.20")
    )
    await db_session.refresh(account)
    assert account.cash == Decimal("807.30") and account.realized_pnl == 0
    assert (await reconcile_account(db_session, account))["status"] == "consistent"
    event = await db_session.get(AccountLedgerEvent, receipt["event_id"])
    # Half-open booking-time boundary; economic payment time does not move booking.
    report = await collect_execution_period(
        db_session, user_id=ids[0], start=at - timedelta(days=1), end=event.observed_at
    )
    assert report["accounts"][0]["dividend_count"] == 0
    event.payload = dict(event.payload, gross_base="11")
    await db_session.flush()
    checked = await reconcile_account(db_session, account)
    assert checked["status"] == "unverified" and checked["dividend_gross"] is None
