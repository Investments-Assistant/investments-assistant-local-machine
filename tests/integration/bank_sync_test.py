"""Synthetic GoCardless HTTP contract + real PostgreSQL checkpoint recovery."""

import json
import uuid
from decimal import Decimal
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from cryptography.fernet import Fernet

from src.db.models import User, ExpenseTransaction
from src.operations.models import BankSyncState
from src.expenses.providers import GoCardless, ProviderError
from src.expenses.provider_sync import (
    seal,
    disconnect,
    account_key,
    sync_account,
    begin_consent,
    choose_account,
)

pytestmark = pytest.mark.integration
ACCOUNT = "11111111-1111-4111-8111-111111111111"
REQUISITION = "22222222-2222-4222-8222-222222222222"


class Fixture:
    def __init__(self):
        self.reference = None
        self.calls = []
        self.requested_dates = []
        self.filter_dates = False
        self.fail = None
        self.status = "LN"
        self.records = {
            "booked": [
                {
                    "transactionId": "fixture-1",
                    "bookingDate": "2026-09-01",
                    "transactionAmount": {"amount": "-0.004", "currency": "EUR"},
                }
            ]
        }

    def respond(self, request):
        self.calls.append(request.url.path)
        path = request.url.path
        if path.endswith("token/new/"):
            return httpx.Response(200, json={"refresh": "fixture-refresh", "refresh_expires": 2592000})
        if path.endswith("token/refresh/"):
            return httpx.Response(200, json={"access": "fixture-access", "access_expires": 86400})
        if path.endswith("requisitions/") and request.method == "POST":
            self.reference = json.loads(request.content)["reference"]
            return httpx.Response(
                201,
                json={"id": REQUISITION, "link": "https://ob.gocardless.com/psd2/start/fixture"},
            )
        if path.endswith(REQUISITION + "/"):
            return httpx.Response(
                200,
                json={"status": self.status, "reference": self.reference, "accounts": [ACCOUNT]},
            )
        if path.endswith("transactions/"):
            self.requested_dates.append(request.url.params["date_from"])
            if self.fail:
                return httpx.Response(
                    self.fail,
                    json={"detail": "sensitive fixture provider error"},
                    headers={"Retry-After": "600"},
                )
            records = self.records
            if self.filter_dates:
                records = {
                    state: [row for row in rows if row["bookingDate"] >= request.url.params["date_from"]]
                    for state, rows in records.items()
                }
            return httpx.Response(200, json={"transactions": records})
        raise AssertionError("Unexpected provider path")


async def connected(session):
    owner = User(
        id=str(uuid.uuid4()),
        username="bank-" + uuid.uuid4().hex,
        password_hash="synthetic-non-login",
        is_active=True,
    )
    session.add(owner)
    await session.flush()
    fixture, vault = Fixture(), Fernet(Fernet.generate_key())
    provider = GoCardless(transport=httpx.MockTransport(fixture.respond))
    consent = await begin_consent(
        session,
        user_id=owner.id,
        provider=provider,
        vault=vault,
        credentials={"secret_id": "fixture-id", "secret_key": "fixture-secret"},
        institution="SANDBOXFINANCE_SFIN0000",
        redirect="https://fixture.invalid/expenses",
        human_event=True,
    )
    state_id = consent["connection_id"]
    await choose_account(
        session,
        user_id=owner.id,
        state_id=state_id,
        selected_account=ACCOUNT,
        provider=provider,
        vault=vault,
        human_event=True,
    )
    return owner.id, state_id, provider, vault, fixture


async def test_refresh_idempotency_revision_and_category_override(db_session):
    owner, state_id, provider, vault, fixture = await connected(db_session)
    args = dict(user_id=owner, state_id=state_id, provider=provider, vault=vault)
    assert (await sync_account(db_session, **args))["status"] == "complete"
    assert (await sync_account(db_session, **args))["status"] == "complete"
    rows = (
        (await db_session.execute(select(ExpenseTransaction).where(ExpenseTransaction.user_id == owner)))
        .scalars()
        .all()
    )
    assert len(rows) == 1 and rows[0].amount == Decimal("0.004")
    row = rows[0]
    row.category, row.category_override = "health", True
    await db_session.flush()
    fixture.records["booked"][0]["transactionAmount"]["amount"] = "-10.25"
    await sync_account(db_session, **args)
    await db_session.refresh(row)
    assert row.amount == Decimal("10.25") and row.category == "health"
    state = await db_session.get(BankSyncState, state_id)
    assert state.last_success_at and state.last_received_at
    assert ACCOUNT not in state.encrypted_credentials and "fixture-refresh" not in state.encrypted_credentials
    assert "token/refresh/" in " ".join(fixture.calls)


