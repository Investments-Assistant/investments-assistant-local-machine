"""Explicit read refresh: bounded worker, then freshly authorized persistence."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import text, select

from src.db.models import User
from src.db.database import async_session
from src.execution.policy import PolicyDenied
from src.operations.alerts import emit
from src.agent.utils.logger import get_logger
from src.operations.workloads import WorkPool
from src.tools.broker_accounts import BrokerAccountConfig
from src.execution.broker_observations import selected_account, read_observations, record_observations
from src.execution.broker_refresh_state import begin_refresh, finish_refresh
from src.tools.brokers.ibkr_observations import collect_ibkr_observations

broker_read_work = WorkPool(1, "BROKER_OBSERVATION")
logger = get_logger(__name__)


async def refresh_observations(*, user_id, account_id):
    """No implicit scheduler, write, cloud fallback, or retry after uncertain work.

    Cancellation retains worker admission until native reads finish, and never
    persists a cancelled request's later result. The next explicit refresh may
    recover broker-visible facts, subject to broker history-window limitations.
    """
    async with asyncio.timeout(10), async_session.begin() as session:
        await session.execute(text("SET LOCAL lock_timeout = '2s'"))
        await session.execute(text("SET LOCAL statement_timeout = '5s'"))
        config, binding = await selected_account(session, user_id=user_id, account_id=account_id)
        selected = BrokerAccountConfig(account_id, user_id, "ibkr", "Selected account", config)
        lease = await begin_refresh(session, user_id=user_id, account_id=account_id)
    try:
        window = await broker_read_work.arun(collect_ibkr_observations, selected, timeout=40)
        async with asyncio.timeout(10), async_session.begin() as session:
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            _, current_binding = await selected_account(session, user_id=user_id, account_id=account_id)
            if current_binding != binding:
                raise PolicyDenied("BROKER_ACCOUNT_CHANGED_DURING_READ")
            persisted = {"inserted": 0, "received": 0}
            if window["observations"]:
                persisted = await record_observations(
                    session, user_id=user_id, account_id=account_id, observations=window["observations"]
                )
            review = (await read_observations(session, user_id=user_id, account_id=account_id))["review"]
            reasons = list(window.get("failures", [])) + review["reason_codes"]
            if reasons:
                await emit(
                    session,
                    user_id=user_id,
                    account_id=account_id,
                    rule="broker_callback_evidence",
                    observed_value=reasons[0],
                    threshold="review callback gaps and conflicts",
                    message=(
                        "Broker callback evidence needs review. Complete balance reconciliation is not established."
                    ),
                    evidence_at=datetime.now(UTC),
                )
            await finish_refresh(
                session,
                lease=lease,
                user_id=user_id,
                summary={
                    "status": window["status"],
                    "inserted": persisted["inserted"],
                    "review_sha256": review["evidence_sha256"],
                },
                failure_code="BROKER_SNAPSHOT_PARTIAL" if window["status"] == "partial" else None,
            )
    except asyncio.CancelledError:
        await _record_failure(lease, user_id, account_id, "BROKER_READ_CANCELLED", keep_lease=True)
        raise
    except Exception as exc:
        code = (
            exc.code
            if isinstance(exc, PolicyDenied)
            else "BROKER_READ_TIMEOUT"
            if isinstance(exc, TimeoutError)
            else "BROKER_READ_FAILED"
        )
        await _record_failure(lease, user_id, account_id, code, keep_lease=isinstance(exc, TimeoutError))
        raise
    # Never return internal callback objects or raw selected-account identifiers.
    return {key: value for key, value in window.items() if key != "observations"} | persisted | {"review": review}


async def _record_failure(lease, user_id, account_id, code, *, keep_lease):
    try:
        async with asyncio.timeout(5), async_session.begin() as session:
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            await session.execute(text("SET LOCAL statement_timeout = '3s'"))
            await finish_refresh(
                session,
                lease=lease,
                user_id=user_id,
                summary={"status": "failed", "reason_code": code},
                failure_code=code,
                keep_lease=keep_lease,
            )
            # Checkpoint failure even if the owner was deactivated during the
            # read. Only active owners receive a new in-app alert. Fence stale
            # workers before either write; never forward provider exception text.
            active = await session.scalar(
                select(User.id).where(User.id == user_id, User.is_active.is_(True)).with_for_update(read=True)
            )
            if active:
                await emit(
                    session,
                    user_id=user_id,
                    account_id=account_id,
                    rule="broker_read_failure",
                    observed_value=code,
                    threshold="explicit broker read must return within its bounded window",
                    message="Broker evidence refresh failed. Review read status before an explicit retry.",
                    evidence_at=datetime.now(UTC),
                )
    except (Exception, asyncio.CancelledError):
        logger.warning("Broker read failure checkpoint unavailable; existing lease is not success")
