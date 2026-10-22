"""Committed offline handoffs on a marked PostgreSQL fixture; no SDK/network.

Unlike outer-rollback fixtures, these tests exercise independent transactions so
the synthetic transport can prove the attempt was durable before it was called.
"""

import uuid
import asyncio
from datetime import UTC, datetime, timedelta
from contextlib import suppress

import pytest
from sqlalchemy import delete, select, update
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.tools import broker_accounts as vault
from src.db.models import User, BrokerAccount, BrokerObservation
from src.execution.policy import PolicyDenied
from src.execution.broker_submission import MAX_OFFLINE_HANDOFFS, TransportReceipt, BrokerSubmissionJournal
from src.execution.broker_observations import record_observations
from tests.unit.broker_submission_test import request_values
from src.execution.broker_submission_models import BrokerSubmissionEvent, BrokerSubmissionIntent
from tests.integration.broker_observations_test import seed, execution, commission, fixture_key  # noqa: F401

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(loop_scope="function")
async def submission_fixture(integration_engine):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        user, account = await seed(session)
    journal = BrokerSubmissionJournal(factory)
    try:
        yield journal, factory, user.id, account.id
    finally:
        # Only this freshly seeded owner's records; the integration fixture proved
        # database identity before any schema mutation and never targets .env.
        if journal._unfinished:
            await asyncio.wait_for(asyncio.gather(*journal._unfinished, return_exceptions=True), 5)
        async with factory.begin() as session:
            ids = select(BrokerSubmissionIntent.id).where(BrokerSubmissionIntent.account_id == account.id)
            await session.execute(delete(BrokerSubmissionEvent).where(BrokerSubmissionEvent.intent_id.in_(ids)))
            await session.execute(delete(BrokerSubmissionIntent).where(BrokerSubmissionIntent.account_id == account.id))
            await session.execute(delete(BrokerObservation).where(BrokerObservation.account_id == account.id))
            await session.execute(delete(BrokerAccount).where(BrokerAccount.id == account.id))
            await session.execute(delete(User).where(User.id == user.id))


async def stage(fixture, **changes):
    journal, _, user, account = fixture
    return await journal.stage_intent(user_id=user, account_id=account, idempotency_key="fixture-order",
                                      request=request_values(**changes))


def args(fixture, intent):
    return dict(user_id=fixture[2], account_id=fixture[3], intent_id=intent["intent_id"])


class AcceptedTransport:
    """The only transport implementation is synthetic and lives in tests."""

    def __init__(self, factory):
        self.factory, self.calls = factory, 0

    async def submit(self, request, *, intent_id, attempt_id):
        self.calls += 1
        # A distinct session/connection sees both committed intent and attempt.
        async with self.factory() as independent:
            intent = await independent.get(BrokerSubmissionIntent, intent_id)
            event = await independent.scalar(select(BrokerSubmissionEvent).where(
                BrokerSubmissionEvent.intent_id == intent_id, BrokerSubmissionEvent.kind == "handoff_started",
            ))
            assert intent.state == "handoff_started" and intent.attempt_id == attempt_id
            assert event.payload["request_sha256"] == intent.request_sha256
        return TransportReceipt(status="acknowledged", client_id=request.client_id,
                                order_id=request.order_id, permanent_id=9)


async def test_committed_handoff_concurrent_claim_and_reload_invoke_transport_once(submission_fixture):
    fixture = submission_fixture
    journal, factory, user, account = fixture
    staged = await asyncio.gather(*(stage(fixture) for _ in range(2)))
    assert staged[0]["intent_id"] == staged[1]["intent_id"]
    transport = AcceptedTransport(factory)
    results = await asyncio.gather(*(journal.dispatch_once(**args(fixture, staged[0]), transport=transport,
                                                          timeout_seconds=5) for _ in range(2)))
    assert transport.calls == 1
    assert all(result["retry_allowed"] is False and result["execution_authority"] == "none" for result in results)
    restarted = BrokerSubmissionJournal(factory)
    again = await restarted.dispatch_once(user_id=user, account_id=account, intent_id=staged[0]["intent_id"],
                                         transport=transport, timeout_seconds=5)
    assert again["state"] == "acknowledged" and transport.calls == 1
    assert again["environment_verified"] is None and again["scope"] == "offline_contract"


