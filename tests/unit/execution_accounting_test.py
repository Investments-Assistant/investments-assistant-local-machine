from decimal import Decimal, localcontext
from dataclasses import replace

import pytest

from src.execution.accounting import AccountingFill, replay_fills


def fill(sequence, side, quantity, principal, fee="0", allocation="manual", instrument="fixture"):
    return AccountingFill(str(sequence), sequence, instrument, allocation, side,
                          Decimal(quantity), Decimal(principal), Decimal(fee))


def test_partial_and_final_sale_release_exact_basis_and_conserve_capital():
    rows = [fill(1, "buy", "3", "100", "0.01"), fill(2, "sell", "1", "40", "0.02"),
            fill(3, "sell", "2", "90", "0.03")]
    with localcontext() as context:
        context.prec = 6  # Caller decimal context must not corrupt accounting.
        result = replay_fills(Decimal(1000), list(reversed(rows)))
    assert result.positions["manual", "fixture"].quantity == 0
    assert result.positions["manual", "fixture"].cost_basis == 0
    assert result.realized_pnl == Decimal("29.94")
    assert result.cash == Decimal("1029.94")
    assert sum(d.released_basis for d in result.disposals) == Decimal("100.01")


def test_late_purchase_and_sale_fees_reallocate_realized_and_retained_basis():
    original = [fill(1, "buy", "2", "200"), fill(2, "sell", "1", "150")]
    first = replay_fills(Decimal(1000), original)
    revised = replay_fills(Decimal(1000), [replace(original[0], fee_base=Decimal(2)),
                                          replace(original[1], fee_base=Decimal(3))])
    assert first.realized_pnl == 50 and first.positions["manual", "fixture"].cost_basis == 100
    assert revised.realized_pnl == 46 and revised.positions["manual", "fixture"].cost_basis == 101
    assert revised.cash == 945
    assert original[0].fee_base == original[1].fee_base == 0


def test_one_allocation_cannot_sell_another_allocations_position():
    rows = [fill(1, "buy", "2", "200", allocation="long-term"),
            fill(2, "sell", "1", "100", allocation="experiment")]
    with pytest.raises(ValueError, match="ACCOUNTING_UNOWNED_SALE"):
        replay_fills(Decimal(1000), rows)


def test_rebuy_and_weighted_basis_are_order_sensitive():
    rows = [fill(1, "buy", "2", "200"), fill(2, "sell", "1", "150"),
            fill(3, "buy", "1", "200"), fill(4, "sell", "1", "170")]
    result = replay_fills(Decimal(1000), rows)
    assert result.realized_pnl == 70
    assert result.positions["manual", "fixture"].quantity == 1
    assert result.positions["manual", "fixture"].cost_basis == 150
    assert result.cash == 920


@pytest.mark.parametrize("change", [
    {"sequence": 0}, {"sequence": True}, {"side": "short"}, {"allocation_id": ""},
    {"quantity": Decimal("NaN")}, {"fee_base": Decimal("-1")},
    {"principal_base": Decimal("0.00000000001")},
])
def test_invalid_accounting_evidence_is_rejected(change):
    with pytest.raises(ValueError):
        replay_fills(Decimal(1000), [replace(fill(1, "buy", "1", "100"), **change)])


def test_duplicate_execution_or_sequence_requires_reconciliation():
    first = fill(1, "buy", "1", "100")
    for second in (first, replace(first, execution_id="other"), replace(first, sequence=2)):
        with pytest.raises(ValueError, match="ACCOUNTING_AMBIGUOUS_EXECUTION_ORDER"):
            replay_fills(Decimal(1000), [first, second])


def test_execution_policy_rejects_extra_precision_without_altering_caller_context():
    from decimal import ROUND_UP

    from src.execution.policy import PolicyDenied, positive
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_UP
        assert positive('12345678.0000000001') == Decimal('12345678.0000000001')
        with pytest.raises(PolicyDenied, match='UNSUPPORTED_PRECISION'):
            positive('1.00000000001')
        assert context.prec == 6 and context.rounding == ROUND_UP
