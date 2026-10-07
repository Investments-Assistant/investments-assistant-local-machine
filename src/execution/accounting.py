"""Deterministic allocation-scoped weighted-average accounting in base currency.

Inputs are validated fill evidence in a caller-established economic order, with
latest absolute fees already resolved. Replaying corrected fees reallocates costs
between realized results and retained basis without altering original fills.
This calculator does not authorize or submit orders.
"""

from decimal import ROUND_DOWN, Decimal, localcontext
from dataclasses import field, dataclass

SCALE = Decimal("0.0000000001")
LIMIT = Decimal("1e18")


@dataclass(frozen=True)
class AccountingFill:
    execution_id: str
    sequence: int
    instrument_id: str
    allocation_id: str
    side: str
    quantity: Decimal
    principal_base: Decimal
    fee_base: Decimal


@dataclass(frozen=True)
class AccountingCashFlow:
    event_id: str
    sequence: int
    amount_base: Decimal  # Signed external cash movement; never trading PnL.


@dataclass(frozen=True)
class AccountingSplit:
    event_id: str
    sequence: int
    instrument_id: str
    numerator: int  # New shares per denominator old shares.
    denominator: int


@dataclass(frozen=True)
class AccountingDividendPayment:
    event_id: str
    sequence: int
    instrument_id: str
    allocation_id: str
    gross_base: Decimal
    withholding_base: Decimal


@dataclass(frozen=True)
class PositionBalance:
    quantity: Decimal = Decimal(0)
    cost_basis: Decimal = Decimal(0)


@dataclass(frozen=True)
class Disposal:
    execution_id: str
    released_basis: Decimal
    realized_pnl: Decimal


@dataclass(frozen=True)
class LedgerBalance:
    cash: Decimal
    positions: dict[tuple[str, str], PositionBalance]
    realized_by_allocation: dict[str, Decimal]
    disposals: tuple[Disposal, ...]
    net_external_flows: Decimal = Decimal(0)

    dividend_gross_by_allocation: dict[str, Decimal] = field(default_factory=dict)
    dividend_withholding_by_allocation: dict[str, Decimal] = field(default_factory=dict)

    @property
    def realized_pnl(self):
        with localcontext() as context:
            context.prec = 80
            return sum(self.realized_by_allocation.values(), Decimal(0))


def amount(value, *, signed=False):
    if not isinstance(value, Decimal) or not value.is_finite() or abs(value) >= LIMIT:
        raise ValueError("ACCOUNTING_INVALID_AMOUNT")
    if not signed and value < 0:
        raise ValueError("ACCOUNTING_NEGATIVE_AMOUNT")
    if value != value.quantize(SCALE):
        raise ValueError("ACCOUNTING_UNSUPPORTED_PRECISION")
    return value


def replay_fills(initial_cash: Decimal, fills: list[AccountingFill]) -> LedgerBalance:
    return replay_events(initial_cash, fills)


