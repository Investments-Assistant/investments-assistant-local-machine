"""Transactional checkpoints for a bounded, explicitly activated read session.

No connection or scheduling happens here. Callers commit each batch, retain it
until commit succeeds, and stop their SDK owner on any failure. A missing final
checkpoint means interrupted capture, never complete broker history.
"""

from datetime import datetime, timedelta
from dataclasses import field, dataclass

from sqlalchemy import func, select

from src.execution.policy import PolicyDenied, digest
from src.operations.models import JobLease
from src.execution.broker_observations import selected_account, record_observations
from src.execution.broker_refresh_state import begin_refresh, finish_refresh


@dataclass(frozen=True)
class StreamScope:
    user_id: str
    account_id: str
    lease: tuple = field(repr=False)
    binding: str = field(repr=False)
    config_digest: str = field(repr=False)


async def begin_stream(session, *, user_id, account_id, maximum_seconds=60):
    if type(maximum_seconds) is not int or not 1 <= maximum_seconds <= 600:
        raise ValueError("Invalid bounded stream lifetime")
    config, binding = await selected_account(session, user_id=user_id, account_id=account_id)
    lease = await begin_refresh(session, user_id=user_id, account_id=account_id)
    row = await session.get(JobLease, lease[0])
    now = await session.scalar(select(func.clock_timestamp()))
    row.checkpoint = dict(row.checkpoint, capture="stream", batches=0, received=0, inserted=0,
                          stop_at=(now + timedelta(seconds=maximum_seconds)).isoformat(),
                          complete_history=False, execution_authority="none")
    return config, StreamScope(user_id, account_id, lease, binding, digest(config))


async def checkpoint_batch(session, *, scope, observations, final=False, failures=()):
    """Facts and checkpoint commit together, fenced by live authority and DB time.

    The final flag attests that the trusted SDK caller already detached capture
    and finished native cleanup; it must retain the lease if cleanup is uncertain.
    It does not attest to complete history, fees or financial reconciliation.
    Gaps terminate this lease as partial; they cannot be cleared by a later batch.
    """
    if not isinstance(observations, list) or len(observations) > 1000 or type(final) is not bool:
        raise PolicyDenied("INVALID_OBSERVATION_BATCH")
    allowed = {"BROKER_CALLBACK_CAPACITY", "INVALID_BROKER_CALLBACK",
               "COMMISSION_EXECUTION_MISMATCH", "BROKER_DISCONNECTED_DURING_SNAPSHOT",
               "BROKER_SNAPSHOT_REQUEST_FAILED", "BROKER_STREAM_INTERRUPTED",
               "BROKER_UPSTREAM_CONNECTION_CHANGED"}
    if not isinstance(failures, (list, tuple)) or len(failures) > len(allowed) or any(
        not isinstance(code, str) or code not in allowed for code in failures
    ) or (failures and not final):
        raise PolicyDenied("INVALID_CALLBACK_FAILURE")
    config, binding = await selected_account(session, user_id=scope.user_id, account_id=scope.account_id)
    if binding != scope.binding or digest(config) != scope.config_digest:
        raise PolicyDenied("BROKER_ACCOUNT_CHANGED_DURING_READ")
    row = await session.scalar(select(JobLease).where(
        JobLease.id == scope.lease[0], JobLease.user_id == scope.user_id,
        JobLease.token == scope.lease[1]).with_for_update())
    now = await session.scalar(select(func.clock_timestamp()))
    if (row is None or row.leased_at is None or row.leased_at > now or row.lease_until <= now
            or row.checkpoint.get("capture") != "stream" or row.checkpoint.get("status") != "running"):
        raise PolicyDenied("STALE_JOB_LEASE")
    stop_at = datetime.fromisoformat(row.checkpoint["stop_at"])
    if now >= stop_at:
        raise PolicyDenied("BROKER_STREAM_EXPIRED")
    persisted = {"inserted": 0, "received": 0}
    if observations:
        persisted = await record_observations(session, user_id=scope.user_id,
                                             account_id=scope.account_id, observations=observations)
    summary = dict(row.checkpoint, batches=row.checkpoint["batches"] + 1,
                   received=row.checkpoint["received"] + persisted["received"],
                   inserted=row.checkpoint["inserted"] + persisted["inserted"],
                   checkpoint_at=now.isoformat(), failures=sorted(set(failures)))
    # Recheck after persistence, for terminal batches as well as renewals.
    end = await session.scalar(select(func.clock_timestamp()))
    if end < now or end >= row.lease_until or end >= stop_at:
        raise PolicyDenied("STALE_JOB_LEASE")
    if final or failures:
        summary["status"] = "partial" if failures else "observed"
        await finish_refresh(session, lease=scope.lease, user_id=scope.user_id, summary=summary,
                             failure_code="BROKER_STREAM_PARTIAL" if failures else None)
    else:
        # Check again after persistence: a transaction started before expiry must
        # not revive ownership after waiting for an insert or lock.
        row.leased_at = end
        row.lease_until = min(end + timedelta(seconds=90), stop_at)
        row.checkpoint = summary
    return summary
