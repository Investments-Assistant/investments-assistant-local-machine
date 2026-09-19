"""Integration fixtures refuse databases without an explicit disposable marker."""

from __future__ import annotations

import os
import re

import pytest
from sqlalchemy import text
import pytest_asyncio
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.db.models import Base


@pytest.fixture(scope="session")
def integration_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    marker = os.environ.get("TEST_DATABASE_DISPOSABLE_TOKEN")
    if not url or not marker:
        pytest.fail("Explicit TEST_DATABASE_URL and disposable marker token are required")
    parsed = make_url(url)
    if not re.fullmatch(r"test_[a-z0-9_]+", parsed.database or ""):
        pytest.fail("Disposable database name must begin with test_")
    if parsed.drivername != "postgresql+asyncpg":
        pytest.fail("Integration requires real PostgreSQL through asyncpg")
    return url


@pytest_asyncio.fixture(loop_scope="function")
async def integration_engine(integration_db_url):
    """One loop owns engine lifetime. Prove identity before schema mutations."""
    engine = create_async_engine(integration_db_url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            database = await conn.scalar(text("SELECT current_database()"))
            if database != make_url(integration_db_url).database:
                pytest.fail("Unexpected connected database identity")
            token = await conn.scalar(text("SELECT token FROM public.ia_disposable_marker"))
            if token != os.environ["TEST_DATABASE_DISPOSABLE_TOKEN"]:
                pytest.fail("Database disposable marker does not match this test run")
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        # No DROP TABLE needed. Every test uses an outer rollback transaction.
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="function")
async def db_session(integration_engine):
    async with integration_engine.connect() as connection:
        outer = await connection.begin()
        session = AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()
