"""Persisted synthetic entitlement, risk, snapshot and report accounting."""

from decimal import Decimal
from datetime import UTC, datetime, timedelta

import pytest

from src.execution.risk import enforce_account_risk
from src.execution.models import ValuationSnapshot, AccountLedgerEvent, SimulatorInstrument
from src.execution.policy import PolicyDenied
from src.scheduler.reporter import _fallback_report
from src.execution.reporting import collect_execution_period
from src.execution.valuation import capture_valuation, period_performance
from src.execution.reconciliation import reconcile_account
from src.execution.dividend_receipts import record_dividend_settlement, record_dividend_entitlement
from tests.integration.simulator_sales_test import owned

pytestmark = pytest.mark.integration


async def earn(session, ids, **changes):
    args = dict(user_id=ids[0], account_id=ids[1], instrument_id=ids[2], allocation_id="manual",
        event_key="earned", action_id="fixture-issuer-action", eligible_quantity="2", gross_base="10",
        withholding_base="2.5", currency="EUR", effective_at=datetime.now(UTC),
        source_reference="synthetic-dated-eligibility", fixture_event=True)
    return await record_dividend_entitlement(session, **(args | changes))


async def pay(session, ids, entitlement_id, **changes):
    args = dict(user_id=ids[0], account_id=ids[1], entitlement_id=entitlement_id, event_key="paid",
                effective_at=datetime.now(UTC), source_reference="synthetic-received-payment", fixture_event=True)
    return await record_dividend_settlement(session, **(args | changes))


async def test_unpaid_income_is_not_cash_and_settlement_is_not_double_income(db_session):
    ids, account, _ = await owned(db_session)
    scope = dict(user_id=ids[0], account_id=ids[1])
    start = await capture_valuation(db_session, **scope, snapshot_key="before")
    at = datetime.now(UTC)
    earned = await earn(db_session, ids, effective_at=at)
    assert (await earn(db_session, ids, effective_at=at))["deduplicated"]
    assert account.cash == 800
    checked = await reconcile_account(db_session, account)
    assert checked["status"] == "consistent" and Decimal(checked["dividend_receivable"]) == Decimal("7.5")
    assert Decimal(checked["dividend_gross"]) == 0
    await enforce_account_risk(db_session, account)
    assert Decimal(account.mandate["account_risk"]["dividend_receivable"]) == Decimal("7.5")
    middle = await capture_valuation(db_session, **scope, snapshot_key="unpaid")
    unpaid = await period_performance(db_session, **scope, start=datetime.fromisoformat(start["as_of"]),
                                      end=datetime.fromisoformat(middle["as_of"]))
    assert Decimal(unpaid["portfolio_pnl"]) == Decimal("7.5")
    assert Decimal(unpaid["dividend_cash_net"]) == 0 and Decimal(unpaid["attribution_income"]) == Decimal("7.5")
    paid_at = datetime.now(UTC)
    await pay(db_session, ids, earned["event_id"], effective_at=paid_at)
    assert (await pay(db_session, ids, earned["event_id"], effective_at=paid_at))["deduplicated"]
    assert account.cash == Decimal("807.5")
    checked = await reconcile_account(db_session, account)
    assert checked["status"] == "consistent" and Decimal(checked["dividend_receivable"]) == 0
    finish = await capture_valuation(db_session, **scope, snapshot_key="paid")
    paid = await period_performance(db_session, **scope, start=datetime.fromisoformat(middle["as_of"]),
                                    end=datetime.fromisoformat(finish["as_of"]))
    assert Decimal(paid["portfolio_pnl"]) == Decimal(paid["attribution_income"]) == 0
    assert Decimal(paid["dividend_cash_net"]) == Decimal("7.5")
    assert Decimal(paid["dividend_receivable_change"]) == Decimal("-7.5")
    immutable = await db_session.get(ValuationSnapshot, middle["snapshot_id"])
    assert immutable.payload["schema"] == 3 and Decimal(immutable.payload["dividend_receivable"]) == Decimal("7.5")
    report = await collect_execution_period(db_session, user_id=ids[0],
        start=datetime.fromisoformat(start["as_of"]), end=datetime.fromisoformat(finish["as_of"]))
    row = report["accounts"][0]
    assert row["dividend_entitlement_count"] == row["dividend_count"] == 1
    assert Decimal(row["dividend_accrual_net"]) == Decimal(row["dividend_net"]) == Decimal("7.5")
    rendered = _fallback_report({"period": {"start": at.date().isoformat(), "end": at.date().isoformat()},
                                 "simulator_execution_period": report})
    assert "Unpaid receivables are not spendable cash" in rendered and earned["event_id"] in rendered
    assert "Observed period portfolio P&L" in rendered and "it is unavailable here" not in rendered
    later = await collect_execution_period(db_session, user_id=ids[0],
        start=datetime.fromisoformat(middle["as_of"]), end=datetime.fromisoformat(finish["as_of"]))
    assert Decimal(later["accounts"][0]["dividend_accrual_net"]) == 0


