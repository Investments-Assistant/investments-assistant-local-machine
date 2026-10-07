"""Trusted simulator fixture receipts; no broker or payment operation is performed.

Not exposed to models, MCP or a public route. Callers own the transaction. All
writes take the same active-owner account lock as orders and callbacks.
"""

from decimal import Decimal, InvalidOperation, localcontext
from datetime import UTC, datetime

from sqlalchemy import select

from src.execution.models import AccountLedgerEvent
from src.execution.policy import PolicyDenied, digest
from src.execution.service import account_for_user
from src.execution.accounting import amount


def event_evidence(event):
    return dict(
        account_id=event.account_id,
        user_id=event.user_id,
        event_key=event.event_key,
        kind=event.kind,
        payload=event.payload,
        effective_at=event.effective_at.isoformat(),
    )


async def record_cash_flow(
    session,
    *,
    user_id,
    account_id,
    event_key,
    amount_base,
    currency,
    effective_at,
    source_reference,
    fixture_event=False,
):
    account = await account_for_user(session, account_id, user_id)
    if fixture_event is not True or account.mandate.get("environment") != "simulator":
        raise PolicyDenied("SIMULATOR_EVENT_REQUIRED")
    if currency != account.currency:
        raise PolicyDenied("CASH_FLOW_CURRENCY_MISMATCH")
    if (
        not isinstance(event_key, str)
        or not 1 <= len(event_key) <= 128
        or not isinstance(source_reference, str)
        or not 1 <= len(source_reference) <= 128
        or not isinstance(effective_at, datetime)
        or effective_at.tzinfo is None
        or effective_at > datetime.now(UTC)
    ):
        raise PolicyDenied("INVALID_ACCOUNT_EVENT_EVIDENCE")
    with localcontext() as context:
        context.prec = 80
        try:
            value = amount(Decimal(str(amount_base)), signed=True)
            if not value:
                raise ValueError("zero")
        except (ValueError, InvalidOperation):
            raise PolicyDenied("INVALID_CASH_FLOW_AMOUNT") from None
        event = AccountLedgerEvent(
            account_id=account.id,
            user_id=user_id,
            event_key=event_key,
            kind="cash_flow",
            effective_at=effective_at.astimezone(UTC),
            payload=dict(
                environment="simulator",
                amount_base=str(value.normalize()),
                currency=currency,
                source_reference=source_reference,
                origin="synthetic_fixture_receipt",
            ),
        )
        event.evidence_hash = digest(event_evidence(event))
        old = await session.scalar(
            select(AccountLedgerEvent).where(
                AccountLedgerEvent.account_id == account_id, AccountLedgerEvent.event_key == event_key
            )
        )
        if old:
            if old.evidence_hash != event.evidence_hash or digest(event_evidence(old)) != old.evidence_hash:
                raise PolicyDenied("CONFLICTING_ACCOUNT_EVENT")
            return dict(event_id=old.id, deduplicated=True, environment="simulator")
        from src.execution.reconciliation import reconcile_account

        checked = await reconcile_account(session, account)
        if checked["status"] != "consistent":
            raise PolicyDenied("LEDGER_NOT_RECONCILED")
        if checked.get("account_events_checked", 0) >= 10000:
            raise PolicyDenied("ACCOUNT_EVENT_CAPACITY")
        if value < 0 and account.cash + value < account.reserved:
            raise PolicyDenied("INSUFFICIENT_UNRESERVED_CASH")
        try:
            new_cash = amount(account.cash + value, signed=True)
        except ValueError:
            raise PolicyDenied("INVALID_CASH_FLOW_AMOUNT") from None
        session.add(event)
        account.cash = new_cash
        await session.flush()
        return dict(event_id=event.id, deduplicated=False, environment="simulator")


