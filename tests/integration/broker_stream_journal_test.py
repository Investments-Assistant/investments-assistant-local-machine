"""Disposable PostgreSQL stream checkpoints; no SDK or provider access."""

import asyncio
from datetime import UTC, datetime, timedelta
from dataclasses import replace

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.tools import broker_accounts as vault
from src.db.models import User, BrokerAccount, BrokerObservation
from src.execution.policy import PolicyDenied
from src.operations.models import JobLease
from src.execution.broker_observations import read_observations
from src.execution.broker_refresh_state import refresh_state
from src.execution.broker_stream_journal import begin_stream, checkpoint_batch
from tests.integration.broker_observations_test import seed, execution, commission, fixture_key  # noqa: F401

pytestmark = pytest.mark.integration


async def test_batches_preserve_late_commission_and_replay_dedup_then_fence_final(db_session):
    user, account = await seed(db_session)
    args = dict(user_id=user.id, account_id=account.id)
    config, scope = await begin_stream(db_session, **args, maximum_seconds=180)
    event = execution()
    first = await checkpoint_batch(db_session, scope=scope, observations=[event])
    assert first["status"] == "running" and first["inserted"] == 1
    lease = await db_session.get(JobLease, scope.lease[0])
    assert lease.last_success is None
    # A late fee is durable in a second transaction/batch; an execution replay
    # contributes no second financial fact.
    second = await checkpoint_batch(db_session, scope=scope, observations=[event, commission()])
    assert second["batches"] == 2 and second["received"] == 3 and second["inserted"] == 2
    result = await checkpoint_batch(db_session, scope=scope, observations=[], final=True)
    assert result["status"] == "observed" and result["complete_history"] is False
    assert result["execution_authority"] == "none"
    assert config["broker_account_id"] not in str(result)
    assert len((await read_observations(db_session, **args))["observations"]) == 2
    assert (await refresh_state(db_session, **args))["last_success"] is not None
    with pytest.raises(PolicyDenied, match="STALE_JOB_LEASE"):
        await checkpoint_batch(db_session, scope=scope, observations=[event])


@pytest.mark.parametrize("change,code", [
    ("revoke", "IBKR_READ_CONSENT_REQUIRED"),
    ("client_id", "BROKER_ACCOUNT_CHANGED_DURING_READ"),
    ("host", "BROKER_ACCOUNT_CHANGED_DURING_READ"),
    ("binding", "BROKER_ACCOUNT_CHANGED_DURING_READ"),
    ("inactive", "PRINCIPAL_INACTIVE"),
    ("token", "STALE_JOB_LEASE"),
    ("expired", "STALE_JOB_LEASE"),
    ("clock_backwards", "STALE_JOB_LEASE"),
    ("lifetime", "BROKER_STREAM_EXPIRED"),
])
async def test_each_batch_rechecks_current_authority_and_time(db_session, change, code):
    user, account = await seed(db_session)
    config, scope = await begin_stream(db_session, user_id=user.id, account_id=account.id)
    row = await db_session.get(JobLease, scope.lease[0])
    if change in {"revoke", "client_id", "host", "binding"}:
        edits = {"revoke": {"read_authorized": False}, "client_id": {"client_id": 99},
                 "host": {"host": "different.invalid"}, "binding": {"broker_account_id": "other-fixture"}}
        account.config_encrypted = vault.encrypt_config(config | edits[change])
    elif change == "inactive":
        user.is_active = False
    elif change == "token":
        scope = replace(scope, lease=(scope.lease[0], "stale-token"))
    elif change == "expired":
        row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    elif change == "clock_backwards":
        row.leased_at = datetime.now(UTC) + timedelta(seconds=1)
    else:
        row.checkpoint = dict(row.checkpoint, stop_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat())
    await db_session.flush()
    with pytest.raises(PolicyDenied, match=code):
        await checkpoint_batch(db_session, scope=scope, observations=[execution()])
    from src.db.models import BrokerObservation
    assert not (await db_session.scalars(select(BrokerObservation).where(
        BrokerObservation.account_id == account.id))).all()


