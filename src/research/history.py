"""Bounded public historical adapter with explicit currency and exchange sessions.

Yahoo/yfinance data is research input, not broker-qualified execution evidence.
Unknown exchange/currency/FX fails closed. Provider split-adjusted share units are
retained and disclosed; split events must not be applied a second time.
"""

from decimal import Decimal
from datetime import UTC, time, datetime, timedelta

import pandas as pd
import yfinance as yf
import exchange_calendars as calendars

from src.research.replay import Bar

CALENDARS = {
    "NMS": "XNAS",
    "NGM": "XNAS",
    "NCM": "XNAS",
    "NYQ": "XNYS",
    "PCX": "XNYS",
    "GER": "XETR",
    "LSE": "XLON",
    "PAR": "XPAR",
}


def load_history(symbols: list[str], start: str, end: str, base_currency: str):
    start_at, end_at = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if not start_at < end_at or (end_at - start_at).days > 3653:
        raise ValueError("Research interval must be increasing and at most10 years")
    if not 1 <= len(symbols) <= 20 or len(set(symbols)) != len(symbols):
        raise ValueError("Provide 1..20 unique provider symbols")
    if base_currency not in {"USD", "EUR", "GBP"}:
        raise ValueError("Choose an explicit supported base currency: USD, EUR or GBP")
    series, sources, fx_cache = {}, {}, {}
    for symbol in symbols:
        ticker = yf.Ticker(symbol)
        frame = ticker.history(
            start=start,
            end=end,
            auto_adjust=False,
            back_adjust=False,
            actions=True,
            repair=False,
            timeout=10,
            raise_errors=True,
        )
        metadata = ticker.history_metadata
        currency = metadata.get("currency")
        exchange = metadata.get("exchangeName")
        calendar_name = CALENDARS.get(exchange)
        if not currency or not calendar_name or frame.empty:
            raise ValueError("Historical currency, supported exchange or prices unavailable")
        unit = Decimal(".01") if currency == "GBp" else Decimal(1)
        currency = "GBP" if currency == "GBp" else currency
        calendar = calendars.get_calendar(calendar_name, start=start, end=end)
        schedule = calendar.schedule
        fx_rows = None
        if currency != base_currency:
            pair = currency + base_currency + "=X"
            if pair not in fx_cache:
                fx_start = (start_at - timedelta(days=10)).date().isoformat()
                fx_frame = yf.Ticker(pair).history(
                    start=fx_start, end=end, auto_adjust=False, timeout=10, raise_errors=True
                )
                if fx_frame.empty:
                    raise ValueError("Dated historical FX unavailable")
                fx_cache[pair] = [
                    (
                        datetime.combine(index.date() + timedelta(days=1), time.min, UTC),
                        Decimal(str(row["Close"])),
                    )
                    for index, row in fx_frame.iterrows()
                ]
            fx_rows = fx_cache[pair]
        bars = []
        for index, row in frame.iterrows():
            date = pd.Timestamp(index.date())
            if date not in schedule.index:
                raise ValueError("Provider bar does not match the verified exchange calendar")
            market = schedule.loc[date]
            opened, closed = market["open"].to_pydatetime(), market["close"].to_pydatetime()
            fx, fx_at = Decimal(1), opened
            if fx_rows is not None:
                known = [(at, rate) for at, rate in fx_rows if at <= opened]
                if not known:
                    raise ValueError("FX was not available before the simulated open")
                fx_at, fx = max(known, key=lambda item: item[0])
            bars.append(
                Bar(
                    symbol=symbol,
                    open_at=opened,
                    close_at=closed,
                    open=Decimal(str(row["Open"])) * unit,
                    close=Decimal(str(row["Close"])) * unit,
                    volume=Decimal(str(row["Volume"])),
                    currency=currency,
                    fx_to_base=fx,
                    fx_as_of=fx_at,
                    dividend=Decimal(str(row.get("Dividends", 0))) * unit,
                )
            )
        series[symbol] = bars
        sources[symbol] = dict(
            provider="yfinance/Yahoo",
            exchange=exchange,
            calendar=calendar_name,
            source_currency=metadata.get("currency"),
            valuation_currency=currency,
            minor_unit_factor=str(unit),
            first_session=bars[0].open_at.isoformat(),
            last_session=bars[-1].close_at.isoformat(),
            price_basis="provider split-adjusted share units; split events not applied twice",
            split_events=int((frame.get("Stock Splits", pd.Series(dtype=float)) > 0).sum()),
        )
    return series, dict(
        provider_version=yf.__version__,
        calendar_version=calendars.__version__,
        retrieved_at=datetime.now(UTC).isoformat(),
        instruments=sources,
        limitations=[
            "Provider revision and delisting completeness unverified",
            "Historical provider availability latency not observed",
            "FX daily closes conservatively available at next UTC midnight",
            "Vendor corporate-action adjustments require independent reconciliation",
        ],
    )
