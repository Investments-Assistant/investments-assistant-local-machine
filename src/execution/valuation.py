"""Observed simulator valuation evidence and exact-boundary period accounting.

Missing historical boundaries stay unavailable. Capturing a current quote never
backdates it to satisfy a report. Fees are already included in cash and basis.
"""

from decimal import Decimal
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from src.execution.models import (
    ExecutionEvent,
    SimulatorOrder,
    ValuationSnapshot,
    AccountLedgerEvent,
    SimulatorInstrument,
)
from src.execution.policy import PolicyDenied, digest, positive
from src.execution.numeric import execution_precision
from src.execution.service import account_for_user
from src.execution.reconciliation import reconcile_account
from src.execution.valuation_attribution import attribute, execution_totals

MAX_SNAPSHOTS = 10000
MAX_POSITIONS = 1000


def evidence(row):
    return dict(
        account_id=row.account_id,
        user_id=row.user_id,
        snapshot_key=row.snapshot_key,
        as_of=row.as_of.isoformat(),
        payload=row.payload,
    )


def validate(row, account):
    if (
        row.account_id != account.id
        or row.user_id != account.user_id
        or digest(evidence(row)) != row.evidence_hash
        or row.payload.get("currency") != account.currency
        or row.payload.get("environment") != "simulator"
    ):
        raise PolicyDenied("VALUATION_EVIDENCE_INVALID")


def receipt(row):
    return dict(snapshot_id=row.id, as_of=row.as_of.isoformat(), evidence_sha256=row.evidence_hash)


