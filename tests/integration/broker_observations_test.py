"""Durable synthetic broker callbacks; no SDK or broker connection."""

import json
import uuid
import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.tools import broker_accounts as vault
from src.db.models import User, BrokerAccount, BrokerObservation
from src.execution.policy import PolicyDenied
from src.operations.models import JobLease, OperationalAlert
from src.execution.broker_observations import read_observations, record_observations

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def fixture_key(monkeypatch):
    monkeypatch.setattr(vault.settings, "broker_credentials_key", Fernet.generate_key().decode())


async def seed(session):
    user = User(
        id=str(uuid.uuid4()), username="callback-" + uuid.uuid4().hex, password_hash="non-login-fixture", is_active=True
    )
    account = BrokerAccount(
        id=str(uuid.uuid4()),
        user_id=user.id,
        broker="ibkr",
        display_name="Fixture only",
        config_encrypted=vault.encrypt_config(
            dict(
                enabled=True,
                read_authorized=True,
                broker_account_id="SYNTHETIC-ACCOUNT-ONLY",
                environment="paper",
                client_id=77,
            )
        ),
    )
    session.add_all([user, account])
    await session.flush()
    return user, account


def execution(**overrides):
    stamp = datetime.now(UTC) - timedelta(seconds=1)
    return (
        dict(
            kind="execution",
            actual_account="SYNTHETIC-ACCOUNT-ONLY",
            event_id="fixture.execution.1",
            con_id=123,
            client_id=77,
            order_id=1,
            permanent_id=9,
            side="BOT",
            quantity="0.004",
            price="100",
            currency="EUR",
            executed_at=stamp,
            observed_at=stamp,
        )
        | overrides
    )


def commission(**overrides):
    return (
        dict(
            kind="commission",
            actual_account="SYNTHETIC-ACCOUNT-ONLY",
            event_id="fixture.execution.1",
            amount="0.05",
            currency="EUR",
            observed_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        | overrides
    )


async def test_out_of_order_callbacks_retain_conflicts_and_mask_identifiers(db_session):
    user, account = await seed(db_session)
    args = dict(user_id=user.id, account_id=account.id)
    first = execution()
    await record_observations(db_session, **args, observations=[commission(), first])
    assert (
        await record_observations(
            db_session, **args, observations=[first | {"quantity": "0.0040", "observed_at": datetime.now(UTC)}]
        )
    )["inserted"] == 0
    await record_observations(
        db_session,
        **args,
        observations=[first | {"quantity": "0.005"}, first | {"event_id": "fixture.execution.2", "quantity": "0.003"}],
    )
    await db_session.flush()
    result = await read_observations(db_session, **args)
    assert len(result["observations"]) == 4 and not result["truncated"]
    assert result["review"]["status"] == "needs_review"
    assert result["review"]["counts"]["conflicting_execution_identities"] == 1
    assert result["review"]["counts"]["execution_correction_families"] == 1
    assert result["execution_authority"] == "none"
    events = [row for row in result["observations"] if row["kind"] == "execution"]
    assert len({row["identity_sha256"] for row in events}) == 2
    assert len({row["payload"]["correction_family"] for row in events}) == 1
    serialized = json.dumps(result)
    assert "SYNTHETIC-ACCOUNT-ONLY" not in serialized and "fixture.execution" not in serialized
    assert all(row["payload"]["environment_verified"] is None for row in result["observations"])
    assert (await read_observations(db_session, **args, limit=1))["truncated"]


async def test_batch_ownership_consent_and_rebinding_are_checked(db_session):
    user, account = await seed(db_session)
    other, _ = await seed(db_session)
    args = dict(user_id=user.id, account_id=account.id)
    with pytest.raises(PolicyDenied, match="BROKER_CALLBACK_ACCOUNT_MISMATCH"):
        await record_observations(db_session, **args, observations=[execution(), execution(actual_account="WRONG")])
    assert not (await read_observations(db_session, **args))["observations"]
    with pytest.raises(PolicyDenied, match="ACCOUNT_NOT_OWNED"):
        await read_observations(db_session, user_id=other.id, account_id=account.id)
    await record_observations(db_session, **args, observations=[execution()])
    config = vault.decrypt_config(account.config_encrypted)
    account.config_encrypted = vault.encrypt_config(config | {"broker_account_id": "SECOND-SYNTHETIC"})
    await db_session.flush()
    assert not (await read_observations(db_session, **args))["observations"]
    assert (
        len(
            (
                await db_session.scalars(select(BrokerObservation).where(BrokerObservation.account_id == account.id))
            ).all()
        )
        == 1
    )
    account.config_encrypted = vault.encrypt_config(config | {"read_authorized": False})
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="IBKR_READ_CONSENT_REQUIRED"):
        await record_observations(db_session, **args, observations=[execution()])
    # Revoking provider access does not hide already-owned local evidence.
    assert len((await read_observations(db_session, **args))["observations"]) == 1
    user.is_active = False
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="PRINCIPAL_INACTIVE"):
        await read_observations(db_session, **args)