async def test_partial_capture_is_terminal_and_cannot_be_relabelled_success(db_session):
    user, account = await seed(db_session)
    args = dict(user_id=user.id, account_id=account.id)
    _, scope = await begin_stream(db_session, **args)
    result = await checkpoint_batch(db_session, scope=scope, observations=[execution()],
                                    final=True, failures=["BROKER_CALLBACK_CAPACITY"])
    assert result["status"] == "partial" and result["inserted"] == 1
    state = await refresh_state(db_session, **args)
    assert state["failure_code"] == "BROKER_STREAM_PARTIAL" and state["last_success"] is None
    with pytest.raises(PolicyDenied, match="STALE_JOB_LEASE"):
        await checkpoint_batch(db_session, scope=scope, observations=[], final=True)


async def test_expired_running_checkpoint_reports_interruption_and_replay_is_safe(db_session):
    user, account = await seed(db_session)
    args = dict(user_id=user.id, account_id=account.id)
    _, original = await begin_stream(db_session, **args)
    event = execution()
    await checkpoint_batch(db_session, scope=original, observations=[event])
    row = await db_session.get(JobLease, original.lease[0])
    row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()
    assert (await refresh_state(db_session, **args))["status"] == "interrupted"
    _, recovered = await begin_stream(db_session, **args)
    assert recovered.lease != original.lease
    result = await checkpoint_batch(db_session, scope=recovered, observations=[event, commission()], final=True)
    assert result["inserted"] == 1 and result["received"] == 2
    with pytest.raises(PolicyDenied, match="STALE_JOB_LEASE"):
        await checkpoint_batch(db_session, scope=original, observations=[], final=True)


async def test_invalid_inputs_do_not_renew_or_write(db_session):
    user, account = await seed(db_session)
    args = dict(user_id=user.id, account_id=account.id)
    for invalid in (True, 0, 601, 1.5):
        with pytest.raises(ValueError):
            await begin_stream(db_session, **args, maximum_seconds=invalid)
    _, scope = await begin_stream(db_session, **args)
    row = await db_session.get(JobLease, scope.lease[0])
    before = dict(row.checkpoint)
    for kwargs in ({"observations": ()}, {"observations": [execution()] * 1001},
                   {"observations": [], "failures": ["private provider text"]},
                   {"observations": [], "failures": ["BROKER_CALLBACK_CAPACITY"]},
                   {"observations": [], "final": "yes"}):
        with pytest.raises(PolicyDenied):
            await checkpoint_batch(db_session, scope=scope, **kwargs)
    assert row.checkpoint == before


@pytest.mark.parametrize("final", [False, True])
async def test_committed_batches_concurrent_delivery_and_failure_rollback(integration_engine, monkeypatch, final):
    from src.execution import broker_stream_journal as journal

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        user, account = await seed(session)
        _, scope = await begin_stream(session, user_id=user.id, account_id=account.id, maximum_seconds=180)
    event = execution()

    async def deliver(observations, *, final=False):
        async with factory.begin() as session:
            return await checkpoint_batch(session, scope=scope, observations=observations, final=final)

    try:
        results = await asyncio.gather(deliver([event]), deliver([event]))
        assert sorted(result["batches"] for result in results) == [1, 2]
        async with factory.begin() as session:
            row = await session.get(JobLease, scope.lease[0])
            assert row.checkpoint["inserted"] == 1 and row.checkpoint["received"] == 2
        original = journal.record_observations

        async def expires_after_insert(session, **kwargs):
            result = await original(session, **kwargs)
            row = await session.get(JobLease, scope.lease[0])
            row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
            await session.flush()
            return result

        monkeypatch.setattr(journal, "record_observations", expires_after_insert)
        with pytest.raises(PolicyDenied, match="STALE_JOB_LEASE"):
            await deliver([commission()], final=final)
        monkeypatch.setattr(journal, "record_observations", original)
        async with factory.begin() as session:
            rows = (await read_observations(session, user_id=user.id, account_id=account.id))["observations"]
            assert len(rows) == 1  # Failed checkpoint rolled back its fee as well.
            row = await session.get(JobLease, scope.lease[0])
            assert row.checkpoint["batches"] == 2 and row.lease_until > datetime.now(UTC)
        async with factory.begin() as session:
            result = await checkpoint_batch(session, scope=scope, observations=[commission()], final=True)
            assert result["inserted"] == 2 and result["status"] == "observed"
    finally:
        async with factory.begin() as session:
            await session.execute(delete(BrokerObservation).where(BrokerObservation.account_id == account.id))
            await session.execute(delete(BrokerAccount).where(BrokerAccount.id == account.id))
            await session.execute(delete(JobLease).where(JobLease.user_id == user.id))
            await session.execute(delete(User).where(User.id == user.id))