async def test_idempotency_conflict_and_broker_id_reservation_are_persistent(submission_fixture):
    fixture = submission_fixture
    journal, _, user, account = fixture
    await stage(fixture)
    with pytest.raises(PolicyDenied, match="SUBMISSION_IDEMPOTENCY_CONFLICT"):
        await stage(fixture, quantity="0.005")
    with pytest.raises(PolicyDenied, match="SUBMISSION_BROKER_ID_ALREADY_RESERVED"):
        await journal.stage_intent(user_id=user, account_id=account, idempotency_key="different-intent",
                                   request=request_values())


@pytest.mark.parametrize("key", ["", "x" * 65, "with spaces", True])
async def test_invalid_keys_never_create_journal_records(submission_fixture, key):
    journal, factory, user, account = submission_fixture
    with pytest.raises(PolicyDenied, match="INVALID_SUBMISSION_KEY"):
        await journal.stage_intent(user_id=user, account_id=account, idempotency_key=key, request=request_values())
    async with factory() as session:
        assert not (await session.scalars(select(BrokerSubmissionIntent).where(
            BrokerSubmissionIntent.account_id == account))).all()


async def test_default_dispatch_denies_without_injected_transport(submission_fixture, monkeypatch):
    fixture = submission_fixture
    intent = await stage(fixture)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.delenv("TEST_DATABASE_DISPOSABLE_TOKEN")
    result = await fixture[0].dispatch_once(**args(fixture, intent))
    assert result["state"] == "blocked" and result["attempt_id"] is None
    async with fixture[1]() as session:
        events = (await session.scalars(select(BrokerSubmissionEvent).where(
            BrokerSubmissionEvent.intent_id == intent["intent_id"]))).all()
        assert [event.kind for event in events] == ["staged"]
        assert result["reason_code"] == "EXTERNAL_WRITES_NOT_AUTHORIZED"


@pytest.mark.parametrize("change", ["absent_marker", "wrong_marker", "different_database"])
async def test_injected_transport_requires_actual_disposable_database(submission_fixture, monkeypatch, change):
    fixture = submission_fixture
    intent = await stage(fixture)
    transport = AcceptedTransport(fixture[1])
    if change == "absent_marker":
        monkeypatch.delenv("TEST_DATABASE_DISPOSABLE_TOKEN")
    elif change == "wrong_marker":
        monkeypatch.setenv("TEST_DATABASE_DISPOSABLE_TOKEN", "wrong-fixture-marker-123456789")
    else:
        monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+asyncpg://fixture@127.0.0.1:1/test_other")
    with pytest.raises(PolicyDenied, match="OFFLINE_.*DATABASE"):
        await fixture[0].dispatch_once(**args(fixture, intent), transport=transport, timeout_seconds=5)
    assert transport.calls == 0
    async with fixture[1]() as session:
        assert (await session.get(BrokerSubmissionIntent, intent["intent_id"])).state == "staged"


@pytest.mark.parametrize("change,code", [
    ("owner", "PRINCIPAL_INACTIVE"), ("account", "BROKER_ACCOUNT_INACTIVE"),
    ("revoke", "IBKR_READ_CONSENT_REQUIRED"), ("binding", "SUBMISSION_ACCOUNT_CHANGED"),
    ("endpoint", "SUBMISSION_ACCOUNT_CHANGED"),
])
async def test_scope_rechecked_before_handoff_and_cross_owner_denied(submission_fixture, change, code):
    fixture = submission_fixture
    journal, factory, user, account = fixture
    intent = await stage(fixture)
    transport = AcceptedTransport(factory)
    with pytest.raises(PolicyDenied, match="SUBMISSION_NOT_OWNED"):
        await journal.dispatch_once(**(args(fixture, intent) | {"user_id": str(uuid.uuid4())}),
                                     transport=transport, timeout_seconds=5)
    async with factory.begin() as session:
        row = await session.get(BrokerAccount, account)
        if change == "owner":
            await session.execute(update(User).where(User.id == user).values(is_active=False))
        elif change == "account":
            row.is_active = False
        else:
            config = vault.decrypt_config(row.config_encrypted)
            edits = {"revoke": {"read_authorized": False}, "binding": {"broker_account_id": "OTHER-FIXTURE"},
                     "endpoint": {"host": "different.invalid"}}
            row.config_encrypted = vault.encrypt_config(config | edits[change])
    with pytest.raises(PolicyDenied, match=code):
        await journal.dispatch_once(**args(fixture, intent), transport=transport, timeout_seconds=5)
    assert transport.calls == 0