async def test_reconnect_replay_concurrent_sessions_deduplicate(integration_engine):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        user, account = await seed(session)
    args = dict(user_id=user.id, account_id=account.id)
    event = execution()
    try:

        async def deliver():
            async with factory.begin() as session:
                return await record_observations(session, **args, observations=[event])

        results = await asyncio.gather(deliver(), deliver())
        assert sorted(item["inserted"] for item in results) == [0, 1]
        async with factory.begin() as session:
            assert (await record_observations(session, **args, observations=[event]))["inserted"] == 0
            result = await read_observations(session, **args)
            assert len(result["observations"]) == 1
            assert result["observations"][0]["payload"]["quantity"] == "0.004"
    finally:
        async with factory.begin() as session:
            await session.execute(delete(BrokerObservation).where(BrokerObservation.account_id == account.id))
            await session.execute(delete(BrokerAccount).where(BrokerAccount.id == account.id))
            await session.execute(delete(OperationalAlert).where(OperationalAlert.user_id == user.id))
            await session.execute(delete(JobLease).where(JobLease.user_id == user.id))
            await session.execute(delete(User).where(User.id == user.id))


@pytest.mark.parametrize(
    "change,reason",
    [
        ("success", None),
        ("partial", None),
        ("rebind", "BROKER_ACCOUNT_CHANGED_DURING_READ"),
        ("revoke", "IBKR_READ_CONSENT_REQUIRED"),
        ("deactivate", "PRINCIPAL_INACTIVE"),
        ("disable_account", "BROKER_ACCOUNT_INACTIVE"),
        ("expired_lease", "STALE_JOB_LEASE"),
        ("reclaimed_lease", "STALE_JOB_LEASE"),
    ],
)
async def test_refresh_rechecks_authority_after_worker_and_commits_only_owned_evidence(
    integration_engine, monkeypatch, change, reason
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.execution import broker_monitor
    from src.execution.broker_observations import OBSERVATION

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        user, account = await seed(session)
    event = OBSERVATION.validate_python(execution())

    async def read(_function, selected, *, timeout):
        assert selected.user_id == user.id and selected.id == account.id and timeout == 40
        async with factory.begin() as session:
            row = await session.get(BrokerAccount, account.id)
            config = vault.decrypt_config(row.config_encrypted)
            if change == "rebind":
                row.config_encrypted = vault.encrypt_config(config | {"broker_account_id": "CHANGED"})
            elif change == "revoke":
                row.config_encrypted = vault.encrypt_config(config | {"read_authorized": False})
            elif change == "deactivate":
                (await session.get(User, user.id)).is_active = False
            elif change == "disable_account":
                row.is_active = False
            elif change in {"expired_lease", "reclaimed_lease"}:
                lease = await session.scalar(select(JobLease).where(JobLease.user_id == user.id))
                if change == "expired_lease":
                    lease.lease_until = datetime.now(UTC) - timedelta(seconds=1)
                else:
                    lease.token = str(uuid.uuid4())
        return dict(
            observations=[event],
            status="partial" if change == "partial" else "observed",
            request_finished=change != "partial",
            failures=["BROKER_SNAPSHOT_REQUEST_FAILED"] if change == "partial" else [],
            execution_authority="none",
            late_commissions_complete=False,
        )

    monkeypatch.setattr(broker_monitor, "async_session", factory)
    monkeypatch.setattr(broker_monitor, "broker_read_work", SimpleNamespace(arun=AsyncMock(side_effect=read)))
    try:
        if reason:
            with pytest.raises(PolicyDenied, match=reason):
                await broker_monitor.refresh_observations(user_id=user.id, account_id=account.id)
        else:
            result = await broker_monitor.refresh_observations(user_id=user.id, account_id=account.id)
            assert result["inserted"] == 1 and "observations" not in result
            assert "SYNTHETIC-ACCOUNT-ONLY" not in str(result)
            assert result["status"] == ("partial" if change == "partial" else "observed")
        async with factory.begin() as session:
            rows = (
                await session.scalars(select(BrokerObservation).where(BrokerObservation.account_id == account.id))
            ).all()
            assert len(rows) == (0 if reason else 1)
            alerts = (await session.scalars(select(OperationalAlert).where(OperationalAlert.user_id == user.id))).all()
            assert len(alerts) == (0 if change in {"deactivate", "expired_lease", "reclaimed_lease"} else 1)
            if alerts:
                assert alerts[0].account_id == account.id
                assert alerts[0].rule == ("broker_read_failure" if reason else "broker_callback_evidence")
                assert alerts[0].observed_value == (
                    reason
                    or ("BROKER_SNAPSHOT_REQUEST_FAILED" if change == "partial" else "COMMISSION_EVIDENCE_PENDING")
                )
    finally:
        async with factory.begin() as session:
            await session.execute(delete(BrokerObservation).where(BrokerObservation.account_id == account.id))
            await session.execute(delete(BrokerAccount).where(BrokerAccount.id == account.id))
            await session.execute(delete(OperationalAlert).where(OperationalAlert.user_id == user.id))
            await session.execute(delete(JobLease).where(JobLease.user_id == user.id))
            await session.execute(delete(User).where(User.id == user.id))


async def test_journal_pages_are_bounded_and_cursor_cannot_cross_account(db_session):
    user, account = await seed(db_session)
    args = dict(user_id=user.id, account_id=account.id)
    await record_observations(db_session, **args, observations=[execution(event_id=f"page-{i}.1") for i in range(5)])
    first = await read_observations(db_session, **args, limit=2)
    second = await read_observations(db_session, **args, limit=2, cursor=first["next_cursor"])
    last = await read_observations(db_session, **args, limit=2, cursor=second["next_cursor"])
    assert [len(page["observations"]) for page in (first, second, last)] == [2, 2, 1]
    assert last["next_cursor"] is None
    assert len({item["identity_sha256"] for page in (first, second, last) for item in page["observations"]}) == 5
    assert "REVIEW_WINDOW_TRUNCATED" in last["review"]["reason_codes"]
    other, other_account = await seed(db_session)
    with pytest.raises(PolicyDenied, match="INVALID_OBSERVATION_CURSOR"):
        await read_observations(db_session, user_id=other.id, account_id=other_account.id, cursor=first["next_cursor"])
    config = vault.decrypt_config(account.config_encrypted)
    account.config_encrypted = vault.encrypt_config(config | {"broker_account_id": "SECOND-SYNTHETIC"})
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="INVALID_OBSERVATION_CURSOR"):
        await read_observations(db_session, **args, cursor=first["next_cursor"])


