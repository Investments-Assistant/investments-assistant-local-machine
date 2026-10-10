"""Exact closing-rate price/FX decomposition from immutable boundary evidence."""

from decimal import Decimal

from src.execution.policy import PolicyDenied
from src.execution.numeric import execution_precision


@execution_precision
def execution_totals(executions):
    totals = {}
    for row in executions:
        key = row["allocation_id"], row["instrument_id"]
        item = totals.setdefault(key, dict(allocation_id=key[0], instrument_id=key[1],
                                          source_currency=row["source_currency"],
                                          net_source=Decimal(0), net_base=Decimal(0), fees=Decimal(0)))
        if item["source_currency"] != row["source_currency"]:
            raise PolicyDenied("VALUATION_INSTRUMENT_CURRENCY_CHANGED")
        sign = 1 if row["side"] == "buy" else -1
        item["net_source"] += sign * Decimal(row["principal_source"])
        item["net_base"] += sign * Decimal(row["principal_base"])
        item["fees"] += Decimal(row["fee_base"])
    return [{key: str(value) if isinstance(value, Decimal) else value for key, value in row.items()}
            for _, row in sorted(totals.items())]


@execution_precision
def attribute(opening, closing, *, pnl):
    unavailable = dict(fx_attribution_status="unavailable", fx_effect=None, price_effect=None)
    if any("execution_totals" not in row or "fx_marks" not in row for row in (opening, closing)):
        return unavailable | {"fx_attribution_reason": "ATTRIBUTION_HISTORY_UNAVAILABLE"}

    def indexed(rows):
        return {(row["allocation_id"], row["instrument_id"]): row for row in rows}

    first, last = indexed(opening["positions"]), indexed(closing["positions"])
    buys0, buys1 = indexed(opening["execution_totals"]), indexed(closing["execution_totals"])
    price_total, fx_total, fee_total = Decimal(0), Decimal(0), Decimal(0)
    by_allocation = {}
    for allocation, instrument in sorted(first.keys() | last.keys() | buys0.keys() | buys1.keys()):
        key = allocation, instrument
        p0, p1, b0, b1 = (mapping.get(key, {}) for mapping in (first, last, buys0, buys1))
        currencies = {item["source_currency"] for item in (p0, p1, b0, b1) if item}
        if len(currencies) != 1:
            return unavailable | {"fx_attribution_reason": "INSTRUMENT_CURRENCY_CHANGED"}
        def source_value(position):
            return (Decimal(position["quantity"]) * Decimal(position["price"]) * Decimal(position["multiplier"])
                    if position else Decimal(0))

        source0, source1 = source_value(p0), source_value(p1)
        purchases_source = Decimal(b1.get("net_source", "0")) - Decimal(b0.get("net_source", "0"))
        purchases_base = Decimal(b1.get("net_base", "0")) - Decimal(b0.get("net_base", "0"))
        fees = Decimal(b1.get("fees", "0")) - Decimal(b0.get("fees", "0"))
        currency = currencies.pop()
        if currency == closing["currency"] or not (source0 or source1 or purchases_source or purchases_base):
            rate = Decimal(1)
        else:
            mark = closing["fx_marks"].get(instrument)
            if not mark or mark["source_currency"] != currency:
                return unavailable | {"fx_attribution_reason": "CLOSING_FX_MARK_UNAVAILABLE"}
            rate = Decimal(mark["fx_to_base"])

        price = (source1 - source0 - purchases_source) * rate
        fx = (source0 + purchases_source) * rate - Decimal(p0.get("market_value", "0")) - purchases_base
        price_total += price
        fx_total += fx
        fee_total += fees
        totals = by_allocation.setdefault(allocation, dict(price=Decimal(0), fx=Decimal(0), fees=Decimal(0)))
        totals["price"] += price
        totals["fx"] += fx
        totals["fees"] += fees
    income = (Decimal(closing["dividend_gross"]) - Decimal(opening["dividend_gross"])
              - Decimal(closing["dividend_withholding"]) + Decimal(opening["dividend_withholding"])
              + Decimal(closing.get("dividend_receivable", "0")) - Decimal(opening.get("dividend_receivable", "0")))
    for allocation in sorted(set(by_allocation) | set(opening["allocations"]) | set(closing["allocations"])):
        first = opening["allocations"].get(allocation, {})
        last = closing["allocations"].get(allocation, {})
        delta = {field: Decimal(last.get(field, "0")) - Decimal(first.get(field, "0"))
                 for field in ("realized", "unrealized", "dividend_gross", "dividend_withholding",
                               "dividend_receivable")}
        totals = by_allocation.setdefault(allocation, dict(price=Decimal(0), fx=Decimal(0), fees=Decimal(0)))
        totals["income"] = delta["dividend_gross"] - delta["dividend_withholding"] + delta["dividend_receivable"]
        totals["pnl"] = totals["price"] + totals["fx"] - totals["fees"] + totals["income"]
        if totals["pnl"] != delta["realized"] + delta["unrealized"] + totals["income"]:
            raise PolicyDenied("VALUATION_ALLOCATION_ATTRIBUTION_MISMATCH")
    if price_total + fx_total - fee_total + income != pnl:
        raise PolicyDenied("VALUATION_ATTRIBUTION_NOT_RECONCILED")
    return dict(fx_attribution_status="complete", fx_attribution_reason=None,
                price_effect=str(price_total), fx_effect=str(fx_total),
                attribution_fees=str(fee_total), attribution_income=str(income),
                attribution_basis=("Price changes at closing FX include interaction; "
                                   "FX covers opening exposure and execution-rate effects"),
                allocation_attribution=[dict(allocation_id=key, **{name: str(value) for name, value in item.items()})
                                        for key, item in sorted(by_allocation.items())])
