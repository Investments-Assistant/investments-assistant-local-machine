from decimal import Decimal as D
from datetime import UTC, datetime, timedelta
from dataclasses import replace

import pytest

from src.research.replay import Bar, Costs, NewsEvidence, replay

pytestmark = pytest.mark.unit
FREE = Costs(
    commission_bps=D(0),
    minimum_commission=D(0),
    spread_bps=D(0),
    slippage_bps=D(0),
    fx_bps=D(0),
    volume_participation=D(1),
    lot=D(".001"),
)


def bars(values):
    result = []
    for i, value in enumerate(values):
        opening = datetime(2026, 1, 1, 9, tzinfo=UTC) + timedelta(days=i)
        result.append(
            Bar(
                "FIXTURE",
                opening,
                opening + timedelta(hours=8),
                D(str(value)),
                D(str(value)),
                D(10000),
                "EUR",
                D(1),
                opening,
            )
        )
    return result


def run(data, **kwargs):
    return replay(
        data,
        capital=D(100),
        base_currency="EUR",
        source_version="fixture-v1",
        fixture=kwargs.pop("fixture", True),
        costs=kwargs.pop("costs", FREE),
        **kwargs,
    )


def test_signal_cannot_fill_its_own_bar_and_no_invented_terminal_sale():
    data = bars([100, 110, 120, 130, 200])
    result = run(data, strategy="momentum", lookback=2)
    assert result["trade_count"] == 1
    trade = result["trades"][0]
    assert trade["signal_at"] == data[2].close_at.isoformat()
    assert trade["filled_at"] == data[3].open_at.isoformat()
    assert D(result["final_value"]) == D("153.83")
    assert D(result["realized_pnl"]) == 0
    assert D(result["unrealized_pnl"]) > 0


def test_known_costs_reduce_equity_and_cash_cannot_go_negative():
    data = bars([100, 100, 100, 100])
    no_cost = run(data, strategy="buy_and_hold")
    costly = run(
        data,
        strategy="buy_and_hold",
        costs=replace(FREE, commission_bps=D(10), minimum_commission=D(1), spread_bps=D(10)),
    )
    assert D(costly["final_value"]) < D(no_cost["final_value"])
    assert D(costly["fees"]) == D(1)
    assert D(costly["cash"]) >= 0
    assert costly["total_return_pct"] < 0


def test_volume_partial_fill_and_no_stale_residual_replay():
    data = bars([100, 100, 100])
    data[1] = replace(data[1], volume=D(".2"))
    result = run(data, strategy="buy_and_hold")
    assert result["trade_count"] == 1 and result["trades"][0]["status"] == "partial_expired"
    assert D(result["quantity"]) == D(".2")


def test_split_and_dividend_conserve_wealth_with_explicit_cash_flow():
    data = bars([100, 100, 50])
    data[2] = replace(data[2], split=D(2), dividend=D(1))
    result = run(data, strategy="buy_and_hold")
    assert D(result["quantity"]) == 2
    assert D(result["dividends"]) == 2
    assert D(result["final_value"]) == 102
    assert D(result["unrealized_pnl"]) == 0


def test_late_available_news_and_syndication_do_not_create_early_signal():
    data = bars([100, 110, 120, 130, 140])
    article = NewsEvidence(
        "same-content",
        "FIXTURE",
        data[0].close_at,
        data[-1].close_at + timedelta(days=1),
        D(1),
        "fixture",
        "fixture-model-v1",
    )
    result = run(data, strategy="momentum_news", lookback=2, news=[article, article])
    assert result["trade_count"] == 0 and D(result["final_value"]) == 100
    early = replace(article, available_at=data[2].close_at)
    result = run(data, strategy="momentum_news", lookback=2, news=[early, early])
    assert result["trades"][0]["source_ids"] == ["same-content"]
    assert result["trades"][0]["signal_at"] == data[2].close_at.isoformat()
    assert result["conventions"]["news_score_timing"].startswith("legacy synthetic fixture:")


def timed_article(data, score_available_at):
    return NewsEvidence(
        "timed-content", "FIXTURE", data[0].close_at,
        data[2].close_at - timedelta(hours=1), D(1), "synthetic-fixture",
        "synthetic-score-not-an-LLM", score_available_at=score_available_at,
    )