async def test_failure_does_not_advance_checkpoint_and_retry_recovers(db_session):
    owner, state_id, provider, vault, fixture = await connected(db_session)
    args = dict(user_id=owner, state_id=state_id, provider=provider, vault=vault)
    await sync_account(db_session, **args)
    state = await db_session.get(BankSyncState, state_id)
    success = state.last_success_at
    through = state.checkpoint["through"]
    fixture.fail = 429
    assert (await sync_account(db_session, **args))["error_code"] == "PROVIDER_RATE_LIMIT"
    assert state.last_success_at == success and state.checkpoint["through"] == through
    calls = len(fixture.calls)
    assert (await sync_account(db_session, **args))["status"] == "retry_wait"
    assert len(fixture.calls) == calls  # persisted backoff, no polling loop
    state.checkpoint = {
        **state.checkpoint,
        "retry_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    }
    await db_session.flush()
    fixture.fail = None
    assert (await sync_account(db_session, **args))["status"] == "complete"


async def test_invalid_batch_is_atomic_and_revoked_consent_disconnects(db_session):
    owner, state_id, provider, vault, fixture = await connected(db_session)
    args = dict(user_id=owner, state_id=state_id, provider=provider, vault=vault)
    fixture.records["booked"].append({"transactionId": "bad", "amount": -1, "date": "2026-09-01"})
    assert (await sync_account(db_session, **args))["error_code"] == "INVALID_PROVIDER_DATA"
    assert (
        not (await db_session.execute(select(ExpenseTransaction).where(ExpenseTransaction.user_id == owner)))
        .scalars()
        .all()
    )
    state = await db_session.get(BankSyncState, state_id)
    assert state.last_success_at is None
    state.checkpoint = {}
    before_revocation = len(fixture.calls)
    fixture.status = "EX"
    assert (await sync_account(db_session, **args))["status"] == "reconnect_required"
    assert not any(path.endswith("transactions/") for path in fixture.calls[before_revocation:])
    await disconnect(db_session, user_id=owner, state_id=state_id)
    assert state.encrypted_credentials is None
    with pytest.raises(ProviderError, match="BANK_CONNECTION_DISCONNECTED"):
        await sync_account(db_session, **args)


async def test_account_and_user_binding(db_session):
    owner, state_id, provider, vault, fixture = await connected(db_session)
    other = User(
        id=str(uuid.uuid4()),
        username="bank-other-" + uuid.uuid4().hex,
        password_hash="synthetic",
        is_active=True,
    )
    db_session.add(other)
    await db_session.flush()
    with pytest.raises(ProviderError, match="BANK_CONNECTION_NOT_OWNED"):
        await sync_account(db_session, user_id=other.id, state_id=state_id, provider=provider, vault=vault)
    state = await db_session.get(BankSyncState, state_id)
    state.encrypted_credentials = seal(vault, {"account_id": str(uuid.uuid4()), "refresh": "fixture-refresh"})
    assert (await sync_account(db_session, user_id=owner, state_id=state_id, provider=provider, vault=vault))[
        "error_code"
    ] == "BANK_ACCOUNT_IDENTITY_MISMATCH"
    assert state.account_key == account_key("gocardless", ACCOUNT)


async def test_reconnect_keeps_account_identity_and_checkpoint(db_session):
    owner, state_id, provider, vault, fixture = await connected(db_session)
    args = dict(user_id=owner, state_id=state_id, provider=provider, vault=vault)
    await sync_account(db_session, **args)
    state = await db_session.get(BankSyncState, state_id)
    checkpoint = dict(state.checkpoint)
    await disconnect(db_session, user_id=owner, state_id=state_id)
    consent = await begin_consent(
        db_session,
        **args,
        credentials={"secret_id": "fixture-id", "secret_key": "fixture-secret"},
        institution="SANDBOXFINANCE_SFIN0000",
        redirect="https://fixture.invalid/expenses",
        human_event=True,
    )
    assert consent["connection_id"] == state_id
    await choose_account(db_session, **args, selected_account=ACCOUNT, human_event=True)
    assert state.checkpoint == checkpoint
    assert (await sync_account(db_session, **args))["status"] == "complete"


async def test_explicit_history_recovers_old_revision_and_keeps_absent_rows(db_session):
    owner, state_id, provider, vault, fixture = await connected(db_session)
    args = dict(user_id=owner, state_id=state_id, provider=provider, vault=vault)
    await sync_account(db_session, **args)
    row = await db_session.scalar(select(ExpenseTransaction).where(ExpenseTransaction.user_id == owner))
    start = datetime.now(UTC).date() - timedelta(days=365)
    fixture.filter_dates = True
    fixture.records["booked"][0]["bookingDate"] = (datetime.now(UTC).date() - timedelta(days=120)).isoformat()
    fixture.records["booked"][0]["transactionAmount"]["amount"] = "-8.25"
    await sync_account(db_session, **args)
    await db_session.refresh(row)
    assert row.amount == Decimal("0.004")  # old correction is absent from incremental retrieval
    result = await sync_account(db_session, **args, history_from=start)
    assert result["status"] == "complete"
    assert fixture.requested_dates[-1] == start.isoformat()
    await db_session.refresh(row)
    assert row.amount == Decimal("8.25")
    state = await db_session.get(BankSyncState, state_id)
    history = dict(state.checkpoint["last_history_retrieval"])
    assert history["requested_from"] == start.isoformat()
    assert history["coverage_verified"] is False
    fixture.records = {"booked": []}
    await sync_account(db_session, **args)
    assert fixture.requested_dates[-1] == (datetime.now(UTC).date() - timedelta(days=7)).isoformat()
    assert state.checkpoint["last_history_retrieval"] == history
    assert await db_session.get(ExpenseTransaction, row.id) is not None


async def test_history_retrieval_failure_preserves_success_and_honors_backoff(db_session):
    owner, state_id, provider, vault, fixture = await connected(db_session)
    args = dict(user_id=owner, state_id=state_id, provider=provider, vault=vault)
    start = datetime.now(UTC).date() - timedelta(days=300)
    await sync_account(db_session, **args)
    await sync_account(db_session, **args, history_from=start)
    state = await db_session.get(BankSyncState, state_id)
    old = dict(state.checkpoint)
    fixture.fail = 429
    assert (await sync_account(db_session, **args, history_from=start))["status"] == "retry_wait"
    assert state.checkpoint["last_history_retrieval"] == old["last_history_retrieval"]
    assert state.checkpoint.get("through") == old.get("through")
    count = len(fixture.calls)
    assert (await sync_account(db_session, **args, history_from=start))["status"] == "retry_wait"
    assert len(fixture.calls) == count


@pytest.mark.parametrize("days", [-1, 731])
async def test_history_date_outside_local_bound_never_calls_provider(db_session, days):
    owner, state_id, provider, vault, fixture = await connected(db_session)
    count = len(fixture.calls)
    with pytest.raises(ProviderError, match="BANK_HISTORY_RANGE_INVALID"):
        await sync_account(
            db_session,
            user_id=owner,
            state_id=state_id,
            provider=provider,
            vault=vault,
            history_from=datetime.now(UTC).date() - timedelta(days=days),
        )
    assert len(fixture.calls) == count


async def test_history_owner_inactive_and_disconnected_guards(db_session):
    from src.security.sessions import SessionInactive

    owner, state_id, provider, vault, fixture = await connected(db_session)
    other, _, _, _, _ = await connected(db_session)
    args = dict(
        user_id=owner,
        state_id=state_id,
        provider=provider,
        vault=vault,
        history_from=datetime.now(UTC).date() - timedelta(days=200),
    )
    count = len(fixture.calls)
    with pytest.raises(ProviderError, match="BANK_CONNECTION_NOT_OWNED"):
        await sync_account(db_session, **(args | {"user_id": other}))
    user = await db_session.get(User, owner)
    user.is_active = False
    await db_session.flush()
    with pytest.raises(SessionInactive, match="PRINCIPAL_INACTIVE"):
        await sync_account(db_session, **args)
    user.is_active = True
    await db_session.flush()
    await disconnect(db_session, user_id=owner, state_id=state_id)
    with pytest.raises(ProviderError, match="BANK_CONNECTION_DISCONNECTED"):
        await sync_account(db_session, **args)
    assert len(fixture.calls) == count


async def test_history_invalid_batch_preserves_previous_records_and_metadata(db_session):
    owner, state_id, provider, vault, fixture = await connected(db_session)
    args = dict(
        user_id=owner,
        state_id=state_id,
        provider=provider,
        vault=vault,
        history_from=datetime.now(UTC).date() - timedelta(days=200),
    )
    await sync_account(db_session, **args)
    state = await db_session.get(BankSyncState, state_id)
    old = dict(state.checkpoint)
    fixture.records["booked"][0]["transactionAmount"]["amount"] = "-123"
    fixture.records["booked"].append({"transactionId": "invalid", "bookingDate": "2026-09-01"})
    assert (await sync_account(db_session, **args))["error_code"] == "INVALID_PROVIDER_DATA"
    row = await db_session.scalar(select(ExpenseTransaction).where(ExpenseTransaction.user_id == owner))
    assert row.amount == Decimal("0.004")
    assert state.checkpoint["last_history_retrieval"] == old["last_history_retrieval"]
    assert state.checkpoint.get("through") == old.get("through")


async def test_narrow_history_request_never_skips_incremental_cursor(db_session):
    owner, state_id, provider, vault, fixture = await connected(db_session)
    args = dict(user_id=owner, state_id=state_id, provider=provider, vault=vault)
    today = datetime.now(UTC).date()
    await sync_account(db_session, **args, history_from=today)
    state = await db_session.get(BankSyncState, state_id)
    assert "through" not in state.checkpoint
    await sync_account(db_session, **args)
    assert fixture.requested_dates[-1] == (today - timedelta(days=90)).isoformat()
    old_cursor = datetime.now(UTC) - timedelta(days=45)
    state.checkpoint = {**state.checkpoint, "through": old_cursor.isoformat()}
    await db_session.flush()
    await sync_account(db_session, **args, history_from=today)
    assert state.checkpoint["through"] == old_cursor.isoformat()
    await sync_account(db_session, **args)
    assert fixture.requested_dates[-1] == (old_cursor.date() - timedelta(days=7)).isoformat()
