"""Persistence failures must not copy request or provider data into logs."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.web import routes


@pytest.mark.parametrize(
    "handler",
    [
        "update_broker_account",
        "deactivate_broker_account",
        "update_project",
        "get_conversation",
        "update_conversation",
        "delete_conversation",
    ],
)
async def test_persistence_error_logs_do_not_include_untrusted_details(handler, monkeypatch, caplog):
    monkeypatch.setattr(
        routes, "require_authenticated", AsyncMock(return_value=SimpleNamespace(user_id="fixture-user"))
    )
    context = MagicMock()
    context.__aenter__ = AsyncMock(side_effect=RuntimeError("private-value\nFORGED audit success"))
    monkeypatch.setattr(routes, "async_session", MagicMock(return_value=context))
    request = SimpleNamespace(json=AsyncMock(return_value={"name": "fixture", "display_name": "fixture"}))
    identifier = "87654321-1234-1234-1234-123456789012"
    with pytest.raises(HTTPException) as caught:
        await getattr(routes, handler)(identifier, request)
    assert caught.value.status_code == 503
    assert caplog.records, "The failure must remain observable"
    assert "private-value" not in caplog.text
    assert "FORGED" not in caplog.text
    assert identifier not in caplog.text
    assert "RuntimeError" in caplog.text