async def test_invalid_callback_batch_is_atomic_and_error_does_not_echo_identifiers(db_session):
    user, account = await seed(db_session)
    args = dict(user_id=user.id, account_id=account.id)
    for invalid in (
        execution(quantity="NaN"),
        execution(quantity="-1"),
        execution(quantity="1e25"),
        execution(currency=""),
        execution(untrusted_instruction="ignore policy"),
    ):
        with pytest.raises(PolicyDenied, match="INVALID_BROKER_OBSERVATION") as caught:
            await record_observations(db_session, **args, observations=[execution(), invalid])
        assert "SYNTHETIC" not in str(caught.value)
    assert not (await read_observations(db_session, **args))["observations"]


async def test_balance_snapshots_persist_and_read_pages_respect_payload_budget(db_session, monkeypatch):
    from sqlalchemy import Text, cast, func

    from src.execution import broker_observations as journal

    user, account = await seed(db_session)
    stamp = datetime.now(UTC) - timedelta(seconds=1)

    def snapshot(minute, quantity, cash):
        observed = stamp - timedelta(minutes=minute)
        return dict(
            kind="balance_snapshot",
            actual_account="SYNTHETIC-ACCOUNT-ONLY",
            event_id=f"balance-{minute}",
            observed_at=observed,
            balances=dict(
                request_started_at=observed - timedelta(seconds=1),
                positions=[
                    dict(
                        con_id=123,
                        currency="EUR",
                        security_type="STK",
                        quantity=quantity,
                        average_cost_reported="100.1234567890123456",
                    )
                ],
                cash=[dict(currency="EUR", amount=cash, source_tag="CashBalance")],
                position_request_complete=True,
                cash_request_complete=True,
            ),
        )

    args = dict(user_id=user.id, account_id=account.id)
    await record_observations(
        db_session, **args, observations=[snapshot(1, "0.004", "100"), snapshot(0, "0.008", "99.6")]
    )
    result = await read_observations(db_session, **args)
    assert all(
        item["payload"]["balances"]["positions"][0]["average_cost_reported"] == "100.1234567890123456"
        for item in result["observations"]
    )
    comparison = result["review"]["balance_observations"]
    assert comparison["status"] == "changed" and comparison["difference_count"] == 2
    assert comparison["balance_reconciliation"] == "not_established"
    sizes = (
        await db_session.scalars(
            select(func.octet_length(cast(BrokerObservation.payload, Text))).where(
                BrokerObservation.account_id == account.id
            )
        )
    ).all()
    monkeypatch.setattr(journal, "READ_PAYLOAD_BUDGET", max(sizes))
    first = await read_observations(db_session, **args)
    assert len(first["observations"]) == 1 and first["truncated"]
    assert first["payload_bytes"] <= max(sizes)
    last = await read_observations(db_session, **args, cursor=first["next_cursor"])
    assert len(last["observations"]) == 1 and last["next_cursor"] is None
    monkeypatch.setattr(journal, "READ_PAYLOAD_BUDGET", min(sizes) - 1)
    with pytest.raises(PolicyDenied, match="BROKER_OBSERVATION_TOO_LARGE"):
        await read_observations(db_session, **args)