async def test_revocation_after_committed_attempt_is_checked_before_call(submission_fixture, monkeypatch):
    fixture = submission_fixture
    journal, factory, _, account = fixture
    intent = await stage(fixture)
    verify = journal._fixture
    passes = 0

    async def revoke_after_claim():
        nonlocal passes
        await verify()
        passes += 1
        if passes == 2:
            async with factory.begin() as session:
                row = await session.get(BrokerAccount, account)
                row.config_encrypted = vault.encrypt_config(vault.decrypt_config(row.config_encrypted)
                                                           | {"read_authorized": False})

    monkeypatch.setattr(journal, "_fixture", revoke_after_claim)
    transport = AcceptedTransport(factory)
    with pytest.raises(PolicyDenied, match="IBKR_READ_CONSENT_REQUIRED"):
        await journal.dispatch_once(**args(fixture, intent), transport=transport, timeout_seconds=5)
    assert transport.calls == 0
    async with factory() as session:
        assert (await session.get(BrokerSubmissionIntent, intent["intent_id"])).state == "handoff_started"


async def test_revocation_during_transport_prevents_late_acknowledgement_persistence(submission_fixture):
    fixture = submission_fixture
    journal, factory, user, _ = fixture
    intent = await stage(fixture)

    class RevokingTransport(AcceptedTransport):
        async def submit(self, request, **kwargs):
            receipt = await super().submit(request, **kwargs)
            async with factory.begin() as session:
                await session.execute(update(User).where(User.id == user).values(is_active=False))
            return receipt

    transport = RevokingTransport(factory)
    with pytest.raises(PolicyDenied, match="PRINCIPAL_INACTIVE"):
        await journal.dispatch_once(**args(fixture, intent), transport=transport, timeout_seconds=5)
    async with factory() as session:
        row = await session.get(BrokerSubmissionIntent, intent["intent_id"])
        assert row.state == "handoff_started" and row.permanent_id is None
        assert not await session.scalar(select(BrokerSubmissionEvent.id).where(
            BrokerSubmissionEvent.intent_id == row.id, BrokerSubmissionEvent.kind == "acknowledged"))


@pytest.mark.parametrize("mode", ["timeout", "exception", "bad_receipt", "cancel"])
async def test_uncertain_handoff_survives_restart_without_resubmission(submission_fixture, mode):
    fixture = submission_fixture
    journal, factory, _, _ = fixture
    intent = await stage(fixture)
    entered = asyncio.Event()

    class UncertainTransport(AcceptedTransport):
        async def submit(self, request, **kwargs):
            receipt = await super().submit(request, **kwargs)
            entered.set()
            if mode in {"timeout", "cancel"}:
                await asyncio.Event().wait()
            if mode == "exception":
                raise RuntimeError("must-not-be-persisted-secret")
            return {"success": True} if mode == "bad_receipt" else receipt

    transport = UncertainTransport(factory)
    if mode == "cancel":
        task = asyncio.create_task(journal.dispatch_once(**args(fixture, intent), transport=transport,
                                                        timeout_seconds=5))
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await journal.dispatch_once(**args(fixture, intent), transport=transport,
                                             timeout_seconds=0.05 if mode == "timeout" else 5)
        assert result["state"] == "uncertain"
    restarted = BrokerSubmissionJournal(factory)
    result = await restarted.dispatch_once(**args(fixture, intent), transport=transport, timeout_seconds=5)
    assert result["state"] == "uncertain" and transport.calls == 1
    async with factory() as session:
        payloads = (await session.scalars(select(BrokerSubmissionEvent.payload).where(
            BrokerSubmissionEvent.intent_id == intent["intent_id"]))).all()
        assert "must-not-be-persisted-secret" not in str(payloads)


