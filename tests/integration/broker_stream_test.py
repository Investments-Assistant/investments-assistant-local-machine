"""Finite capture through the real owner and PG journal, using only an SDK fixture."""

import sys
from types import SimpleNamespace as Obj
import asyncio
import threading
from contextlib import suppress

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.tools import broker_accounts as vault
from src.db.models import User, BrokerAccount, BrokerObservation
from src.execution import broker_stream, broker_monitor
from src.execution.policy import PolicyDenied
from src.operations.models import JobLease, OperationalAlert
from tests.unit.ibkr_observations_test import SDK, fill
from tests.integration.broker_observations_test import seed, fixture_key  # noqa: F401

pytestmark = pytest.mark.integration


class StreamingSDK(SDK):
    def __init__(self):
        super().__init__()
        self.connected = False
        self.late = threading.Event()
        self.trace = []
        self.observed = fill()
        self.startup_hold = None
        self.entered = threading.Event()
        self.closed = threading.Event()
        self.cleanup_failure = False

    def connect(self, **kwargs):
        assert kwargs["readonly"] is True and kwargs["account"] == "synthetic"
        self.connected = True
        self.trace.append(("connect", threading.get_ident()))
        self.entered.set()
        if self.startup_hold is not None:
            assert self.startup_hold.wait(5)

    def disconnect(self):
        self.connected = False
        self.trace.append(("disconnect", threading.get_ident()))
        self.closed.set()
        if self.cleanup_failure:
            raise RuntimeError("private provider cleanup details")

    def managedAccounts(self):
        return ["synthetic"]

    def isConnected(self):
        return self.connected

    def reqExecutions(self, _filter):
        return [self.observed]

    def sleep(self, seconds):
        if self.late.is_set():
            self.late.clear()
            self.commissionReportEvent.emit(None, self.observed,
                Obj(execId="fixture.1", currency="EUR", commission=.03))
        threading.Event().wait(min(seconds, .01))


