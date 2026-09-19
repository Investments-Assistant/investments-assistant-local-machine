"""Real PostgreSQL export snapshots and failure trailers with synthetic expenses."""

import json
import uuid
from types import SimpleNamespace
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import delete
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.web import expense_export as export
from src.db.models import ExpenseTransaction
from src.expenses.sync import normalise_transaction
from src.expenses.persistence import upsert_transaction

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def export_fixture(integration_engine, monkeypatch):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    owner, other = str(uuid.uuid4()), str(uuid.uuid4())
    monkeypatch.setattr(export, "async_session", factory)
    monkeypatch.setattr(export, "require_authenticated", AsyncMock(return_value=SimpleNamespace(user_id=owner)))
    monkeypatch.setattr(export, "BATCH_SIZE", 2)
    async with factory.begin() as session:
        for user, count in ((owner, 5), (other, 1)):
            for index in range(count):
                item = normalise_transaction(
                    dict(
                        transactionId=str(index),
                        accountId="synthetic-bank",
                        amount="-0.004",
                        currency="EUR",
                        date="2026-09-01",
                        merchant="Fixture",
                    ),
                    "fixture",
                    "Fixture",
                )
                await upsert_transaction(session, user_id=user, item=item, received_at=datetime.now(UTC))
    try:
        yield factory, owner, other
    finally:
        async with factory.begin() as session:
            await session.execute(delete(ExpenseTransaction).where(ExpenseTransaction.user_id.in_([owner, other])))


async def response():
    return await export.export_expenses(None, date(2026, 9, 1), date(2026, 9, 30))


async def test_export_is_complete_exact_owned_and_consistent_during_concurrent_import(export_fixture):
    factory, owner, _ = export_fixture
    stream = (await response()).body_iterator
    values = []
    imported = False
    async for encoded in stream:
        value = json.loads(encoded)
        values.append(value)
        if value["kind"] == "transaction" and not imported:
            # Arrives after the repeatable-read snapshot; cannot leak into this export.
            item = normalise_transaction(
                dict(transactionId="later", amount="-99", currency="USD", date="2026-09-02", merchant="Later fixture"),
                "fixture",
                "Fixture",
            )
            async with factory.begin() as session:
                await upsert_transaction(session, user_id=owner, item=item, received_at=datetime.now(UTC))
            imported = True
    rows = [value["transaction"] for value in values if value["kind"] == "transaction"]
    assert len(rows) == 5 and len({row["id"] for row in rows}) == 5
    assert all(row["amount_exact"] == "0.0040000000" and row["signed_amount"] == "-0.004" for row in rows)
    assert all("raw_data" not in row and row["currency"] == "EUR" for row in rows)
    assert values[-1] == {"kind": "completion", "status": "complete", "records": 5}


async def test_limit_and_revocation_never_claim_complete(export_fixture, monkeypatch):
    monkeypatch.setattr(export, "MAX_RECORDS", 2)
    values = [json.loads(value) async for value in (await response()).body_iterator]
    assert values[-1]["status"] == "partial" and values[-1]["reason_code"] == "EXPORT_LIMIT"
    monkeypatch.setattr(export, "MAX_RECORDS", 100)
    checks = export.require_authenticated
    stream = (await response()).body_iterator
    assert json.loads(await anext(stream))["kind"] == "manifest"
    checks.side_effect = HTTPException(401, "Revoked fixture")
    rest = [json.loads(value) async for value in stream]
    assert not any(value["kind"] == "transaction" for value in rest)
    assert rest[-1]["status"] == "partial" and rest[-1]["reason_code"] == "EXPORT_INTERRUPTED"


async def test_other_owner_exports_only_their_rows(export_fixture, monkeypatch):
    _, _, other = export_fixture
    monkeypatch.setattr(export, "require_authenticated", AsyncMock(return_value=SimpleNamespace(user_id=other)))
    values = [json.loads(value) async for value in (await response()).body_iterator]
    assert values[-1]["records"] == 1