@pytest.mark.parametrize("changes,code", [
    ({"eligible_quantity": "3"}, "DIVIDEND_ELIGIBILITY_UNVERIFIED"),
    ({"allocation_id": "unowned"}, "DIVIDEND_ELIGIBILITY_UNVERIFIED"),
    ({"gross_base": "NaN"}, "INVALID_DIVIDEND_AMOUNT"),
    ({"currency": "USD"}, "DIVIDEND_CURRENCY_MISMATCH"),
    ({"fixture_event": False}, "SIMULATOR_EVENT_REQUIRED"),
    ({"effective_at": datetime(2020, 1, 1, tzinfo=UTC)}, "HISTORICAL_DIVIDEND_ELIGIBILITY_UNAVAILABLE"),
])
async def test_eligibility_is_explicit_scoped_and_not_inferred_from_current_holdings(db_session, changes, code):
    ids, account, _ = await owned(db_session)
    with pytest.raises(PolicyDenied, match=code):
        await earn(db_session, ids, **changes)
    assert account.cash == 800 and (await reconcile_account(db_session, account))["dividend_receivable"] == "0"


async def test_conflicts_duplicate_actions_and_repeated_settlement_do_not_create_cash(db_session):
    from tests.integration.dividend_events_test import dividend

    ids, account, _ = await owned(db_session)
    at = datetime.now(UTC)
    earned = await earn(db_session, ids, effective_at=at)
    with pytest.raises(PolicyDenied, match="DIVIDEND_ENTITLEMENT_LINK_REQUIRED"):
        await dividend(db_session, ids)
    with pytest.raises(PolicyDenied, match="CONFLICTING_ACCOUNT_EVENT"):
        await earn(db_session, ids, effective_at=at, gross_base="11")
    with pytest.raises(PolicyDenied, match="DUPLICATE_DIVIDEND_ACTION"):
        await earn(db_session, ids, event_key="another-key")
    with pytest.raises(PolicyDenied, match="DIVIDEND_PAYMENT_BEFORE_ENTITLEMENT"):
        await pay(db_session, ids, earned["event_id"], effective_at=at-timedelta(seconds=1))
    await pay(db_session, ids, earned["event_id"])
    with pytest.raises(PolicyDenied, match="DIVIDEND_ENTITLEMENT_LINK_REQUIRED"):
        await dividend(db_session, ids)
    with pytest.raises(PolicyDenied, match="DIVIDEND_ENTITLEMENT_NOT_OUTSTANDING"):
        await pay(db_session, ids, earned["event_id"], event_key="second-payment")
    assert account.cash == Decimal("807.5")


