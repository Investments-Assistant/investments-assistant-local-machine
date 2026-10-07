"""Persisted split facts preserve ownership and never authorize trading."""

from decimal import Decimal
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.execution.models import SimulatorOrder, SimulatorPosition, AccountLedgerEvent, SimulatorInstrument
from src.execution.policy import PolicyDenied
from src.execution.commissions import record_commission
from src.execution.account_events import record_split
from src.execution.reconciliation import reconcile_account
from tests.integration.execution_test import seed
from tests.integration.commissions_test import callback
from tests.integration.simulator_sales_test import sell, owned

pytestmark = pytest.mark.integration


async def split(session, ids, **overrides):
    args = dict(
        user_id=ids[0],
        account_id=ids[1],
        instrument_id=ids[2],
        event_key="split",
        numerator=2,
        denominator=1,
        effective_at=datetime.now(UTC),
        source_reference="synthetic-split",
        fixture_event=True,
    )
    return await record_split(session, **(args | overrides))


async def test_persisted_split_preserves_basis_and_cash_and_requires_review(db_session):
    ids, account, buy = await owned(db_session)
    quote = await db_session.get(SimulatorInstrument, ids[2])
    quote.protected = True
    initial_mandate = dict(account.mandate)
    at = datetime.now(UTC)
    receipt = await split(db_session, ids, effective_at=at)
    again = await split(db_session, ids, effective_at=at)
    assert again["deduplicated"] and again["event_id"] == receipt["event_id"]
    await db_session.flush()
    db_session.expire_all()
    position = await db_session.scalar(select(SimulatorPosition).where(SimulatorPosition.account_id == ids[1]))
    from src.execution.models import SimulatorAccount

    account = await db_session.get(SimulatorAccount, ids[1])
    checked = await reconcile_account(db_session, account, _include_execution_evidence=True)
    assert checked["status"] == "consistent"
    assert position.quantity == 4 and position.cost_basis == 200
    assert account.cash == 800 and account.realized_pnl == 0
    assert account.halted and account.halt_reason == "CORPORATE_ACTION_REVIEW_REQUIRED"
    assert account.mandate == initial_mandate
    quote = await db_session.get(SimulatorInstrument, ids[2])
    assert quote.protected and at - quote.as_of > timedelta(seconds=60)
    assert checked["reconciled_corporate_actions"][0]["event_id"] == receipt["event_id"]
    assert not checked["reconciled_cash_flows"]
    assert checked["allocation_inventory"][0]["allocation_id"] == "manual"
    await record_commission(
        db_session, **callback(ids, buy["order_id"], datetime.now(UTC), execution_id="buy", amount="0.20")
    )
    checked = await reconcile_account(db_session, account)
    assert checked["status"] == "consistent"
    assert position.cost_basis == Decimal("200.20") and position.quantity == 4


async def test_pending_order_or_retroactive_split_is_rejected_without_changes(db_session):
    ids, account, _ = await owned(db_session)
    with pytest.raises(PolicyDenied, match="RETROACTIVE_CORPORATE_ACTION"):
        await split(db_session, ids, effective_at=datetime.now(UTC) - timedelta(days=1))
    proposed = await sell(db_session, ids)
    with pytest.raises(PolicyDenied, match="CORPORATE_ACTION_UNRESOLVED_ORDERS"):
        await split(db_session, ids)
    assert (await db_session.get(SimulatorOrder, proposed["order_id"])).status == "proposed"
    assert not (
        await db_session.scalars(select(AccountLedgerEvent).where(AccountLedgerEvent.account_id == ids[1]))
    ).all()
    assert account.cash == 800 and not account.halted


async def test_unrepresentable_split_scope_and_conflict_fail_closed(db_session):
    ids, account, _ = await owned(db_session)
    other = await seed(db_session)
    with pytest.raises(PolicyDenied, match="INSTRUMENT_NOT_OWNED"):
        await split(db_session, ids, instrument_id=other[2])
    with pytest.raises(PolicyDenied, match="ACCOUNTING_UNSUPPORTED_PRECISION"):
        await split(db_session, ids, numerator=1, denominator=3)
    assert not account.halted
    await split(db_session, ids)
    with pytest.raises(PolicyDenied, match="CONFLICTING_ACCOUNT_EVENT"):
        await split(db_session, ids, numerator=3)
    assert (await reconcile_account(db_session, account))["status"] == "consistent"


async def test_split_retains_operator_halt_and_period_report_provenance(db_session):
    from src.scheduler.reporter import _fallback_report
    from src.execution.reporting import collect_execution_period

    ids, account, _ = await owned(db_session)
    account.halted = True
    account.halt_reason = "OPERATOR_HALT"
    start = datetime.now(UTC)
    receipt = await split(db_session, ids, numerator=1, denominator=2)
    end = datetime.now(UTC)
    assert account.halt_reason == "OPERATOR_HALT"
    report = await collect_execution_period(db_session, user_id=ids[0], start=start, end=end)
    row = report["accounts"][0]
    assert row["corporate_action_count"] == 1
    assert row["corporate_actions"][0]["event_id"] == receipt["event_id"]
    assert Decimal(row["net_external_flows"]) == Decimal(row["realized_pnl"]) == 0
    rendered = _fallback_report(
        {"period": {"start": start.isoformat(), "end": end.isoformat()}, "simulator_execution_period": report}
    )
    assert receipt["event_id"] in rendered and "Synthetic split 1:2" in rendered
    assert report["portfolio_period_pnl"] is None