async def record_split(
    session,
    *,
    user_id,
    account_id,
    instrument_id,
    event_key,
    numerator,
    denominator,
    effective_at,
    source_reference,
    fixture_event=False,
):
    """Apply a current synthetic split fact; invalidate quotes and halt for review.

    Historical restatement and unresolved order adjustments require separate
    evidence and are refused. Existing operator halts are never cleared/replaced.
    """
    from datetime import timedelta

    from sqlalchemy import func

    from src.execution.models import ExecutionEvent, SimulatorOrder, SimulatorPosition, SimulatorInstrument
    from src.execution.reconciliation import MAX_ROWS, reconcile_account

    account = await account_for_user(session, account_id, user_id)
    if fixture_event is not True or account.mandate.get("environment") != "simulator":
        raise PolicyDenied("SIMULATOR_EVENT_REQUIRED")
    if (
        not isinstance(event_key, str)
        or not 1 <= len(event_key) <= 128
        or not isinstance(source_reference, str)
        or not 1 <= len(source_reference) <= 128
        or not isinstance(effective_at, datetime)
        or effective_at.tzinfo is None
        or effective_at > datetime.now(UTC)
        or any(type(n) is not int or not 0 < n <= 10**9 for n in (numerator, denominator))
    ):
        raise PolicyDenied("INVALID_CORPORATE_ACTION_EVIDENCE")
    instrument = await session.scalar(
        select(SimulatorInstrument).where(
            SimulatorInstrument.id == instrument_id, SimulatorInstrument.account_id == account_id
        )
    )
    if instrument is None:
        raise PolicyDenied("INSTRUMENT_NOT_OWNED")
    event = AccountLedgerEvent(
        account_id=account_id,
        user_id=user_id,
        event_key=event_key,
        kind="split",
        effective_at=effective_at.astimezone(UTC),
        payload=dict(
            environment="simulator",
            instrument_id=instrument_id,
            numerator=numerator,
            denominator=denominator,
            currency=account.currency,
            source_reference=source_reference,
            origin="synthetic_fixture_receipt",
        ),
    )
    event.evidence_hash = digest(event_evidence(event))
    old = await session.scalar(
        select(AccountLedgerEvent).where(
            AccountLedgerEvent.account_id == account_id, AccountLedgerEvent.event_key == event_key
        )
    )
    if old:
        if old.evidence_hash != event.evidence_hash or digest(event_evidence(old)) != old.evidence_hash:
            raise PolicyDenied("CONFLICTING_ACCOUNT_EVENT")
        return dict(event_id=old.id, deduplicated=True, environment="simulator")
    unresolved = await session.scalar(
        select(SimulatorOrder.id)
        .where(
            SimulatorOrder.account_id == account_id,
            SimulatorOrder.instrument_id == instrument_id,
            SimulatorOrder.status != "filled",
        )
        .limit(1)
    )
    if unresolved:
        raise PolicyDenied("CORPORATE_ACTION_UNRESOLVED_ORDERS")
    latest_fill = await session.scalar(
        select(func.max(ExecutionEvent.observed_at))
        .join(SimulatorOrder, SimulatorOrder.id == ExecutionEvent.order_id)
        .where(
            SimulatorOrder.account_id == account_id,
            SimulatorOrder.instrument_id == instrument_id,
            ExecutionEvent.kind == "fill",
        )
    )
    latest_action = await session.scalar(
        select(func.max(AccountLedgerEvent.effective_at)).where(
            AccountLedgerEvent.account_id == account_id,
            AccountLedgerEvent.kind == "split",
            AccountLedgerEvent.payload["instrument_id"].as_string() == instrument_id,
        )
    )
    if any(stamp is not None and effective_at < stamp for stamp in (latest_fill, latest_action)):
        raise PolicyDenied("RETROACTIVE_CORPORATE_ACTION")
    checked, ledger = await reconcile_account(session, account, _include_ledger=True)
    if checked["status"] != "consistent" or ledger is None:
        raise PolicyDenied("LEDGER_NOT_RECONCILED")
    if checked["account_events_checked"] + checked["events_checked"] >= MAX_ROWS:
        raise PolicyDenied("ACCOUNT_EVENT_CAPACITY")
    with localcontext() as context:
        context.prec = 80
        try:
            quantities = [
                amount(position.quantity * numerator / denominator)
                for (_, identity), position in ledger.positions.items()
                if identity == instrument_id
            ]
            quantity = amount(sum(quantities, Decimal(0)))
        except (ValueError, InvalidOperation) as exc:
            raise PolicyDenied(str(exc)) from None
        position = await session.scalar(
            select(SimulatorPosition).where(
                SimulatorPosition.account_id == account_id, SimulatorPosition.instrument_id == instrument_id
            )
        )
        if position is None or position.quantity <= 0:
            raise PolicyDenied("CORPORATE_ACTION_POSITION_UNAVAILABLE")
        position.quantity = quantity
        instrument.as_of = min(instrument.as_of, effective_at - timedelta(seconds=61))
        if not account.halted:
            account.halted = True
            account.halt_reason = "CORPORATE_ACTION_REVIEW_REQUIRED"
        session.add(event)
        await session.flush()
        return dict(event_id=event.id, deduplicated=False, environment="simulator", review_required=True)