async def test_protected_entitlement_preserves_operator_halt_and_tamper_is_unavailable(db_session):
    ids, account, _ = await owned(db_session)
    instrument = await db_session.get(SimulatorInstrument, ids[2])
    instrument.protected = True
    account.halted, account.halt_reason = True, "OPERATOR_INCIDENT"
    earned = await earn(db_session, ids)
    assert account.halt_reason == "OPERATOR_INCIDENT" and account.cash == 800
    row = await db_session.get(AccountLedgerEvent, earned["event_id"])
    row.payload = dict(row.payload, gross_base="99")
    await db_session.flush()
    assert (await reconcile_account(db_session, account))["status"] == "unverified"
    with pytest.raises(PolicyDenied, match="DIVIDEND_ENTITLEMENT_UNAVAILABLE"):
        await pay(db_session, ids, earned["event_id"])


async def test_concurrent_receipts_and_payments_commit_only_once(integration_engine):
    import asyncio

    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.db.models import User
    from src.execution.models import ExecutionEvent, SimulatorOrder, SimulatorAccount, SimulatorPosition

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        ids, _, _ = await owned(session)
    at = datetime.now(UTC)

    async def receipt():
        async with factory.begin() as session:
            return await earn(session, ids, effective_at=at)

    try:
        receipts = await asyncio.gather(receipt(), receipt())
        assert sorted(row["deduplicated"] for row in receipts) == [False, True]
        earned_id = receipts[0]["event_id"]
        paid_at = datetime.now(UTC)

        async def payment():
            async with factory.begin() as session:
                return await pay(session, ids, earned_id, effective_at=paid_at)

        payments = await asyncio.gather(payment(), payment())
        assert sorted(row["deduplicated"] for row in payments) == [False, True]
        async with factory.begin() as session:
            account = await session.get(SimulatorAccount, ids[1])
            assert account.cash == Decimal("807.5")
            result = await reconcile_account(session, account)
            assert result["status"] == "consistent" and result["dividend_receivable"] == "0"
            with pytest.raises(PolicyDenied, match="DIVIDEND_ENTITLEMENT_NOT_OUTSTANDING"):
                await pay(session, ids, earned_id, event_key="restart-retry")
    finally:
        async with factory.begin() as session:
            orders = select(SimulatorOrder.id).where(SimulatorOrder.account_id == ids[1])
            await session.execute(delete(ExecutionEvent).where(ExecutionEvent.order_id.in_(orders)))
            for model in (AccountLedgerEvent, SimulatorOrder, SimulatorPosition, SimulatorInstrument):
                await session.execute(delete(model).where(model.account_id == ids[1]))
            await session.execute(delete(SimulatorAccount).where(SimulatorAccount.id == ids[1]))
            await session.execute(delete(User).where(User.id == ids[0]))


async def test_receivable_cannot_fund_order_or_cross_account_settlement(db_session):
    from src.execution.account_events import record_cash_flow
    from tests.integration.execution_test import proposal, confirmation

    ids, account, _ = await owned(db_session)
    other, _, _ = await owned(db_session)
    earned = await earn(db_session, ids)
    with pytest.raises(PolicyDenied, match="DIVIDEND_ENTITLEMENT_UNAVAILABLE"):
        await pay(db_session, other, earned["event_id"])
    with pytest.raises(PolicyDenied, match="ACCOUNT_NOT_OWNED"):
        await pay(db_session, ids, earned["event_id"], user_id=other[0])
    await record_cash_flow(db_session, user_id=ids[0], account_id=ids[1], event_key="withdraw-cash",
        amount_base="-800", currency="EUR", effective_at=datetime.now(UTC),
        source_reference="synthetic-withdrawal", fixture_event=True)
    assert account.cash == 0
    quote = await db_session.get(SimulatorInstrument, ids[2])
    quote.price, quote.as_of = Decimal(100), datetime.now(UTC)  # Match the helper's marketable limit.
    with pytest.raises(PolicyDenied, match="INSUFFICIENT_UNRESERVED_CASH"):
        proposed = await proposal(db_session, ids, quantity="0.004")
        await confirmation(db_session, ids, proposed)
    assert account.cash == 0 and account.reserved == 0
    assert Decimal((await reconcile_account(db_session, account))["dividend_receivable"]) == Decimal("7.5")