def replay_events(
    initial_cash: Decimal,
    events: list[AccountingFill | AccountingCashFlow | AccountingSplit | AccountingDividendPayment],
) -> LedgerBalance:
    """Replay ordered observed evidence, without authorizing any cash movement.

    Splits preserve each allocation's complete basis. Nonrepresentable fractions
    require separate evidence; no rounding or invented cash-in-lieu is allowed.
    """
    if len(events) > 10000:
        raise ValueError("ACCOUNTING_CAPACITY")
    with localcontext() as context:
        context.prec = 80
        cash = amount(initial_cash)
        sequences, identities = set(), set()
        for fill in events:
            if not isinstance(fill, (AccountingFill, AccountingCashFlow, AccountingSplit, AccountingDividendPayment)):
                raise ValueError("ACCOUNTING_UNSUPPORTED_EVENT")
            identity = fill.execution_id if isinstance(fill, AccountingFill) else fill.event_id
            if (
                type(fill.sequence) is not int
                or fill.sequence < 1
                or fill.sequence in sequences
                or not isinstance(identity, str)
                or not identity
                or identity in identities
            ):
                raise ValueError("ACCOUNTING_AMBIGUOUS_EXECUTION_ORDER")
            sequences.add(fill.sequence)
            identities.add(identity)
            if isinstance(fill, AccountingDividendPayment):
                if not fill.instrument_id or not fill.allocation_id:
                    raise ValueError("ACCOUNTING_INVALID_DIVIDEND_IDENTITY")
                if amount(fill.gross_base) <= 0 or amount(fill.withholding_base) > fill.gross_base:
                    raise ValueError("ACCOUNTING_INVALID_DIVIDEND_AMOUNT")
                continue
            if isinstance(fill, AccountingCashFlow):
                if amount(fill.amount_base, signed=True) == 0:
                    raise ValueError("ACCOUNTING_ZERO_CASH_FLOW")
                continue
            if isinstance(fill, AccountingSplit):
                if not fill.instrument_id or any(
                    type(n) is not int or not 0 < n <= 10**9 for n in (fill.numerator, fill.denominator)
                ):
                    raise ValueError("ACCOUNTING_INVALID_SPLIT")
                continue
            if not fill.instrument_id or not fill.allocation_id or fill.side not in {"buy", "sell"}:
                raise ValueError("ACCOUNTING_INVALID_IDENTITY_OR_SIDE")
            if amount(fill.quantity) <= 0 or amount(fill.principal_base) <= 0:
                raise ValueError("ACCOUNTING_NONPOSITIVE_FILL")
            amount(fill.fee_base)
        positions, realized, disposals = {}, {}, []
        net_flows = Decimal(0)
        gross, withholding = {}, {}
        for fill in sorted(events, key=lambda row: row.sequence):
            if isinstance(fill, AccountingDividendPayment):
                if (fill.allocation_id, fill.instrument_id) not in positions:
                    raise ValueError("DIVIDEND_OWNERSHIP_UNVERIFIED")
                cash = amount(cash + fill.gross_base - fill.withholding_base, signed=True)
                gross[fill.allocation_id] = amount(gross.get(fill.allocation_id, Decimal(0)) + fill.gross_base)
                withholding[fill.allocation_id] = amount(
                    withholding.get(fill.allocation_id, Decimal(0)) + fill.withholding_base
                )
                continue
            if isinstance(fill, AccountingCashFlow):
                cash = amount(cash + fill.amount_base, signed=True)
                net_flows = amount(net_flows + fill.amount_base, signed=True)
                continue
            if isinstance(fill, AccountingSplit):
                for key, position in list(positions.items()):
                    if key[1] == fill.instrument_id:
                        quantity = amount(position.quantity * fill.numerator / fill.denominator)
                        positions[key] = PositionBalance(quantity, position.cost_basis)
                continue
            key = fill.allocation_id, fill.instrument_id
            position = positions.get(key, PositionBalance())
            realized.setdefault(fill.allocation_id, Decimal(0))
            if fill.side == "buy":
                cost = fill.principal_base + fill.fee_base
                cash -= cost
                position = PositionBalance(position.quantity + fill.quantity, position.cost_basis + cost)
            else:
                if fill.quantity > position.quantity:
                    raise ValueError("ACCOUNTING_UNOWNED_SALE")
                # Partial disposal retains rounding dust in basis; final sale
                # releases the exact residual so a closed position has zero basis.
                basis = (
                    position.cost_basis
                    if fill.quantity == position.quantity
                    else (position.cost_basis * fill.quantity / position.quantity).quantize(SCALE, rounding=ROUND_DOWN)
                )
                proceeds = fill.principal_base - fill.fee_base
                pnl = proceeds - basis
                cash += proceeds
                realized[fill.allocation_id] += pnl
                disposals.append(Disposal(fill.execution_id, basis, pnl))
                position = PositionBalance(position.quantity - fill.quantity, position.cost_basis - basis)
            amount(cash, signed=True)  # Discrepant fills can produce a recorded deficit.
            amount(position.quantity)
            amount(position.cost_basis)
            amount(realized[fill.allocation_id], signed=True)
            positions[key] = position
        return LedgerBalance(cash, positions, realized, tuple(disposals), net_flows, gross, withholding)
