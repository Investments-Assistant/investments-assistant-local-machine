"""Provider contract safety using only synthetic in-memory transports."""

from unittest.mock import patch

import httpx
import pytest

from src.config import Settings
from src.expenses.sync import normalise_transaction
from src.expenses.runtime import dependencies
from src.expenses.providers import GoCardless, ProviderError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "status,code",
    [
        (302, "PROVIDER_REQUEST_REJECTED"),
        (401, "CONSENT_OR_TOKEN_REQUIRED"),
        (402, "PROVIDER_ACCESS_REQUIRES_DECISION"),
        (429, "PROVIDER_RATE_LIMIT"),
        (503, "PROVIDER_UNAVAILABLE"),
    ],
)
async def test_errors_are_typed_and_do_not_leak_provider_payload(status, code):
    provider = GoCardless(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status,
                json={"secret": "must-not-leak"},
                headers={"Location": "http://127.0.0.1/private"},
            )
        )
    )
    with pytest.raises(ProviderError, match=code) as raised:
        await provider.token({"refresh": "fixture-refresh"})
    assert "must-not-leak" not in str(raised.value)


async def test_response_bound_and_account_path_injection():
    provider = GoCardless(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 2_000_001))
    )
    with pytest.raises(ProviderError, match="PROVIDER_RESPONSE_TOO_LARGE"):
        await provider.token({"refresh": "fixture-refresh"})
    with pytest.raises(ProviderError, match="INVALID_PROVIDER_IDENTIFIER"):
        await provider.accounts({"requisition_id": "../../private", "access": "fixture"})


def test_production_bank_network_requires_separate_configuration():
    with patch(
        "src.expenses.runtime.config.settings", Settings(_env_file=None, environment="production")
    ), pytest.raises(ProviderError, match="BANK_ACCESS_NOT_AUTHORIZED"):
        dependencies()


@pytest.mark.parametrize(
    "direction,amount,expected",
    [
        ("refund", "-10.004", "10.004"),
        ("transfer", "-10.004", "-10.004"),
        ("transfer", "10.004", "10.004"),
        ("debit", "10.004", "-10.004"),
    ],
)
def test_signed_amount_and_pending_lifecycle(direction, amount, expected):
    result = normalise_transaction(
        {
            "date": "2026-09-01",
            "currency": "EUR",
            "amount": amount,
            "direction": direction,
            "lifecycle": "pending",
        },
        "fixture",
        "a",
    )
    assert result["raw_data"]["signed_amount"] == expected
    assert result["pending"] is True


def test_transfer_opposite_directions_have_distinct_fallback_ids():
    raw = {"date": "2026-09-01", "currency": "EUR", "amount": "-1", "direction": "transfer"}
    first = normalise_transaction(raw, "fixture", "a")
    second = normalise_transaction({**raw, "amount": "1"}, "fixture", "a")
    assert first["external_id"] != second["external_id"]
