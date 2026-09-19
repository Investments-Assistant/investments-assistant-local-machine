"""Provider-neutral transaction normalisation for bank sync adapters."""

from __future__ import annotations

import re
from typing import Any
from decimal import Decimal, InvalidOperation
import hashlib
from datetime import UTC, date, datetime

from src.expenses.categories import normalise_category


def parse_transaction_datetime(value: object) -> datetime:
    """Parse provider dates into timezone-aware UTC datetimes."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("Transaction date is required")
        else:
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"Invalid transaction date: {raw}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _provider_amount(raw: dict[str, Any]) -> tuple[Decimal, str, Decimal]:
    amount_value = raw.get("amount")
    if isinstance(amount_value, dict):
        amount_value = amount_value.get("amount")
    if amount_value is None and isinstance(raw.get("transactionAmount"), dict):
        amount_value = raw["transactionAmount"].get("amount")
    if amount_value is None:
        raise ValueError("Every transaction needs a numeric amount")
    try:
        amount = Decimal(str(amount_value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Every transaction needs a numeric amount") from exc
    if (
        not amount.is_finite()
        or amount == 0
        or abs(amount) >= Decimal("1e18")
        or amount != amount.quantize(Decimal("0.0000000001"))
    ):
        raise ValueError("Transaction amount must be a finite non-zero number")

    direction = str(raw.get("direction") or raw.get("transaction_type") or "").lower()
    if direction in {"credit", "income", "in", "inflow", "deposit"}:
        return abs(amount), "income", abs(amount)
    if direction in {"transfer", "internal_transfer"}:
        return abs(amount), "transfer", amount
    if direction in {"debit", "expense", "out", "outflow", "withdrawal"}:
        return abs(amount), "expense", -abs(amount)
    if direction in {"refund", "reimbursement"}:
        return abs(amount), "refund", abs(amount)
    # Most PSD2 feeds represent account debits as negative amounts. The sign
    # convention is kept as the fallback when a provider omits direction.
    return (abs(amount), "expense", amount) if amount < 0 else (abs(amount), "income", amount)


def _external_id(
    raw: dict[str, Any],
    provider: str,
    occurred_at: datetime,
    amount: Decimal,
    merchant: str,
    description: str,
    currency: str,
    transaction_type: str,
    account_name: str,
) -> str:
    supplied = (
        raw.get("external_id")
        or raw.get("transaction_id")
        or raw.get("transactionId")
        or raw.get("internalTransactionId")
    )
    if supplied:
        return str(supplied)[:256]
    stable = "|".join(
        (
            provider,
            str(raw.get("account_id") or raw.get("account_name") or account_name),
            currency,
            transaction_type,
            occurred_at.isoformat(),
            str(amount.normalize()),
            merchant,
            description,
        )
    )
    return "generated-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:48]


def normalise_transaction(raw: object, provider: str, account_name: str = "") -> dict[str, Any]:
    """Map common bank-feed shapes to the local expense transaction contract."""
    if not isinstance(raw, dict):
        raise ValueError("Each transaction must be a JSON object")
    amount, transaction_type, signed_amount = _provider_amount(raw)
    merchant = str(
        raw.get("merchant")
        or raw.get("merchant_name")
        or raw.get("debtorName")
        or raw.get("creditorName")
        or raw.get("counterparty")
        or "Unknown merchant"
    ).strip()[:256]
    description = str(
        raw.get("description")
        or raw.get("remittanceInformationUnstructured")
        or raw.get("additionalInformation")
        or ""
    ).strip()[:2000]
    occurred_at = parse_transaction_datetime(
        raw.get("occurred_at")
        or raw.get("bookingDateTime")
        or raw.get("bookingDate")
        or raw.get("valueDate")
        or raw.get("date")
    )
    currency_value = raw.get("currency")
    if not currency_value and isinstance(raw.get("transactionAmount"), dict):
        currency_value = raw["transactionAmount"].get("currency")
    currency = str(currency_value or "").upper().strip()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("An explicit three-letter transaction currency is required")
    category, subcategory = normalise_category(
        raw.get("category"),
        raw.get("subcategory"),
        merchant,
        description,
        transaction_type,
    )
    account_scope = str(raw.get("account_id") or raw.get("account_name") or account_name).strip()
    if not account_scope:
        account_scope = "import-unspecified"
    account_key = hashlib.sha256((provider + "|" + account_scope).encode()).hexdigest()
    lifecycle = str(raw.get("lifecycle") or ("pending" if raw.get("pending") else "booked"))
    if lifecycle not in {"pending", "booked", "revised", "deleted"}:
        raise ValueError("Unsupported transaction lifecycle")
    safe_provider_fields = {
        key: value
        for key, value in {
            "bank_transaction_code": raw.get("bankTransactionCode")
            or raw.get("bank_transaction_code"),
            "merchant_category_code": raw.get("merchantCategoryCode")
            or raw.get("merchant_category_code"),
            "booking_date": raw.get("bookingDate") or raw.get("booking_date"),
            "value_date": raw.get("valueDate") or raw.get("value_date"),
        }.items()
        if value is not None
    }
    safe_provider_fields["signed_amount"] = str(signed_amount)
    return {
        "external_id": _external_id(
            raw,
            provider,
            occurred_at,
            signed_amount,
            merchant,
            description,
            currency,
            transaction_type,
            account_name,
        ),
        "provider": provider[:32],
        "account_key": account_key,
        "lifecycle": lifecycle,
        "account_name": str(raw.get("account_name") or account_name or "Bank account").strip()[
            :128
        ],
        "merchant": merchant,
        "description": description,
        "amount": amount,
        "currency": currency,
        "transaction_type": transaction_type,
        "category": category,
        "subcategory": subcategory,
        "occurred_at": occurred_at,
        "pending": lifecycle == "pending",
        # Keep useful provider metadata without persisting raw account numbers,
        # IBANs, or other unreviewed provider payload fields.
        "raw_data": safe_provider_fields,
    }
