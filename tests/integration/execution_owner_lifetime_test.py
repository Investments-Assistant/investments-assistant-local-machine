"""Authorization remains valid while an execution transaction waits for its account."""

import asyncio

import pytest
from sqlalchemy import text, delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models import User
from src.execution.models import SimulatorAccount, SimulatorInstrument
from src.execution.policy import PolicyDenied
from src.execution.service import account_for_user
from tests.integration.execution_test import seed

pytestmark = pytest.mark.integration


async def test_deactivation_cannot_overtake_authorized_account_lock_wait(integration_engine):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        ids = await seed(session)
    checked = asyncio.Event()
    worker = None

    async def authorize():
        async with factory.begin() as session:
            scalar = session.scalar

            async def observed(statement, *args, **kwargs):
                result = await scalar(statement, *args, **kwargs)
                if "FROM users" in str(statement):
                    checked.set()
                return result

            session.scalar = observed
            account = await account_for_user(session, ids[1], ids[0])
            return account.id

    try:
        async with factory.begin() as locker:
            await locker.scalar(select(SimulatorAccount).where(SimulatorAccount.id == ids[1]).with_for_update())
            worker = asyncio.create_task(authorize())
            await asyncio.wait_for(checked.wait(), 5)
            # This cannot commit while the already-authorized worker is waiting
            # for its account: otherwise that worker uses revoked authority later.
            with pytest.raises(DBAPIError):
                async with factory.begin() as deactivation:
                    await deactivation.execute(text("SET LOCAL lock_timeout = '200ms'"))
                    await deactivation.execute(update(User).where(User.id == ids[0]).values(is_active=False))
        assert await asyncio.wait_for(worker, 5) == ids[1]
        async with factory.begin() as session:
            await session.execute(update(User).where(User.id == ids[0]).values(is_active=False))
        async with factory.begin() as session:
            with pytest.raises(PolicyDenied, match="PRINCIPAL_INACTIVE"):
                await account_for_user(session, ids[1], ids[0])
    finally:
        if worker is not None:
            if not worker.done():
                worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        async with factory.begin() as session:
            await session.execute(delete(SimulatorInstrument).where(SimulatorInstrument.id == ids[2]))
            await session.execute(delete(SimulatorAccount).where(SimulatorAccount.id == ids[1]))
            await session.execute(delete(User).where(User.id == ids[0]))