async def test_explicit_crash_recovery_and_late_result_never_rearm_handoff(submission_fixture):
    fixture = submission_fixture
    journal, factory, _, _ = fixture
    intent = await stage(fixture)
    entered, release = asyncio.Event(), asyncio.Event()

    class Delayed(AcceptedTransport):
        async def submit(self, request, **kwargs):
            receipt = await super().submit(request, **kwargs)
            entered.set()
            await release.wait()
            return receipt

    transport = Delayed(factory)
    task = asyncio.create_task(journal.dispatch_once(**args(fixture, intent), transport=transport, timeout_seconds=5))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        restarted = BrokerSubmissionJournal(factory)
        recovered = await restarted.recover_uncertain(**args(fixture, intent))
        assert recovered["state"] == "uncertain"
        release.set()
        assert (await asyncio.wait_for(task, 5))["state"] == "uncertain"
        assert (await restarted.dispatch_once(**args(fixture, intent), transport=transport,
                                             timeout_seconds=5))["state"] == "uncertain"
        assert transport.calls == 1
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


def order_status(status="Filled", **changes):
    return dict(kind="order_status", actual_account="SYNTHETIC-ACCOUNT-ONLY", event_id="fixture.status",
                client_id=77, order_id=1, permanent_id=9, status=status, filled="0.004", remaining="0",
                observed_at=datetime.now(UTC) - timedelta(seconds=1)) | changes


async def retain(fixture, observations):
    async with fixture[1].begin() as session:
        await record_observations(session, user_id=fixture[2], account_id=fixture[3], observations=observations)
    async with fixture[1]() as session:
        return (await session.scalars(select(BrokerObservation).where(
            BrokerObservation.account_id == fixture[3]).order_by(BrokerObservation.recorded_at))).all()


async def test_callback_links_reuse_existing_review_without_ownership_or_fill_claims(submission_fixture):
    fixture = submission_fixture
    journal, factory, _, _ = fixture
    intent = await stage(fixture)
    await journal.dispatch_once(**args(fixture, intent), transport=AcceptedTransport(factory), timeout_seconds=5)
    rows = await retain(fixture, [commission(), execution(), order_status(), order_status("Cancelled")])
    fee = next(row for row in rows if row.kind == "commission")
    with pytest.raises(PolicyDenied, match="SUBMISSION_LINKED_EXECUTION_REQUIRED"):
        await journal.attach_observation(**args(fixture, intent), observation_id=fee.id)
    for row in [row for row in rows if row.kind != "commission"] + [fee]:
        await journal.attach_observation(**args(fixture, intent), observation_id=row.id)
        await journal.attach_observation(**args(fixture, intent), observation_id=row.id)
    review = await BrokerSubmissionJournal(factory).review_intent(**args(fixture, intent))
    assert review["linked_observations"] == 4 and review["state"] == "acknowledged"
    assert "ORDER_TERMINAL_STATUS_CONFLICT" in review["review"]["reason_codes"]
    assert review["review"]["counts"]["executions_without_commission"] == 0
    assert review["review"]["order_lifecycle"]["orders"][0]["execution_quantity"] == "0.004"
    assert review["strategy_order_ownership"] == review["current_broker_state"] == "not_established"
    assert review["execution_authority"] == "none" and review["complete_reconciliation"] is False
    assert "SYNTHETIC-ACCOUNT-ONLY" not in str(review)
    async with factory() as session:
        linked = (await session.scalars(select(BrokerSubmissionEvent).where(
            BrokerSubmissionEvent.intent_id == intent["intent_id"],
            BrokerSubmissionEvent.kind == "observation_linked"))).all()
        assert len(linked) == 4


@pytest.mark.parametrize("change", [{"permanent_id": 10}, {"client_id": 78}, {"order_id": 2}])
async def test_unrelated_callbacks_cannot_be_assigned_to_intent(submission_fixture, change):
    fixture = submission_fixture
    intent = await stage(fixture)
    await fixture[0].dispatch_once(**args(fixture, intent), transport=AcceptedTransport(fixture[1]), timeout_seconds=5)
    row, = await retain(fixture, [execution(**change)])
    with pytest.raises(PolicyDenied, match="SUBMISSION_STABLE_BROKER_ID_REQUIRED"):
        await fixture[0].attach_observation(**args(fixture, intent), observation_id=row.id)


async def test_uncertain_identity_and_corrupted_request_fail_closed(submission_fixture):
    fixture = submission_fixture
    intent = await stage(fixture)
    row, = await retain(fixture, [order_status()])
    with pytest.raises(PolicyDenied, match="SUBMISSION_STABLE_BROKER_ID_REQUIRED"):
        await fixture[0].attach_observation(**args(fixture, intent), observation_id=row.id)
    async with fixture[1].begin() as session:
        stored = await session.get(BrokerSubmissionIntent, intent["intent_id"])
        stored.request = stored.request | {"quantity": "0.005"}
    transport = AcceptedTransport(fixture[1])
    with pytest.raises(PolicyDenied, match="SUBMISSION_REQUEST_CHANGED"):
        await fixture[0].dispatch_once(**args(fixture, intent), transport=transport, timeout_seconds=5)
    assert transport.calls == 0


