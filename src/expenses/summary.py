"""Exact, currency-separated expense summaries over an explicitly bounded page."""

from decimal import Decimal
from collections import defaultdict


def summarize_currencies(rows) -> dict:
    totals = defaultdict(lambda: {"expenses": Decimal(0), "income": Decimal(0)})
    for row in rows:
        if row.pending or getattr(row, "lifecycle", None) == "deleted":
            continue
        bucket = totals[row.currency]
        if row.transaction_type == "expense":
            bucket["expenses"] += Decimal(str(row.amount))
        elif row.transaction_type in {"income", "refund"}:
            bucket["income"] += Decimal(str(row.amount))
    return {
        currency: {
            "total_expenses": str(values["expenses"]),
            "total_income": str(values["income"]),
            "net_cashflow": str(values["income"] - values["expenses"]),
        }
        for currency, values in sorted(totals.items())
    }
