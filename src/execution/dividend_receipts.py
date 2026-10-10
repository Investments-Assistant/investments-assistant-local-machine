"""Explicit dated synthetic entitlements and linked payments; no provider writes.

This internal fixture boundary accepts supplied eligibility evidence. It does not
derive exchange ex-dates, tax rates or historical holdings from current symbols.
"""

from decimal import Decimal, InvalidOperation
from datetime import UTC, datetime

from sqlalchemy import func, select

from src.execution.models import ExecutionEvent, SimulatorOrder, AccountLedgerEvent, SimulatorInstrument
from src.execution.policy import PolicyDenied, digest
from src.execution.numeric import execution_precision
from src.execution.service import account_for_user
from src.execution.accounting import amount
from src.execution.account_events import event_evidence
from src.execution.reconciliation import MAX_ROWS, reconcile_account


def evidence_fields(event_key, source_reference, effective_at):
    if (any(not isinstance(value, str) or not 1 <= len(value) <= 128 for value in (event_key, source_reference))
            or not isinstance(effective_at, datetime) or effective_at.tzinfo is None
            or effective_at > datetime.now(UTC)):
        raise PolicyDenied("INVALID_ACCOUNT_EVENT_EVIDENCE")


async def prior_receipt(session, event):
    event.evidence_hash = digest(event_evidence(event))
    old = await session.scalar(select(AccountLedgerEvent).where(
        AccountLedgerEvent.account_id == event.account_id, AccountLedgerEvent.event_key == event.event_key))
    if old:
        if old.evidence_hash != event.evidence_hash or digest(event_evidence(old)) != old.evidence_hash:
            raise PolicyDenied("CONFLICTING_ACCOUNT_EVENT")
        return dict(event_id=old.id, deduplicated=True, environment="simulator")


async def checked_ledger(session, account):
    checked, ledger = await reconcile_account(session, account, _include_ledger=True)
    if checked["status"] != "consistent" or ledger is None:
        raise PolicyDenied("LEDGER_NOT_RECONCILED")
    if checked["account_events_checked"] + checked["events_checked"] >= MAX_ROWS:
        raise PolicyDenied("ACCOUNT_EVENT_CAPACITY")
    return ledger