async def test_history_remains_available_after_read_revocation_and_configuration_rotation(submission_fixture):
    fixture = submission_fixture
    journal, factory, _, account = fixture
    intent = await stage(fixture)

    class Revoking(AcceptedTransport):
        async def submit(self, request, **kwargs):
            receipt = await super().submit(request, **kwargs)
            async with factory.begin() as session:
                row = await session.get(BrokerAccount, account)
                row.config_encrypted = vault.encrypt_config(vault.decrypt_config(row.config_encrypted) | {
                    "enabled": False, "read_authorized": False, "client_id": 99, "host": "rotated.invalid",
                })
            return receipt

    result = await journal.dispatch_once(**args(fixture, intent), transport=Revoking(factory), timeout_seconds=5)
    assert result["state"] == "uncertain" and result["broker_identity_resolution"].startswith("permanent_id_unknown")
    recovered = await journal.recover_uncertain(**args(fixture, intent))
    review = await journal.review_intent(**args(fixture, intent))
    assert recovered["state"] == review["state"] == "uncertain"
    assert review["execution_authority"] == "none" and review["linked_observations"] == 0
    async with factory() as session:
        row = await session.get(BrokerSubmissionIntent, intent["intent_id"])
        assert row.permanent_id is None
        event = await session.scalar(select(BrokerSubmissionEvent).where(
            BrokerSubmissionEvent.intent_id == row.id, BrokerSubmissionEvent.kind == "uncertain"))
        assert event.payload["reason_code"] == "SUBMISSION_SCOPE_LOST_DURING_HANDOFF"


async def test_timeout_candidate_callback_never_guesses_missing_permanent_identity(submission_fixture):
    fixture = submission_fixture
    intent = await stage(fixture)

    class Unknown(AcceptedTransport):
        async def submit(self, request, **kwargs):
            await super().submit(request, **kwargs)  # Synthetic broker accepted, client never received its receipt.
            raise TimeoutError("accepted-but-unknown")

    result = await fixture[0].dispatch_once(**args(fixture, intent), transport=Unknown(fixture[1]), timeout_seconds=5)
    assert result["state"] == "uncertain"
    row, = await retain(fixture, [order_status()])
    with pytest.raises(PolicyDenied, match="SUBMISSION_STABLE_BROKER_ID_REQUIRED"):
        await fixture[0].attach_observation(**args(fixture, intent), observation_id=row.id)
    assert (await fixture[0].review_intent(**args(fixture, intent)))["linked_observations"] == 0


async def test_stubborn_coroutines_hold_bounded_capacity_without_new_attempts(submission_fixture):
    fixture = submission_fixture
    journal, factory, user, account = fixture
    release = asyncio.Event()

    class Stubborn:
        calls = 0

        async def submit(self, request, **_):
            self.calls += 1
            while not release.is_set():
                # Reproduces a native-like operation that has not stopped yet.
                with suppress(asyncio.CancelledError):
                    await release.wait()
            return TransportReceipt(status="acknowledged", client_id=request.client_id,
                                    order_id=request.order_id, permanent_id=9)

    transport = Stubborn()
    try:
        for index in range(MAX_OFFLINE_HANDOFFS):
            intent = await journal.stage_intent(user_id=user, account_id=account, idempotency_key=f"capacity-{index}",
                                                request=request_values(order_id=index))
            result = await journal.dispatch_once(**args(fixture, intent), transport=transport, timeout_seconds=0.05)
            assert result["state"] == "uncertain"
        extra = await journal.stage_intent(user_id=user, account_id=account, idempotency_key="capacity-overflow",
                                           request=request_values(order_id=MAX_OFFLINE_HANDOFFS))
        with pytest.raises(PolicyDenied, match="OFFLINE_HANDOFF_CAPACITY"):
            await BrokerSubmissionJournal(factory).dispatch_once(**args(fixture, extra), transport=transport,
                                                                 timeout_seconds=5)
        assert transport.calls == MAX_OFFLINE_HANDOFFS and len(journal._unfinished) == MAX_OFFLINE_HANDOFFS
        async with factory() as session:
            stored = await session.get(BrokerSubmissionIntent, extra["intent_id"])
            assert stored.state == "staged" and stored.attempt_id is None
    finally:
        release.set()
        if journal._unfinished:
            await asyncio.wait_for(asyncio.gather(*journal._unfinished, return_exceptions=True), 5)


