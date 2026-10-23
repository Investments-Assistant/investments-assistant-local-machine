"""Pure offline contract validation; no SDK construction or database connection."""

import uuid
from types import SimpleNamespace
from decimal import Decimal
import importlib

import pytest
from pydantic import ValidationError

from src.execution.policy import PolicyDenied, digest
from src.execution.broker_submission import (
    TransportReceipt,
    SubmissionRequest,
    BrokerSubmissionJournal,
    _request,
    _attempt_reference,
    _identity_candidates,
)
from src.execution.broker_observations import hash_order_reference


def request_values(**changes):
    return dict(environment="paper", session_id="fixture-session", correlation_id="fixture-correlation",
                con_id=123, client_id=77, order_id=1, security_type="STK", exchange="IBIS2", currency="EUR",
                side="buy", order_type="LMT", quantity="0.004", limit_price="100", tick="0.01", lot="0.001",
                multiplier="1") | changes


def test_exact_decimal_canonicalization_is_immutable_and_hash_stable():
    first = SubmissionRequest(**request_values())
    equivalent = SubmissionRequest(**request_values(quantity="0.0040", limit_price="100.00"))
    assert first.quantity == Decimal("0.004")
    assert digest(first.model_dump(mode="json")) == digest(equivalent.model_dump(mode="json"))
    with pytest.raises(ValidationError):
        first.quantity = Decimal("1")


@pytest.mark.parametrize("changes", [
    {"quantity": "NaN"}, {"limit_price": "Infinity"}, {"quantity": "-1"}, {"quantity": "0"},
    {"quantity": "0.00000000001"}, {"quantity": "1e18"}, {"quantity": "0.0041"},
    {"limit_price": "100.001"}, {"tick": "0"}, {"lot": "0"}, {"multiplier": "-1"},
    {"con_id": True}, {"order_id": -1}, {"client_id": 0}, {"client_id": True},
    {"environment": "live"}, {"environment_verified": "paper"}, {"approval": True},
    {"security_type": "OPT"}, {"order_type": "MKT"}, {"currency": "eur"}, {"exchange": ""},
    {"session_id": "x" * 129}, {"correlation_id": "x" * 65},
    {"quantity": 0.004}, {"multiplier": True}, {"limit_price": 9007199254740993.0},
])
def test_invalid_or_authority_claiming_contracts_are_rejected(changes):
    with pytest.raises(ValidationError):
        SubmissionRequest(**request_values(**changes))


def test_constructed_model_cannot_skip_service_validation():
    forged = SubmissionRequest.model_construct(**request_values(quantity=Decimal("NaN")))
    with pytest.raises(PolicyDenied, match="INVALID_SUBMISSION_REQUEST"):
        _request(forged)


def test_large_exact_decimal_text_does_not_undergo_float_rounding():
    request = SubmissionRequest(**request_values(limit_price="9007199254740993", tick="1"))
    assert request.limit_price == Decimal("9007199254740993")


def test_attempt_reference_reuses_random_identity_without_changing_request():
    request = SubmissionRequest(**request_values())
    before = digest(request.model_dump(mode="json"))
    attempt = str(uuid.uuid4())
    reference = _attempt_reference(attempt)
    assert reference == uuid.UUID(attempt).hex and len(reference) == 32
    assert hash_order_reference(reference) != reference
    assert before == digest(request.model_dump(mode="json"))
    for invalid in (None, "not-an-id", uuid.uuid4().hex, str(uuid.uuid1())):
        with pytest.raises(PolicyDenied, match="SUBMISSION_ATTEMPT_REFERENCE_INVALID"):
            _attempt_reference(invalid)