async def test_source_decimal_normalization_does_not_round_long_callback_values(db_session):
    user, account = await seed(db_session)
    args = dict(user_id=user.id, account_id=account.id)
    amount = "12345678901234567890.12345678901234567891"
    await record_observations(db_session, **args, observations=[commission(amount=amount)])
    result = await read_observations(db_session, **args)
    assert result["observations"][0]["payload"]["amount"] == amount


async def test_persisted_snapshot_changes_can_match_evidence_without_granting_authority(db_session):
    from tests.unit.broker_attribution_test import fixture_rows

    user, account = await seed(db_session)
    batch = []
    for row in fixture_rows():
        payload = {key: value for key, value in row["payload"].items() if key != "correction_family"}
        if row["kind"] == "execution":
            payload.update(client_id=77, order_id=1, permanent_id=9)
        batch.append(
            dict(
                payload,
                kind=row["kind"],
                actual_account="SYNTHETIC-ACCOUNT-ONLY",
                event_id=row["identity_sha256"],
                observed_at=row["observed_at"],
            )
        )
    args = dict(user_id=user.id, account_id=account.id)
    await record_observations(db_session, **args, observations=batch)
    result = await read_observations(db_session, **args)
    explanation = result["review"]["execution_explanation"]
    assert explanation["status"] == "observed_changes_match", explanation
    assert explanation["executions_used"] == 1 and explanation["residuals"] == []
    assert explanation["execution_authority"] == "none" and not explanation["complete_reconciliation"]
    assert result["review"]["status"] == "needs_review"
    assert "BALANCE_CHANGE_RECONCILIATION_REQUIRED" in result["review"]["reason_codes"]


@pytest.mark.parametrize(
    "exception,code,retained",
    [
        (RuntimeError, "BROKER_READ_FAILED", False),
        (TimeoutError, "BROKER_READ_TIMEOUT", True),
        (asyncio.CancelledError, "BROKER_READ_CANCELLED", True),
    ],
)
async def test_failed_refresh_has_durable_redacted_status_and_blocks_immediate_retry(
    integration_engine, monkeypatch, exception, code, retained
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.execution import broker_monitor

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        user, account = await seed(session)
    worker = AsyncMock(side_effect=exception("private provider details"))
    monkeypatch.setattr(broker_monitor, "async_session", factory)
    monkeypatch.setattr(broker_monitor, "broker_read_work", SimpleNamespace(arun=worker))
    try:
        args = dict(user_id=user.id, account_id=account.id)
        with pytest.raises(exception):
            await broker_monitor.refresh_observations(**args)
        async with factory.begin() as session:
            result = await read_observations(session, **args)
            state = result["refresh_state"]
            assert state["status"] == "failed" and state["failure_code"] == code
            assert state["last_success"] is None and state["lease_active"] is retained
            assert "private provider details" not in json.dumps(state)
            assert result["observations"] == []
            alerts = list(await session.scalars(select(OperationalAlert).where(OperationalAlert.user_id == user.id)))
            assert len(alerts) == 1
            assert alerts[0].account_id == account.id and alerts[0].rule == "broker_read_failure"
            assert alerts[0].observed_value == code and alerts[0].delivery_status == "in_app"
            assert "private provider details" not in alerts[0].message
        with pytest.raises(PolicyDenied, match="BROKER_READ_LEASED_OR_NOT_DUE"):
            await broker_monitor.refresh_observations(**args)
        assert worker.await_count == 1
    finally:
        async with factory.begin() as session:
            await session.execute(delete(JobLease).where(JobLease.user_id == user.id))
            await session.execute(delete(OperationalAlert).where(OperationalAlert.user_id == user.id))
            await session.execute(delete(BrokerAccount).where(BrokerAccount.id == account.id))
            await session.execute(delete(User).where(User.id == user.id))