@pytest.mark.parametrize("changes,reason", [
    ({"con_id": 999}, "SUBMISSION_EXECUTION_CONTRACT_MISMATCH"),
    ({"side": "SLD"}, "SUBMISSION_EXECUTION_CONTRACT_MISMATCH"),
    ({"currency": "USD"}, "SUBMISSION_EXECUTION_CONTRACT_MISMATCH"),
    ({"security_type": "OPT", "multiplier": "100"}, "SUBMISSION_EXECUTION_CONTRACT_MISMATCH"),
    ({"security_type": None, "multiplier": None}, "SUBMISSION_CONTRACT_EVIDENCE_INCOMPLETE"),
    ({"quantity": "0.005"}, "SUBMISSION_QUANTITY_EXCEEDED"),
    ({"price": "101"}, "SUBMISSION_LIMIT_PRICE_BREACH"),
])
async def test_matching_broker_identity_retains_request_discrepancies(submission_fixture, changes, reason):
    fixture = submission_fixture
    intent = await stage(fixture)
    await fixture[0].dispatch_once(**args(fixture, intent), transport=AcceptedTransport(fixture[1]), timeout_seconds=5)
    event = execution(**(dict(security_type="STK", multiplier="1") | changes))
    rows = await retain(fixture, [event, order_status(filled=event["quantity"])])
    for row in rows:
        await fixture[0].attach_observation(**args(fixture, intent), observation_id=row.id)
    result = await fixture[0].review_intent(**args(fixture, intent))
    assert result["linked_observations"] == 2 and result["review"]["status"] == "needs_review"
    assert reason in result["review"]["reason_codes"]
    assert result["review"]["execution_authority"] == "none"
    assert result["complete_reconciliation"] is False


async def test_sell_limit_and_distinct_cumulative_overfills_are_detected(submission_fixture):
    fixture = submission_fixture
    intent = await stage(fixture, side="sell")
    await fixture[0].dispatch_once(**args(fixture, intent), transport=AcceptedTransport(fixture[1]), timeout_seconds=5)
    first = execution(side="SLD", price="99", quantity="0.003", security_type="STK", multiplier="1",
                      event_id="fixture.first.1")
    second = execution(side="SLD", price="100", quantity="0.003", security_type="STK", multiplier="1",
                       event_id="fixture.second.1")
    rows = await retain(fixture, [first, first, second, order_status(filled="0.006")])
    for row in rows:
        await fixture[0].attach_observation(**args(fixture, intent), observation_id=row.id)
    result = await fixture[0].review_intent(**args(fixture, intent))
    assert result["linked_observations"] == 3
    comparison = result["review"]["request_comparison"]
    assert comparison["observed_execution_quantity"] == "0.006"
    assert {"SUBMISSION_QUANTITY_EXCEEDED", "SUBMISSION_LIMIT_PRICE_BREACH"} <= set(comparison["reason_codes"])


async def test_correction_family_quantities_are_not_summed_as_fresh_fills(submission_fixture):
    fixture = submission_fixture
    intent = await stage(fixture)
    await fixture[0].dispatch_once(**args(fixture, intent), transport=AcceptedTransport(fixture[1]), timeout_seconds=5)
    rows = await retain(fixture, [execution(event_id="fixture.correction.1", security_type="STK", multiplier="1"),
                                  execution(event_id="fixture.correction.2", security_type="STK", multiplier="1"),
                                  order_status()])
    for row in rows:
        await fixture[0].attach_observation(**args(fixture, intent), observation_id=row.id)
    comparison = (await fixture[0].review_intent(**args(fixture, intent)))["review"]["request_comparison"]
    assert comparison["observed_execution_quantity"] is None
    assert "SUBMISSION_EXECUTION_QUANTITY_UNRESOLVED" in comparison["reason_codes"]
    assert "SUBMISSION_QUANTITY_EXCEEDED" not in comparison["reason_codes"]