@pytest.mark.parametrize("changes,reason", [
    ({"order_ref_sha256": "a" * 64}, "SUBMISSION_IDENTITY_REFERENCE_CONFLICT"),
    ({"order_id": 2}, "SUBMISSION_IDENTITY_ORDER_CONFLICT"),
    ({"client_id": 78}, "SUBMISSION_IDENTITY_ORDER_CONFLICT"),
    ({"con_id": 456}, "SUBMISSION_IDENTITY_CONTRACT_UNRESOLVED"),
    ({"security_type": "OPT"}, "SUBMISSION_IDENTITY_CONTRACT_UNRESOLVED"),
    ({"multiplier": "100"}, "SUBMISSION_IDENTITY_CONTRACT_UNRESOLVED"),
    ({"currency": "USD"}, "SUBMISSION_IDENTITY_CONTRACT_UNRESOLVED"),
    ({"side": "SLD"}, "SUBMISSION_IDENTITY_CONTRACT_UNRESOLVED"),
    ({"permanent_id": 0}, "SUBMISSION_IDENTITY_PERMANENT_ID_UNAVAILABLE"),
])
def test_reference_does_not_override_other_identity_or_contract_evidence(changes, reason):
    reference = hash_order_reference(uuid.uuid4().hex)
    payload = dict(order_ref_sha256=reference, client_id=77, order_id=1, con_id=123, security_type="STK",
                   multiplier="1", currency="EUR", side="BOT", permanent_id=9) | changes
    row = SimpleNamespace(id="synthetic", payload=payload, payload_sha256=digest(payload))
    candidates, reasons, _ = _identity_candidates(SubmissionRequest(**request_values()), reference, [row])
    assert reason in reasons
    assert candidates == set()


def test_missing_reference_never_proves_identity_and_conflicting_history_is_not_discarded():
    reference = hash_order_reference(uuid.uuid4().hex)
    base = dict(client_id=77, order_id=1, con_id=123, security_type="STK", multiplier="1",
                currency="EUR", side="BOT", permanent_id=9)
    def row(identity, **changes):
        payload = base | changes
        return SimpleNamespace(id=identity, payload=payload, payload_sha256=digest(payload))
    request = SubmissionRequest(**request_values())
    assert _identity_candidates(request, reference, [row("missing")])[0] == set()
    candidates, reasons, _ = _identity_candidates(request, reference, [
        row("candidate", order_ref_sha256=reference), row("unreferenced", permanent_id=10),
    ])
    assert candidates == {"9"} and "SUBMISSION_IDENTITY_PERMANENT_ID_CONFLICT" in reasons


@pytest.mark.parametrize("changes", [
    {"permanent_id": None}, {"permanent_id": 0}, {"permanent_id": True},
    {"status": "filled"}, {"status": "rejected"}, {"environment_verified": "paper"},
    {"order_id": True}, {"client_id": 0},
])
def test_receipts_cannot_claim_fills_or_verified_environment(changes):
    with pytest.raises(ValidationError):
        TransportReceipt(**(dict(status="acknowledged", client_id=77, order_id=1, permanent_id=9) | changes))


def test_caller_session_or_unbound_factory_cannot_be_committed_by_service():
    from sqlalchemy.ext.asyncio import async_sessionmaker

    for value in (object(), async_sessionmaker()):
        with pytest.raises(TypeError, match="async_sessionmaker"):
            BrokerSubmissionJournal(value)


@pytest.mark.parametrize("broker", ["ibkr", "alpaca", "binance", "coinbase"])
@pytest.mark.parametrize("operation", ["submit", "cancel"])
def test_all_real_sdk_write_entrypoints_stay_unconditionally_closed(monkeypatch, broker, operation):
    # No SDK import is needed by these lazy adapter modules. Even arbitrary
    # approval/account/verified-environment kwargs never reach the legacy body.
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    module = importlib.import_module("src.tools.brokers." + broker)
    function = getattr(module, operation + "_" + broker + "_order")
    result = function(approval=True, environment_verified="paper", account=object())
    assert result["blocked"] is True and result["success"] is False
    assert result["reason_code"] == "EXTERNAL_WRITES_NOT_AUTHORIZED"
