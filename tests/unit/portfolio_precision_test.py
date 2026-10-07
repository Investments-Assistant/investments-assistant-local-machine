"""Authoritative totals retain small balances next to large source values."""

import json
from decimal import Decimal

from src.tools import portfolio
from src.finance.answers import portfolio_facts
from src.finance.normalization import usd_decimal_value
from src.tools.broker_accounts import BrokerAccountConfig


def test_exact_aggregate_survives_float_cancellation_and_json_roundtrip(monkeypatch):
    rows = [
        {'currency': 'USD', 'market_value': '100000000000000000000', 'unrealized_pnl': '0.01'},
        {'currency': 'USD', 'market_value': '0.01', 'unrealized_pnl': '0.02'},
        {'currency': 'USD', 'market_value': '-100000000000000000000', 'unrealized_pnl': '-0.01'},
    ]
    monkeypatch.setattr(portfolio, '_BROKER_FUNNELS', [
        ('ibkr', lambda account: rows, lambda account: {'currency': 'USD'})
    ])
    account = BrokerAccountConfig('fixture', 'owner', 'ibkr', 'Fixture', {})
    result = portfolio.get_portfolio_summary(accounts=[account])
    assert Decimal(result['total_market_value_usd_exact']) == Decimal('0.01')
    assert Decimal(result['total_unrealized_pnl_usd_exact']) == Decimal('0.02')
    result['total_market_value_usd'] = 0.0  # Compatibility display field is not authoritative.
    facts = portfolio_facts(json.dumps(result))
    assert facts['reported_total_market_value_usd'] == '0.01'


def test_fx_conversion_preserves_sub_float_precision_and_requires_dated_rate():
    data = {'currency': 'EUR', 'fx_to_usd': '1.00000000000000000001',
            'fx_as_of': '2026-09-24T00:00:00Z'}
    assert usd_decimal_value('1', data) == Decimal('1.00000000000000000001')
    assert usd_decimal_value('1', data | {'fx_as_of': None}) is None
    assert usd_decimal_value('1', data | {'currency': None}) is None


def test_missing_fx_invalidates_both_exact_and_display_totals(monkeypatch):
    monkeypatch.setattr(portfolio, '_BROKER_FUNNELS', [
        ('ibkr', lambda account: [{'currency': 'EUR', 'market_value': '100', 'unrealized_pnl': '1'}],
         lambda account: {'currency': 'EUR'})
    ])
    result = portfolio.get_portfolio_summary(accounts=[BrokerAccountConfig('fixture', 'owner', 'ibkr', 'Fixture', {})])
    assert result['valuation_status'] == 'partial'
    assert result['total_market_value_usd_exact'] is None
    assert result['total_market_value_usd'] is None
    assert result['total_unrealized_pnl_usd_exact'] is None