@execution_precision
async def record_dividend_entitlement(session, *, user_id, account_id, instrument_id, allocation_id,
        event_key, action_id, eligible_quantity, gross_base, withholding_base, currency, effective_at,
        source_reference, fixture_event=False):
    account = await account_for_user(session, account_id, user_id)
    if fixture_event is not True or account.mandate.get("environment") != "simulator":
        raise PolicyDenied("SIMULATOR_EVENT_REQUIRED")
    evidence_fields(event_key, source_reference, effective_at)
    if any(not isinstance(value, str) or not 1 <= len(value) <= 128 for value in (action_id, allocation_id)):
        raise PolicyDenied("INVALID_DIVIDEND_ELIGIBILITY")
    if currency != account.currency:
        raise PolicyDenied("DIVIDEND_CURRENCY_MISMATCH")
    try:
        quantity, gross, withholding = (amount(Decimal(str(value))) for value in
                                        (eligible_quantity, gross_base, withholding_base))
        if quantity <= 0 or gross <= 0 or withholding > gross:
            raise ValueError("Invalid entitlement")
    except (ValueError, InvalidOperation):
        raise PolicyDenied("INVALID_DIVIDEND_AMOUNT") from None
    instrument = await session.scalar(select(SimulatorInstrument).where(
        SimulatorInstrument.id == instrument_id, SimulatorInstrument.account_id == account_id))
    if instrument is None:
        raise PolicyDenied("INSTRUMENT_NOT_OWNED")
    event = AccountLedgerEvent(account_id=account_id, user_id=user_id, event_key=event_key,
        kind="dividend_entitlement", effective_at=effective_at.astimezone(UTC), payload=dict(
            environment="simulator", origin="synthetic_fixture_receipt", source_reference=source_reference,
            currency=currency, instrument_id=instrument_id, allocation_id=allocation_id, action_id=action_id,
            eligible_quantity=str(quantity.normalize()), gross_base=str(gross.normalize()),
            withholding_base=str(withholding.normalize())))
    old = await prior_receipt(session, event)
    if old:
        return old
    ledger = await checked_ledger(session, account)
    position = ledger.positions.get((allocation_id, instrument_id))
    if position is None or position.quantity != quantity:
        raise PolicyDenied("DIVIDEND_ELIGIBILITY_UNVERIFIED")
    latest_fill = await session.scalar(select(func.max(ExecutionEvent.observed_at)).join(
        SimulatorOrder, SimulatorOrder.id == ExecutionEvent.order_id).where(
            SimulatorOrder.account_id == account_id, SimulatorOrder.instrument_id == instrument_id,
            ExecutionEvent.kind == "fill"))
    latest_split = await session.scalar(select(func.max(AccountLedgerEvent.observed_at)).where(
        AccountLedgerEvent.account_id == account_id, AccountLedgerEvent.kind == "split",
        AccountLedgerEvent.payload["instrument_id"].as_string() == instrument_id))
    if any(stamp is not None and stamp >= effective_at for stamp in (latest_fill, latest_split)):
        raise PolicyDenied("HISTORICAL_DIVIDEND_ELIGIBILITY_UNAVAILABLE")
    duplicate = await session.scalar(select(AccountLedgerEvent.id).where(
        AccountLedgerEvent.account_id == account_id, AccountLedgerEvent.kind == "dividend_entitlement",
        AccountLedgerEvent.payload["action_id"].as_string() == action_id,
        AccountLedgerEvent.payload["allocation_id"].as_string() == allocation_id,
        AccountLedgerEvent.payload["instrument_id"].as_string() == instrument_id))
    if duplicate:
        raise PolicyDenied("DUPLICATE_DIVIDEND_ACTION")
    try:
        amount(ledger.dividend_receivable + gross - withholding)
    except ValueError:
        raise PolicyDenied("INVALID_DIVIDEND_AMOUNT") from None
    if instrument.protected and not account.halted:
        account.halted, account.halt_reason = True, "PROTECTED_INCOME_REVIEW_REQUIRED"
    session.add(event)
    await session.flush()
    return dict(event_id=event.id, deduplicated=False, environment="simulator")


@execution_precision
async def record_dividend_settlement(session, *, user_id, account_id, entitlement_id, event_key,
        effective_at, source_reference, fixture_event=False):
    account = await account_for_user(session, account_id, user_id)
    if fixture_event is not True or account.mandate.get("environment") != "simulator":
        raise PolicyDenied("SIMULATOR_EVENT_REQUIRED")
    evidence_fields(event_key, source_reference, effective_at)
    earned = await session.scalar(select(AccountLedgerEvent).where(
        AccountLedgerEvent.id == entitlement_id, AccountLedgerEvent.account_id == account_id,
        AccountLedgerEvent.user_id == user_id, AccountLedgerEvent.kind == "dividend_entitlement"))
    if earned is None or digest(event_evidence(earned)) != earned.evidence_hash:
        raise PolicyDenied("DIVIDEND_ENTITLEMENT_UNAVAILABLE")
    if effective_at < earned.effective_at:
        raise PolicyDenied("DIVIDEND_PAYMENT_BEFORE_ENTITLEMENT")
    event = AccountLedgerEvent(account_id=account_id, user_id=user_id, event_key=event_key,
        kind="dividend_settlement", effective_at=effective_at.astimezone(UTC), payload=dict(
            earned.payload, entitlement_id=entitlement_id, source_reference=source_reference))
    old = await prior_receipt(session, event)
    if old:
        return old
    ledger = await checked_ledger(session, account)
    pending = ledger.dividend_receivables.get(entitlement_id)
    if pending is None:
        raise PolicyDenied("DIVIDEND_ENTITLEMENT_NOT_OUTSTANDING")
    try:
        account.cash = amount(account.cash + pending.gross_base - pending.withholding_base, signed=True)
    except ValueError:
        raise PolicyDenied("INVALID_DIVIDEND_AMOUNT") from None
    session.add(event)
    await session.flush()
    return dict(event_id=event.id, deduplicated=False, environment="simulator")
