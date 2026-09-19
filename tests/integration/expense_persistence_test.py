"""Concurrent import/provider writes share atomic user/account transaction identity."""

import uuid
import asyncio
from decimal import Decimal
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models import User, ExpenseTransaction
from src.expenses.sync import normalise_transaction
from src.expenses.persistence import upsert_transaction

pytestmark = pytest.mark.integration


async def test_concurrent_import_counts_and_override_preservation(integration_engine):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    user_id = str(uuid.uuid4())
    item = normalise_transaction(
        dict(
            transactionId="duplicate",
            accountId="fixture-bank",
            amount="-12.30",
            currency="EUR",
            date="2026-09-09",
            merchant="Cafe fixture",
        ),
        "manual",
        "Fixture",
    )
    async with factory.begin() as session:
        session.add(
            User(id=user_id, username=uuid.uuid4().hex, password_hash="fixture", is_active=True)
        )
    try:

        async def write():
            async with factory.begin() as session:
                return await upsert_transaction(
                    session, user_id=user_id, item=item, received_at=datetime.now(UTC)
                )

        inserted = await asyncio.gather(write(), write())
        assert sorted(inserted) == [False, True]
        async with factory.begin() as session:
            row = (
                await session.execute(
                    select(ExpenseTransaction).where(ExpenseTransaction.user_id == user_id)
                )
            ).scalar_one()
            row.category, row.subcategory, row.category_override = "education", "books", True
        revised = dict(
            item,
            category="food",
            subcategory="restaurants",
            amount=Decimal("13.40"),
            lifecycle="revised",
        )
        async with factory.begin() as session:
            assert (
                await upsert_transaction(
                    session, user_id=user_id, item=revised, received_at=datetime.now(UTC)
                )
                is False
            )
        async with factory() as session:
            row = (
                await session.execute(
                    select(ExpenseTransaction).where(ExpenseTransaction.user_id == user_id)
                )
            ).scalar_one()
            assert (row.category, row.subcategory) == ("education", "books")
            assert row.amount == Decimal("13.40") and row.lifecycle == "revised"
    finally:
        async with factory.begin() as session:
            await session.execute(
                delete(ExpenseTransaction).where(ExpenseTransaction.user_id == user_id)
            )
            await session.execute(delete(User).where(User.id == user_id))


async def test_category_edit_is_scoped_and_audited_without_bank_payload(db_session, monkeypatch):
    from types import SimpleNamespace
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    from fastapi import HTTPException

    from src.expenses.models import ExpenseAudit
    from src.web.expense_routes import CategoryInput, set_category

    class Factory:
        @asynccontextmanager
        async def begin(self):
            yield db_session

    owner = str(uuid.uuid4())
    transaction = ExpenseTransaction(
        user_id=owner,
        **normalise_transaction(
            dict(
                transactionId="category-fixture",
                amount="-5",
                currency="EUR",
                date="2026-09-09",
                merchant="Fixture",
            ),
            "manual",
            "Fixture",
        ),
    )
    db_session.add(transaction)
    await db_session.flush()
    monkeypatch.setattr("src.web.expense_routes.async_session", Factory())
    principal = SimpleNamespace(user_id=owner, mechanism="cookie")
    monkeypatch.setattr(
        "src.web.expense_routes.require_authenticated", AsyncMock(return_value=principal)
    )
    # Authentication itself is exercised in real Chromium; this test verifies the data boundary.
    await set_category(transaction.id, CategoryInput(category="work"), None)
    await set_category(transaction.id, CategoryInput(category="work"), None)
    audits = (
        (await db_session.execute(select(ExpenseAudit).where(ExpenseAudit.user_id == owner)))
        .scalars()
        .all()
    )
    assert len(audits) == 1
    assert audits[0].changes["after"]["category"] == "work"
    assert set(audits[0].changes["after"]) == {"category", "subcategory", "override"}
    principal.user_id = "other-authenticated-fixture"
    with pytest.raises(HTTPException) as exc:
        await set_category(transaction.id, CategoryInput(category="food"), None)
    assert exc.value.status_code == 404
    assert transaction.category == "work" and transaction.category_override


async def test_sync_clocks_are_owner_scoped_and_independent_of_transaction_page(db_session):
    from datetime import timedelta

    from src.expenses.status import sync_clocks
    from src.operations.models import BankSyncState

    owner, other = str(uuid.uuid4()), str(uuid.uuid4())
    received = datetime(2026, 9, 1, tzinfo=UTC)
    success = received + timedelta(days=1)
    db_session.add_all(
        [
            BankSyncState(
                user_id=owner,
                provider="gocardless",
                account_key="fixture-a",
                status="retry_wait",
                last_received_at=received,
                last_success_at=success,
            ),
            BankSyncState(
                user_id=other,
                provider="gocardless",
                account_key="fixture-b",
                status="connected",
                last_received_at=success + timedelta(days=2),
                last_success_at=success + timedelta(days=2),
            ),
        ]
    )
    await db_session.flush()
    # Zero transactions does not erase successful provider fetches of empty batches.
    clocks = await sync_clocks(db_session, owner)
    assert clocks["last_received_at"] == received.isoformat()
    assert clocks["provider_last_success_at"] == success.isoformat()
    missing = await sync_clocks(db_session, str(uuid.uuid4()))
    assert missing["provider_last_success_at"] is None and missing["last_received_at"] is None
    # A later manual import changes application receipt, never bank-success time.
    item = normalise_transaction(
        dict(
            transactionId="clock-fixture",
            amount="-1",
            currency="EUR",
            date="2020-01-01",
            merchant="Fixture",
        ),
        "manual",
        "Fixture",
    )
    later = success + timedelta(days=1)
    await upsert_transaction(db_session, user_id=owner, item=item, received_at=later)
    clocks = await sync_clocks(db_session, owner)
    assert clocks["last_received_at"] == later.isoformat()
    assert clocks["provider_last_success_at"] == success.isoformat()