async def record_dividend_payment(
    session,
    *,
    user_id,
    account_id,
    instrument_id,
    allocation_id,
    event_key,
    gross_base,
    withholding_base,
    currency,
    effective_at,
    source_reference,
    fixture_event=False,
):
    """Record a synthetic received payment, not an inferred ex-date entitlement."""
    from src.execution.models import SimulatorInstrument
    from src.execution.reconciliation import MAX_ROWS, reconcile_account

    account = await account_for_user(session, account_id, user_id)
    if fixture_event is not True or account.mandate.get("environment") != "simulator":
        raise PolicyDenied("SIMULATOR_EVENT_REQUIRED")
    if currency != account.currency:
        raise PolicyDenied("DIVIDEND_CURRENCY_MISMATCH")
    if (
        not isinstance(event_key, str)
        or not 1 <= len(event_key) <= 128
        or not isinstance(source_reference, str)
        or not 1 <= len(source_reference) <= 128
        or not isinstance(allocation_id, str)
        or not 1 <= len(allocation_id) <= 128
        or not isinstance(effective_at, datetime)
        or effective_at.tzinfo is None
        or effective_at > datetime.now(UTC)
    ):
        raise PolicyDenied("INVALID_ACCOUNT_EVENT_EVIDENCE")
    instrument = await session.scalar(
        select(SimulatorInstrument).where(
            SimulatorInstrument.id == instrument_id, SimulatorInstrument.account_id == account_id
        )
    )
    if instrument is None:
        raise PolicyDenied("INSTRUMENT_NOT_OWNED")
    with localcontext() as context:
        context.prec = 80
        try:
            gross = amount(Decimal(str(gross_base)))
            withholding = amount(Decimal(str(withholding_base)))
            if gross <= 0 or withholding > gross:
                raise ValueError("invalid payment")
            new_cash = amount(account.cash + gross - withholding, signed=True)
        except (ValueError, InvalidOperation):
            raise PolicyDenied("INVALID_DIVIDEND_AMOUNT") from None
        event = AccountLedgerEvent(
            account_id=account_id,
            user_id=user_id,
            event_key=event_key,
            kind="dividend_payment",
            effective_at=effective_at.astimezone(UTC),
            payload=dict(
                environment="simulator",
                instrument_id=instrument_id,
                allocation_id=allocation_id,
                gross_base=str(gross.normalize()),
                withholding_base=str(withholding.normalize()),
                currency=currency,
                source_reference=source_reference,
                origin="synthetic_fixture_receipt",
            ),
        )
        event.evidence_hash = digest(event_evidence(event))
        old = await session.scalar(
            select(AccountLedgerEvent).where(
                AccountLedgerEvent.account_id == account_id, AccountLedgerEvent.event_key == event_key
            )
        )
        if old:
            if old.evidence_hash != event.evidence_hash or digest(event_evidence(old)) != old.evidence_hash:
                raise PolicyDenied("CONFLICTING_ACCOUNT_EVENT")
            return dict(event_id=old.id, deduplicated=True, environment="simulator")
        checked, ledger = await reconcile_account(session, account, _include_ledger=True)
        if checked["status"] != "consistent" or ledger is None:
            raise PolicyDenied("LEDGER_NOT_RECONCILED")
        if checked["account_events_checked"] + checked["events_checked"] >= MAX_ROWS:
            raise PolicyDenied("ACCOUNT_EVENT_CAPACITY")
        if (allocation_id, instrument_id) not in ledger.positions:
            raise PolicyDenied("DIVIDEND_OWNERSHIP_UNVERIFIED")
        # Keep protected receipts unavailable to experiment consumption pending review.
        if instrument.protected and not account.halted:
            account.halted = True
            account.halt_reason = "PROTECTED_INCOME_REVIEW_REQUIRED"
        account.cash = new_cash
        session.add(event)
        await session.flush()
        return dict(event_id=event.id, deduplicated=False, environment="simulator")