@pytest.mark.parametrize("fixture", [False, True])
def test_score_ready_after_next_open_cannot_create_an_earlier_signal_or_fill(fixture):
    data = bars([100, 110, 120, 130, 140])
    article = timed_article(data, data[3].open_at + timedelta(hours=1))
    result = run(data, strategy="momentum_news", lookback=2, news=[article], fixture=fixture)
    assert result["trade_count"] == 1
    trade = result["trades"][0]
    assert trade["signal_at"] == data[3].close_at.isoformat()
    assert trade["filled_at"] == data[4].open_at.isoformat()
    assert {"at": data[2].close_at.isoformat(), "reason": "NEWS_ABSTENTION"} in result["rejected"]
    assert result["conventions"]["news_score_timing"].startswith("explicit score availability")


@pytest.mark.parametrize("offset_microseconds, signal_index", [(-1, 2), (0, 2), (1, 3)])
def test_score_availability_uses_the_exact_decision_boundary(offset_microseconds, signal_index):
    data = bars([100, 110, 120, 130, 140])
    article = timed_article(data, data[2].close_at + timedelta(microseconds=offset_microseconds))
    result = run(data, strategy="momentum_news", lookback=2, news=[article], fixture=False)
    assert result["trades"][0]["signal_at"] == data[signal_index].close_at.isoformat()
    assert result["trades"][0]["filled_at"] == data[signal_index + 1].open_at.isoformat()


def test_real_news_rejects_missing_score_time_but_empty_news_can_abstain():
    data = bars([100, 110, 120, 130, 140])
    with pytest.raises(ValueError, match="explicit score availability"):
        run(data, strategy="momentum_news", lookback=2, news=[timed_article(data, None)], fixture=False)
    result = run(data, strategy="momentum_news", lookback=2, news=[], fixture=False)
    assert result["trade_count"] == 0
    assert result["conventions"]["news_score_timing"] == "no supplied news scores"


@pytest.mark.parametrize("fixture", [False, True])
@pytest.mark.parametrize("invalid_time", ["naive", "before_news", "not_datetime"])
def test_invalid_explicit_score_times_are_rejected_even_for_fixtures(fixture, invalid_time):
    data = bars([100, 110, 120, 130, 140])
    available_at = data[2].close_at - timedelta(hours=1)
    score_at = {
        "naive": available_at.replace(tzinfo=None),
        "before_news": available_at - timedelta(microseconds=1),
        "not_datetime": available_at.isoformat(),
    }[invalid_time]
    with pytest.raises(ValueError, match="Score availability must be timezone-aware"):
        run(data, strategy="momentum_news", lookback=2,
            news=[timed_article(data, score_at)], fixture=fixture)


def test_score_time_equal_to_news_time_is_valid_and_changes_are_hashed():
    data = bars([100, 110, 120, 130, 140])
    article = timed_article(data, data[2].close_at - timedelta(hours=1))
    first = run(data, strategy="momentum_news", lookback=2, news=[article], fixture=False)
    same = run(data, strategy="momentum_news", lookback=2, news=[article], fixture=False)
    later = run(data, strategy="momentum_news", lookback=2,
                news=[replace(article, score_available_at=article.score_available_at + timedelta(seconds=1))],
                fixture=False)
    assert first["trades"] == later["trades"]
    assert first["input_hash"] == same["input_hash"]
    assert first["input_hash"] != later["input_hash"]


def test_late_score_does_not_refresh_the_existing_news_age_limit():
    data = bars([100, 110, 120, 130, 140, 150, 160])
    article = timed_article(data, data[5].close_at)
    result = run(data, strategy="momentum_news", lookback=2, news=[article], fixture=False)
    assert result["trade_count"] == 0


def test_stale_or_future_fx_and_input_fingerprints():
    data = bars([100, 110, 120])
    bad = list(data)
    bad[1] = replace(bad[1], fx_as_of=bad[1].open_at + timedelta(seconds=1))
    with pytest.raises(ValueError, match="FX unavailable"):
        run(bad, strategy="buy_and_hold")
    bad[1] = replace(data[1], fx_as_of=data[1].open_at - timedelta(days=3))
    result = run(bad, strategy="buy_and_hold")
    assert result["trade_count"] == 0 and result["valuation_status"] == "partial"
    first = run(data, strategy="buy_and_hold")
    assert first["input_hash"] == run(data, strategy="buy_and_hold")["input_hash"]
    assert first["input_hash"] != run(data, strategy="cash")["input_hash"]