@execution_precision
async def capture_valuation(session, *, user_id, account_id, snapshot_key):
    account = await account_for_user(session, account_id, user_id)
    if account.mandate.get("environment") != "simulator":
        raise PolicyDenied("SIMULATOR_EVENT_REQUIRED")
    if not isinstance(snapshot_key, str) or not 1 <= len(snapshot_key) <= 128:
        raise PolicyDenied("INVALID_VALUATION_KEY")
    old = await session.scalar(
        select(ValuationSnapshot).where(
            ValuationSnapshot.account_id == account_id, ValuationSnapshot.snapshot_key == snapshot_key
        )
    )
    if old:
        validate(old, account)
        return receipt(old)
    if (
        await session.scalar(
            select(func.count()).select_from(ValuationSnapshot).where(ValuationSnapshot.account_id == account_id)
        )
        >= MAX_SNAPSHOTS
    ):
        raise PolicyDenied("VALUATION_CAPACITY")
    checked, ledger = await reconcile_account(session, account, _include_ledger=True, _include_execution_evidence=True)
    if checked["status"] != "consistent" or ledger is None:
        raise PolicyDenied("LEDGER_NOT_RECONCILED")
    held = [(key, position) for key, position in ledger.positions.items() if position.quantity]
    if len(held) > MAX_POSITIONS:
        raise PolicyDenied("VALUATION_POSITION_CAPACITY")
    instrument_ids = {key[1] for key, _ in held} | {
        row["instrument_id"] for row in checked["reconciled_executions"]
    }
    quotes = (
        await session.scalars(
            select(SimulatorInstrument).where(
                SimulatorInstrument.account_id == account_id, SimulatorInstrument.id.in_(instrument_ids)
            )
        )
    ).all()
    quotes = {quote.id: quote for quote in quotes}
    at = datetime.now(UTC)
    latest_fill = await session.scalar(
        select(func.max(ExecutionEvent.observed_at))
        .join(SimulatorOrder, SimulatorOrder.id == ExecutionEvent.order_id)
        .where(SimulatorOrder.account_id == account_id)
    )
    latest_event = await session.scalar(
        select(func.max(AccountLedgerEvent.observed_at)).where(AccountLedgerEvent.account_id == account_id)
    )
    if any(stamp is not None and stamp >= at for stamp in (latest_fill, latest_event)):
        raise PolicyDenied("VALUATION_CLOCK_REGRESSION")
    latest = await session.scalar(
        select(func.max(ValuationSnapshot.as_of)).where(ValuationSnapshot.account_id == account_id)
    )
    if latest is not None and at <= latest:
        raise PolicyDenied("VALUATION_CLOCK_REGRESSION")
    rows = []
    for (allocation, instrument_id), position in sorted(held):
        quote = quotes.get(instrument_id)
        if quote is None or quote.as_of > at or at - quote.as_of > timedelta(seconds=60):
            raise PolicyDenied("VALUATION_STALE")
        price, multiplier, fx = positive(quote.price), positive(quote.multiplier), positive(quote.fx_to_base)
        if not quote.currency or (quote.currency == account.currency and fx != 1):
            raise PolicyDenied("VALUATION_FX_UNAVAILABLE")
        market_value = position.quantity * price * multiplier * fx
        rows.append(
            dict(
                allocation_id=allocation,
                instrument_id=instrument_id,
                quantity=str(position.quantity),
                cost_basis=str(position.cost_basis),
                price=str(price),
                multiplier=str(multiplier),
                source_currency=quote.currency,
                fx_to_base=str(fx),
                quote_and_fx_as_of=quote.as_of.isoformat(),
                market_value=str(market_value),
                unrealized=str(market_value - position.cost_basis),
                protected=quote.protected,
            )
        )
    value = sum((Decimal(row["market_value"]) for row in rows), Decimal(0))
    basis = sum((Decimal(row["cost_basis"]) for row in rows), Decimal(0))
    allocations = {}
    for allocation in sorted(set(ledger.realized_by_allocation) | set(ledger.dividend_gross_by_allocation)
                              | set(ledger.dividend_receivables_by_allocation)):
        allocations[allocation] = dict(
            realized=str(ledger.realized_by_allocation.get(allocation, Decimal(0))),
            unrealized=str(
                sum((Decimal(row["unrealized"]) for row in rows if row["allocation_id"] == allocation), Decimal(0))
            ),
            dividend_gross=str(ledger.dividend_gross_by_allocation.get(allocation, Decimal(0))),
            dividend_withholding=str(ledger.dividend_withholding_by_allocation.get(allocation, Decimal(0))),
            dividend_receivable=str(ledger.dividend_receivables_by_allocation.get(allocation, Decimal(0))),
        )
    fx_marks = {}
    for instrument_id, quote in quotes.items():
        if not quote.currency or quote.as_of > at or at - quote.as_of > timedelta(seconds=60):
            continue
        try:
            rate = positive(quote.fx_to_base)
        except PolicyDenied:
            continue
        if quote.currency == account.currency and rate != 1:
            continue
        fx_marks[instrument_id] = dict(source_currency=quote.currency, fx_to_base=str(rate),
                                       as_of=quote.as_of.isoformat())
    payload = dict(
        allocations=allocations,
        schema=3,
        execution_totals=execution_totals(checked["reconciled_executions"]),
        fx_marks=fx_marks,
        environment="simulator",
        currency=account.currency,
        initial_capital=str(account.initial_capital),
        cash=str(ledger.cash),
        equity=str(ledger.cash + value + ledger.dividend_receivable),
        market_value=str(value),
        cost_basis=str(basis),
        unrealized=str(value - basis),
        realized=str(ledger.realized_pnl),
        net_external_flows=str(ledger.net_external_flows),
        dividend_gross=checked["dividend_gross"],
        dividend_withholding=checked["dividend_withholding"],
        dividend_receivable=str(ledger.dividend_receivable),
        fees=str(sum((Decimal(row["fee_base"]) for row in checked["reconciled_executions"]), Decimal(0))),
        positions=rows,
        reconciliation_sha256=checked["evidence_sha256"],
        accounting_basis="Observed current knowledge; later fee revisions affect later observations",
    )
    row = ValuationSnapshot(
        account_id=account_id, user_id=user_id, snapshot_key=snapshot_key, as_of=at, payload=payload
    )
    row.evidence_hash = digest(evidence(row))
    session.add(row)
    await session.flush()
    return receipt(row)


