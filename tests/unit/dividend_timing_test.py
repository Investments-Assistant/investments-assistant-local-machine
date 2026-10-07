"""Dividend entitlement is an asset, not spendable cash before payment evidence."""

from decimal import Decimal as D
from dataclasses import replace

import pytest

from src.research.portfolio import replay_portfolio
from tests.unit.research_replay_test import FREE, run, bars

pytestmark = pytest.mark.unit


def replay(data, engine):
    if engine == 'single':
        return run(data, strategy='buy_and_hold')
    return replay_portfolio({'FIXTURE': data}, capital=D(100), base_currency='EUR',
                            strategy='buy_and_hold', params={}, costs=FREE, source={'fixture': True})


@pytest.mark.parametrize('engine', ['single', 'portfolio'])
def test_unknown_payment_date_does_not_create_spendable_cash(engine):
    data = bars([100, 100, 98, 98])
    data[2] = replace(data[2], dividend=D(2))
    result = replay(data, engine)
    assert D(result['cash']) == 0
    assert D(result['dividend_receivable']) == 2
    assert D(result['dividends_paid']) == 0
    assert D(result['final_value']) == 100
    assert result['valuation_status'] == 'partial'


@pytest.mark.parametrize('engine', ['single', 'portfolio'])
def test_dividend_is_receivable_until_explicit_payment_and_is_not_counted_twice(engine):
    data = bars([100, 100, 98, 98])
    data[2] = replace(data[2], dividend=D(2), dividend_pay_at=data[3].close_at)
    before = replay(data[:3], engine)
    after = replay(data, engine)
    assert D(before['cash']) == 0 and D(before['dividend_receivable']) == 2
    assert D(after['cash']) == 2 and D(after['dividend_receivable']) == 0
    assert D(after['dividends_paid']) == D(after['dividends']) == 2
    assert D(before['final_value']) == D(after['final_value']) == 100
    assert before['valuation_status'] == after['valuation_status'] == 'complete'


@pytest.mark.parametrize('engine', ['single', 'portfolio'])
def test_foreign_dividend_payment_uses_dated_payment_fx_without_future_leakage(engine):
    data = [replace(bar, currency='USD') for bar in bars([100, 100, 98, 98])]
    data[2] = replace(data[2], dividend=D(2), dividend_pay_at=data[3].open_at,
                      dividend_payment_fx=D(2), dividend_payment_fx_as_of=data[3].open_at)
    data[3] = replace(data[3], fx_to_base=D(2))
    before, after = replay(data[:3], engine), replay(data, engine)
    assert D(before['cash']) == 0 and D(before['dividend_receivable']) == 2
    assert D(before['dividend_fx_pnl']) == 0
    assert D(after['cash']) == 4 and D(after['dividends_paid']) == 4
    assert D(after['dividends']) == 2 and D(after['dividend_fx_pnl']) == 2
    assert D(after['final_value']) == 200
    assert D(after['final_value']) == (100 + D(after['realized_pnl']) + D(after['unrealized_pnl'])
                                      + D(after['dividends']) + D(after['dividend_fx_pnl']))


@pytest.mark.parametrize('engine', ['single', 'portfolio'])
def test_later_split_does_not_multiply_an_already_earned_dividend(engine):
    data = bars([100, 100, 98, 49, 49])
    data[2] = replace(data[2], dividend=D(2), dividend_pay_at=data[4].open_at)
    data[3] = replace(data[3], split=D(2))
    result = replay(data, engine)
    assert D(result['dividends_paid']) == 2 and D(result['final_value']) == 100


@pytest.mark.parametrize('kind', ['missing_fx', 'future_fx', 'early_payment', 'naive_payment'])
def test_invalid_payment_evidence_cannot_become_cash(kind):
    from datetime import timedelta

    data = bars([100, 100, 98])
    ex = data[2]
    fields = dict(currency='USD', dividend=D(2), dividend_pay_at=ex.close_at,
                  dividend_payment_fx=D(1), dividend_payment_fx_as_of=ex.open_at)
    data = [replace(bar, currency='USD') for bar in data]
    if kind == 'missing_fx':
        fields['dividend_payment_fx'] = None
    elif kind == 'future_fx':
        fields['dividend_payment_fx_as_of'] = ex.close_at + timedelta(seconds=1)
    elif kind == 'early_payment':
        fields['dividend_pay_at'] = ex.open_at - timedelta(seconds=1)
    else:
        fields['dividend_pay_at'] = ex.close_at.replace(tzinfo=None)
    data[2] = replace(ex, **fields)
    with pytest.raises(ValueError, match='[Dd]ividend'):
        replay(data, 'single')



def test_saved_payment_evidence_reproduces_offline():
    from unittest.mock import patch

    from src.tools.simulator import run_simulation
    from scripts.replay_saved_evidence import reproduce

    data = bars([100, 100, 98, 98])
    data[2] = replace(data[2], dividend=D(2), dividend_pay_at=data[3].close_at)
    with patch('src.tools.simulator._download', return_value=({'FIXTURE': data}, {'fixture': True})):
        result = run_simulation('Dividend fixture', ['FIXTURE'], {'type': 'buy_and_hold', 'params': {}},
                                initial_capital=100, base_currency='EUR')
    evidence = result['strategy']['research']
    assert reproduce(evidence)['status'] == 'PASS'
    evidence['bars']['FIXTURE'][2]['dividend_pay_at'] = data[2].close_at.isoformat()
    with pytest.raises(ValueError, match='hash mismatch'):
        reproduce(evidence)
