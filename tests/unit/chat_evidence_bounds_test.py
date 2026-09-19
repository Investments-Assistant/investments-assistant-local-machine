"""Credential field redaction and structured context bounds without a model."""

import json

from src.chat.evidence import bounded, envelope, snapshot, historical_content


def test_nested_secrets_and_private_url_parameters_are_not_saved():
    event = {
        "type": "tool_result",
        "name": "fixture",
        "result": {
            "nested": [
                {"api_key": "sensitive", "confirmation_nonce": "sensitive", "iban": "sensitive"}
            ],
            "url": "https://user:password@fixture.invalid/report?token=sensitive#private",
            "quantity": "0.004",
            "currency": "EUR",
        },
    }
    value = snapshot(event)
    encoded = json.dumps(value)
    assert "sensitive" not in encoded and "password@" not in encoded
    assert value["payload"]["quantity"] == "0.004"
    assert value["payload"]["url"] == "https://fixture.invalid/report"


def test_large_nested_results_remain_valid_and_have_explicit_omissions():
    raw = {"positions": [{"symbol": "FIXTURE", "description": "x" * 4000} for _ in range(100)]}
    value = snapshot({"type": "tool_result", "name": "get_portfolio_summary", "result": raw})
    assert len(json.dumps(value).encode()) < 17000
    json.loads(json.dumps(value))
    context = historical_content("Answer", envelope("complete", [value] * 32), "fixture-id")
    assert len(context.encode()) < 8200
    assert "exceed context budget" in context
    assert "/api/chat/turns/fixture-id/evidence" in context


def test_profile_budget_never_slices_serialized_json():
    profile = {"description": "x" * 10000, "preferences": {"nested": ["x" * 4000] * 30}}
    result = bounded(profile)
    assert json.loads(json.dumps(result)) == result
    assert result["description"]["omitted_characters"] == 9000
