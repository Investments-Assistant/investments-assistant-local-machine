"""Explicit capture activation with real account consent and synthetic workers."""

import asyncio
from contextlib import suppress, asynccontextmanager

import pytest
from pydantic import ValidationError

from src.tools import broker_accounts as vault
from src.execution import broker_capture_control as control
from src.execution.policy import PolicyDenied
from src.web.broker_observations import CaptureInput
from tests.integration.broker_observations_test import seed, fixture_key  # noqa: F401

pytestmark = pytest.mark.integration


def transactions(monkeypatch, session):
    @asynccontextmanager
    async def transaction():
        yield session

    monkeypatch.setattr(control, "transaction", transaction)


@pytest.mark.parametrize("outcome", ["observed", "partial", "private_failure"])
async def test_explicit_activation_is_finite_and_never_auto_restarts(db_session, monkeypatch, outcome):
    owner, account = await seed(db_session)
    transactions(monkeypatch, db_session)
    calls = []

    async def capture(**args):
        calls.append(args)
        if outcome == "private_failure":
            raise RuntimeError("private-account-credential")
        return {"status": outcome}

    monkeypatch.setattr(control, "capture_observations", capture)
    manager = control.CaptureController()
    scope = dict(user_id=owner.id, account_id=account.id)
    assert manager.status(**scope)["status"] == "inactive" and not calls
    assert (await manager.start(**scope, duration_seconds=7))["status"] == "starting"
    await manager.task
    result = manager.status(**scope)
    assert result["status"] == ("failed" if outcome == "private_failure" else outcome)
    assert "private" not in str(result) and result["execution_authority"] == "none"
    assert calls == [dict(scope, duration_seconds=7)]
    restarted = control.CaptureController()
    assert restarted.status(**scope)["status"] == "inactive" and len(calls) == 1


async def test_current_account_consent_and_ownership_before_activation(db_session, monkeypatch):
    owner, account = await seed(db_session)
    stranger, _ = await seed(db_session)
    transactions(monkeypatch, db_session)

    async def forbidden(**args):
        pytest.fail("Unauthorized capture started")

    monkeypatch.setattr(control, "capture_observations", forbidden)
    manager = control.CaptureController()
    with pytest.raises(PolicyDenied):
        await manager.start(user_id=stranger.id, account_id=account.id, duration_seconds=1)
    config = vault.decrypt_config(account.config_encrypted)
    account.config_encrypted = vault.encrypt_config(config | {"read_authorized": False})
    await db_session.flush()
    with pytest.raises(PolicyDenied):
        await manager.start(user_id=owner.id, account_id=account.id, duration_seconds=1)
    assert manager.task is None


async def test_explicit_stop_scope_slot_and_shutdown(db_session, monkeypatch):
    owner, account = await seed(db_session)
    transactions(monkeypatch, db_session)
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def capture(**args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(control, "capture_observations", capture)
    manager = control.CaptureController()
    scope = dict(user_id=owner.id, account_id=account.id)
    await manager.start(**scope, duration_seconds=3)
    await asyncio.wait_for(entered.wait(), 1)
    try:
        with pytest.raises(PolicyDenied, match="BROKER_CAPTURE_BUSY"):
            await manager.start(**scope, duration_seconds=3)
        assert manager.status(user_id="other", account_id=account.id)["status"] == "inactive"
        with pytest.raises(PolicyDenied, match="BROKER_CAPTURE_NOT_OWNED"):
            await manager.stop(user_id="other", account_id=account.id)
        result = await manager.stop(**scope)
        assert result["status"] == "stop_requested" and not result["native_cleanup_verified"]
        # Repeated stop cannot interrupt cancellation cleanup a second time.
        await manager.stop(**scope)
        with suppress(asyncio.CancelledError):
            await manager.task
        assert cleaned.is_set() and manager.status(**scope)["status"] == "interrupted"
        await manager.start(**scope, duration_seconds=3)
        await manager.shutdown()
        assert manager.task.done() and manager.status(**scope)["status"] == "interrupted"
        with pytest.raises(PolicyDenied, match="BROKER_CAPTURE_SHUTTING_DOWN"):
            await manager.start(**scope, duration_seconds=3)
    finally:
        await manager.shutdown()


@pytest.mark.parametrize("payload", [
    {}, {"confirm_broker_read": False}, {"confirm_broker_read": True, "duration_seconds": True},
    {"confirm_broker_read": 1},
    {"confirm_broker_read": True, "duration_seconds": 481},
    {"confirm_broker_read": True, "duration_seconds": "60"},
    {"confirm_broker_read": True, "automatic_restart": True},
])
def test_capture_requires_explicit_confirmation_and_bounded_duration(payload):
    with pytest.raises(ValidationError):
        CaptureInput(**payload)


async def test_browser_activation_requires_session_csrf_scope_and_current_principal(db_session, monkeypatch):
    import httpx
    from fastapi import FastAPI

    from src.db import database
    from src.web import auth, broker_observations
    from tests.integration.sessions_test import production

    owner, account = await seed(db_session)
    other, _ = await seed(db_session)
    transactions(monkeypatch, db_session)

    @asynccontextmanager
    async def factory():
        yield db_session

    monkeypatch.setattr(database, "async_session", factory)
    monkeypatch.setattr(auth.config, "settings", production())
    manager = control.CaptureController()
    monkeypatch.setattr(broker_observations, "capture_control", manager)
    calls = []

    async def capture(**args):
        calls.append(args)
        return {"status": "observed"}

    monkeypatch.setattr(control, "capture_observations", capture)
    app = FastAPI()
    app.include_router(broker_observations.router)
    path = f"/api/broker-accounts/{account.id}/observations/capture"
    body = {"confirm_broker_read": True, "duration_seconds": 1}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture") as client:
        assert (await client.post(path, json=body)).status_code in {401, 403}
        client.cookies.set("ia_session", auth.create_session(owner.username, owner.id))
        assert (await client.post(path, json=body)).status_code == 403
        client.cookies.set("ia_csrf", "synthetic-csrf")
        client.headers["X-CSRF-Token"] = "synthetic-csrf"
        assert (await client.post(path, json={"confirm_broker_read": 1})).status_code == 422
        client.cookies.set("ia_session", auth.create_session(other.username, other.id))
        assert (await client.post(path, json=body)).status_code == 409
        assert not calls
        client.cookies.set("ia_session", auth.create_session(owner.username, owner.id))
        assert (await client.post(path, json=body)).status_code == 202
        await manager.task
        assert len(calls) == 1 and (await client.get(path)).json()["status"] == "observed"
        owner.is_active = False
        await db_session.flush()
        assert (await client.get(path)).status_code == 401
        assert (await client.delete(path)).status_code == 401
        assert (await client.post(path, json=body)).status_code == 401