@execution_precision
async def period_performance(session, *, user_id, account_id, start, end):
    account = await account_for_user(session, account_id, user_id)
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise PolicyDenied("INVALID_VALUATION_PERIOD")
    rows = (
        await session.scalars(
            select(ValuationSnapshot)
            .where(ValuationSnapshot.account_id == account_id, ValuationSnapshot.as_of.in_([start, end]))
            .limit(3)
        )
    ).all()
    result = dict(
        status="unavailable",
        portfolio_pnl=None,
        reason="EXACT_PERIOD_MARKS_UNAVAILABLE",
        start=start.isoformat(),
        end_exclusive=end.isoformat(),
        currency=account.currency,
        fx_effect=None,
        benchmark_return=None,
        limitations=[
            "Benchmark evidence unavailable",
            "Observed snapshot changes include subsequently booked fee corrections",
        ],
    )
    if len(rows) != 2 or {row.as_of for row in rows} != {start, end}:
        return result
    rows.sort(key=lambda row: row.as_of)
    for row in rows:
        validate(row, account)
    opening, closing = (row.payload for row in rows)
    if Decimal(opening["initial_capital"]) != Decimal(closing["initial_capital"]):
        raise PolicyDenied("VALUATION_CAPITAL_BASIS_CHANGED")

    def change(field):
        return Decimal(closing[field]) - Decimal(opening[field])

    flows, realized, unrealized = change("net_external_flows"), change("realized"), change("unrealized")
    cash_income = change("dividend_gross") - change("dividend_withholding")
    receivable_change = (Decimal(closing.get("dividend_receivable", "0"))
                         - Decimal(opening.get("dividend_receivable", "0")))
    income = cash_income + receivable_change
    pnl = change("equity") - flows
    if pnl != realized + unrealized + income:
        raise PolicyDenied("VALUATION_PNL_NOT_RECONCILED")
    allocation_results = []
    for allocation in sorted(set(opening["allocations"]) | set(closing["allocations"])):
        first, last = opening["allocations"].get(allocation, {}), closing["allocations"].get(allocation, {})
        deltas = {
            field: Decimal(last.get(field, "0")) - Decimal(first.get(field, "0"))
            for field in ("realized", "unrealized", "dividend_gross", "dividend_withholding", "dividend_receivable")
        }
        allocation_results.append(
            dict(
                allocation_id=allocation,
                portfolio_pnl=str(
                    deltas["realized"]
                    + deltas["unrealized"]
                    + deltas["dividend_gross"]
                    - deltas["dividend_withholding"]
                    + deltas["dividend_receivable"]
                ),
                **{key: str(value) for key, value in deltas.items()},
            )
        )
    if sum((Decimal(row["portfolio_pnl"]) for row in allocation_results), Decimal(0)) != pnl:
        raise PolicyDenied("VALUATION_ALLOCATION_MISMATCH")
    result.update(
        allocations=allocation_results,
        status="complete",
        reason=None,
        portfolio_pnl=str(pnl),
        opening=receipt(rows[0]),
        closing=receipt(rows[1]),
        net_external_flows=str(flows),
        realized_change=str(realized),
        unrealized_change=str(unrealized),
        dividend_net=str(income),
        dividend_cash_net=str(cash_income),
        dividend_receivable_change=str(receivable_change),
        fees_change=str(change("fees")),
        fee_basis="Included in PnL; never subtract again",
        opening_equity=opening["equity"],
        closing_equity=closing["equity"],
    )
    result.update(attribute(opening, closing, pnl=pnl))
    if result["fx_attribution_status"] != "complete":
        result["limitations"].append("Separate FX attribution unavailable: " + result["fx_attribution_reason"])
    result["evidence_sha256"] = digest(result)
    return result
