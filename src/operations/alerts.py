"""Durable in-app alerts; outbound delivery is an injected local test sink only."""

import uuid
from datetime import timedelta

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert

from src.db.models import User
from src.execution.policy import PolicyDenied, digest
from src.operations.models import OperationalAlert


async def emit(
    session,
    *,
    user_id: str,
    rule: str,
    observed_value: str,
    threshold: str,
    message: str,
    evidence_at,
    account_id=None,
    severity="warning",
    cooldown_seconds=300,
):
    if severity not in {"info", "warning", "critical"} or not 1 <= cooldown_seconds <= 86400:
        raise ValueError("Invalid alert policy")
    if not await session.scalar(
        select(User.id).where(User.id == user_id, User.is_active.is_(True))
    ):
        raise PolicyDenied("PRINCIPAL_INACTIVE")
    now = await session.scalar(select(func.now()))
    key = digest({"rule": rule, "version": "1", "account": account_id})
    statement = insert(OperationalAlert).values(
        id=str(uuid.uuid4()),
        user_id=user_id,
        account_id=account_id,
        rule=rule,
        rule_version="1",
        severity=severity,
        deduplication_key=key,
        evidence_at=evidence_at,
        observed_value=str(observed_value),
        threshold=str(threshold),
        message=message,
        status="open",
        occurrences=1,
        cooldown_until=now + timedelta(seconds=cooldown_seconds),
        delivery_status="in_app",
    )
    # Keep repeated evidence in one alert; only a resolved/expired rule reopens it.
    reopen = (OperationalAlert.cooldown_until <= now) | (OperationalAlert.status == "resolved")
    statement = statement.on_conflict_do_update(
        index_elements=["user_id", "deduplication_key"],
        set_={
            "occurrences": OperationalAlert.occurrences + 1,
            "evidence_at": func.greatest(OperationalAlert.evidence_at, evidence_at),
            "observed_value": case(
                (OperationalAlert.evidence_at <= evidence_at, str(observed_value)),
                else_=OperationalAlert.observed_value,
            ),
            "status": case((reopen, "open"), else_=OperationalAlert.status),
            "cooldown_until": case(
                (reopen, now + timedelta(seconds=cooldown_seconds)),
                else_=OperationalAlert.cooldown_until,
            ),
            "delivery_status": case((reopen, "in_app"), else_=OperationalAlert.delivery_status),
            "acknowledged_at": case((reopen, None), else_=OperationalAlert.acknowledged_at),
            "resolved_at": case((reopen, None), else_=OperationalAlert.resolved_at),
        },
    ).returning(OperationalAlert.id)
    return await session.scalar(statement)


async def acknowledge(session, *, user_id: str, alert_id: str, resolve=False):
    if not await session.scalar(
        select(User.id).where(User.id == user_id, User.is_active.is_(True))
    ):
        raise PolicyDenied("PRINCIPAL_INACTIVE")
    row = await session.scalar(
        select(OperationalAlert)
        .where(OperationalAlert.id == alert_id, OperationalAlert.user_id == user_id)
        .with_for_update()
    )
    if row is None:
        raise PolicyDenied("ALERT_NOT_OWNED")
    now = await session.scalar(select(func.now()))
    row.acknowledged_at = now
    row.status = "resolved" if resolve else "acknowledged"
    if resolve:
        row.resolved_at = now
    await session.flush()
    return row.status


async def deliver_local(session, *, user_id: str, alert_id: str, sink):
    if not await session.scalar(
        select(User.id).where(User.id == user_id, User.is_active.is_(True))
    ):
        raise PolicyDenied("PRINCIPAL_INACTIVE")
    row = await session.scalar(
        select(OperationalAlert)
        .where(OperationalAlert.id == alert_id, OperationalAlert.user_id == user_id)
        .with_for_update()
    )
    if row is None:
        raise PolicyDenied("ALERT_NOT_OWNED")
    if row.delivery_status == "delivered":
        return "deduplicated"
    try:
        await sink(
            {"id": row.id, "rule": row.rule, "severity": row.severity, "message": row.message}
        )
        row.delivery_status = "delivered"
        row.delivery_error = None
    except Exception:
        row.delivery_status = "failed"
        row.delivery_error = "LOCAL_SINK_FAILED"
    await session.flush()
    return row.delivery_status