@pytest.mark.parametrize("scenario", [
    "success", "gap", "revoke", "disconnect", "cancel", "startup_cancel", "cleanup_failure",
    "upstream1100", "upstream1101", "upstream1102", "upstream1300",
])
async def test_stream_preserves_only_authorized_batches_and_cleans_owner(integration_engine, monkeypatch, scenario):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    monkeypatch.setattr(broker_stream, "async_session", factory)
    monkeypatch.setattr(broker_monitor, "async_session", factory)
    sdk = StreamingSDK()
    sdk.cleanup_failure = scenario == "cleanup_failure"
    if scenario == "startup_cancel":
        sdk.startup_hold = threading.Event()
    monkeypatch.setitem(sys.modules, "ib_insync", Obj(IB=lambda: sdk, ExecutionFilter=lambda **_: "fixture-filter"))
    async with factory.begin() as session:
        user, account = await seed(session)
        config = vault.decrypt_config(account.config_encrypted)
        account.config_encrypted = vault.encrypt_config(config | {"broker_account_id": "synthetic"})
    original = broker_stream.checkpoint_batch
    batches = []

    async def checkpoint(session, **kwargs):
        result = await original(session, **kwargs)
        batches.append(result)
        if len(batches) == 1:
            sdk.late.set()
            if scenario == "revoke":
                row = await session.get(BrokerAccount, account.id)
                selected = vault.decrypt_config(row.config_encrypted)
                row.config_encrypted = vault.encrypt_config(selected | {"read_authorized": False})
            elif scenario == "disconnect":
                sdk.connected = False
            elif scenario == "gap":
                # Bad provider evidence delivered on the SDK owner, after its
                # initial snapshot. It must close partial rather than renew.
                sdk.observed.execution.shares = -1
                sdk.sleep = bad_callback
            elif scenario.startswith("upstream"):
                sdk.sleep = upstream_message
        return result

    def bad_callback(seconds):
        sdk.execDetailsEvent.emit(None, sdk.observed)
        threading.Event().wait(min(seconds, .01))

    def upstream_message(seconds):
        assert sdk.connected  # Upstream notification without local socket loss.
        sdk.errorEvent.emit(-1, int(scenario.removeprefix("upstream")), "private provider account", None)
        sdk.errorEvent.emit(-1, 1102, "restored", None)
        threading.Event().wait(min(seconds, .01))

    monkeypatch.setattr(broker_stream, "checkpoint_batch", checkpoint)
    task = asyncio.create_task(broker_stream.capture_observations(
        user_id=user.id, account_id=account.id, duration_seconds=1, batch_seconds=1))
    try:
        if scenario == "startup_cancel":
            assert await asyncio.to_thread(sdk.entered.wait, 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not sdk.closed.is_set()  # Native connect is still owned.
            sdk.startup_hold.set()
            assert await asyncio.to_thread(sdk.closed.wait, 2)
        elif scenario == "cancel":
            # Wait for an actual committed first checkpoint, then cancel between
            # reads; use a bounded test deadline, no elapsed-time success claim.
            async with asyncio.timeout(3):
                while True:
                    async with factory.begin() as session:
                        row = await session.scalar(select(JobLease).where(JobLease.user_id == user.id))
                        if row and row.checkpoint.get("batches", 0) >= 1:
                            break
                    await asyncio.sleep(.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif scenario == "revoke":
            with pytest.raises(PolicyDenied, match="IBKR_READ_CONSENT_REQUIRED"):
                await task
        elif scenario in {"disconnect", "cleanup_failure"}:
            with pytest.raises(RuntimeError):
                await task
        else:
            result = await task
            assert result["status"] == (
                "partial" if scenario == "gap" or scenario.startswith("upstream") else "observed")
            assert result["complete_history"] is False and result["execution_authority"] == "none"
        assert [item[0] for item in sdk.trace] == ["connect", "disconnect"]
        assert len({item[1] for item in sdk.trace}) == 1
        assert not sdk.execDetailsEvent.handlers and not sdk.commissionReportEvent.handlers
        assert not sdk.errorEvent.handlers
        async with factory.begin() as session:
            row = await session.scalar(select(JobLease).where(JobLease.user_id == user.id))
            observations = (await session.scalars(select(BrokerObservation).where(
                BrokerObservation.account_id == account.id))).all()
            kinds = [observation.kind for observation in observations]
            assert ("execution" in kinds) is (scenario != "startup_cancel")
            if scenario == "success":
                assert "commission" in kinds and row.last_success is not None
            elif scenario in {"revoke", "cancel", "disconnect", "startup_cancel", "cleanup_failure"}:
                assert "commission" not in kinds and row.checkpoint["status"] == "failed"
                assert row.last_success is None and row.checkpoint["native_completion"] == "unknown"
                assert row.checkpoint["batches"] == (0 if scenario == "startup_cancel" else 1)
            else:
                assert row.checkpoint["status"] == "partial" and row.last_success is None
                alert = await session.scalar(select(OperationalAlert).where(OperationalAlert.user_id == user.id))
                expected = ("BROKER_UPSTREAM_CONNECTION_CHANGED" if scenario.startswith("upstream")
                            else "INVALID_BROKER_CALLBACK")
                assert alert.rule == "broker_callback_evidence" and alert.observed_value == expected
                assert "private provider" not in str(row.checkpoint)
    finally:
        if sdk.startup_hold is not None:
            sdk.startup_hold.set()
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        async with factory.begin() as session:
            for model, condition in [
                (BrokerObservation, BrokerObservation.account_id == account.id),
                (BrokerAccount, BrokerAccount.id == account.id),
                (OperationalAlert, OperationalAlert.user_id == user.id),
                (JobLease, JobLease.user_id == user.id), (User, User.id == user.id),
            ]:
                await session.execute(delete(model).where(condition))
