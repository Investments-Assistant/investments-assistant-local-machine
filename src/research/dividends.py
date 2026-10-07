"""Gross dividend receivables with explicit payment timing and conversion evidence."""

import heapq
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass

ZERO = Decimal(0)


def validate_payment(bar, base_currency, max_fx_age_seconds):
    at, fx, fx_at = bar.dividend_pay_at, bar.dividend_payment_fx, bar.dividend_payment_fx_as_of
    if at is None:
        if fx is not None or fx_at is not None:
            raise ValueError("Dividend payment FX requires a payment time")
        return
    if at.tzinfo is None or at.utcoffset() is None or at < bar.open_at:
        raise ValueError("Dividend payment time must be aware and no earlier than entitlement")
    if bar.currency == base_currency:
        if fx is not None and fx != 1:
            raise ValueError("Base-currency dividend payment FX must equal one")
    elif fx is None or fx_at is None:
        raise ValueError("Foreign dividend payment requires explicit dated FX")
    if fx is not None and (not fx.is_finite() or fx <= 0):
        raise ValueError("Dividend payment FX must be positive and finite")
    if fx_at is not None and (
        fx_at.tzinfo is None or fx_at.utcoffset() is None or fx_at > at
        or (at - fx_at).total_seconds() > max_fx_age_seconds
    ):
        raise ValueError("Dividend payment FX is unavailable or stale")


@dataclass
class Claim:
    symbol: str
    amount: Decimal
    accrued_base: Decimal
    pay_at: datetime | None
    payment_fx: Decimal | None


class DividendLedger:
    def __init__(self):
        self.payments = []
        self.amounts = {}
        self.outstanding_basis = ZERO
        self.unknown_dates = 0
        self.sequence = 0
        self.accrued = ZERO
        self.paid = ZERO
        self.settled_fx_pnl = ZERO

    def accrue(self, bar, quantity, base_currency):
        amount = quantity * bar.dividend
        if amount == 0:
            return
        accrued = amount * bar.fx_to_base
        self.accrued += accrued
        self.amounts[bar.symbol] = self.amounts.get(bar.symbol, ZERO) + amount
        self.outstanding_basis += accrued
        if bar.dividend_pay_at is None:
            self.unknown_dates += 1
        else:
            claim = Claim(bar.symbol, amount, accrued, bar.dividend_pay_at,
                          Decimal(1) if bar.currency == base_currency else bar.dividend_payment_fx)
            self.sequence += 1
            heapq.heappush(self.payments, (claim.pay_at, self.sequence, claim))

    def settle(self, at):
        payment = ZERO
        while self.payments and self.payments[0][0] <= at:
            _, _, claim = heapq.heappop(self.payments)
            amount = claim.amount * claim.payment_fx
            payment += amount
            self.settled_fx_pnl += amount - claim.accrued_base
            self.amounts[claim.symbol] -= claim.amount
            self.outstanding_basis -= claim.accrued_base
        self.paid += payment
        return payment

    def receivable(self, rates):
        return sum((amount * rates[symbol] for symbol, amount in self.amounts.items()), ZERO)

    def summary(self, rates):
        value = self.receivable(rates)
        return dict(dividends=str(self.accrued), dividends_paid=str(self.paid),
                    dividend_receivable=str(value),
                    dividend_fx_pnl=str(self.settled_fx_pnl + value - self.outstanding_basis),
                    dividend_payment_dates_missing=self.unknown_dates)
