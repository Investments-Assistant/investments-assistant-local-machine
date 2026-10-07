"""Cost assumptions must never imply a nonpositive executable sale price."""

from decimal import Decimal as D
from dataclasses import replace

import pytest

from src.research.portfolio import replay_portfolio
from tests.unit.research_replay_test import FREE, run, bars

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("engine", ["single", "portfolio"])
@pytest.mark.parametrize("spread,slippage", [("10000", "5000"), ("10000", "10000"), ("0", "10000")])
def test_combined_execution_impact_must_leave_a_positive_sale_price(engine, spread, slippage):
    costs = replace(FREE, spread_bps=D(spread), slippage_bps=D(slippage))
    data = bars([100, 100, 100])
    with pytest.raises(ValueError, match="Combined execution impact"):
        if engine == "single":
            run(data, strategy="buy_and_hold", costs=costs)
        else:
            replay_portfolio({"FIXTURE": data}, capital=D(100), base_currency="EUR",
                             strategy="buy_and_hold", params={}, costs=costs, source={"fixture": True})



def test_positive_price_boundary_is_valid_but_does_not_create_leverage():
    costs = replace(FREE, spread_bps=D("10000"), slippage_bps=D("4999.999"))
    result = run(bars([100, 100, 100]), strategy="buy_and_hold", costs=costs)
    assert D(result["cash"]) >= 0 and D(result["quantity"]) >= 0
    assert all(D(trade["price_in_base"]) > 0 for trade in result["trades"])
