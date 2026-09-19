"""User-scoped in-app alerts. This router has no external notification channel."""

from fastapi import Depends, Request, APIRouter, HTTPException
from sqlalchemy import select

from src.web.auth import require_csrf, require_authenticated
from src.db.models import User
from src.db.database import async_session
from src.execution.policy import PolicyDenied
from src.operations.alerts import acknowledge
from src.operations.models import OperationalAlert

router = APIRouter(prefix="/api/alerts", dependencies=[Depends(require_authenticated)])


@router.get("")
async def list_alerts(request: Request, offset: int = 0, limit: int = 50):
    principal = await require_authenticated(request)
    async with async_session() as session:
        if not await session.scalar(
            select(User.id).where(User.id == principal.user_id, User.is_active.is_(True))
        ):
            raise HTTPException(401, "Account inactive")
        rows = (
            (
                await session.execute(
                    select(OperationalAlert)
                    .where(OperationalAlert.user_id == principal.user_id)
                    .order_by(OperationalAlert.evidence_at.desc(), OperationalAlert.id)
                    .offset(max(0, offset))
                    .limit(min(100, max(1, limit)))
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": row.id,
                "rule": row.rule,
                "severity": row.severity,
                "message": row.message,
                "status": row.status,
                "evidence_at": row.evidence_at.isoformat(),
                "observed_value": row.observed_value,
                "threshold": row.threshold,
                "occurrences": row.occurrences,
                "delivery_status": row.delivery_status,
                "delivery_error": row.delivery_error,
            }
            for row in rows
        ]


@router.post("/{alert_id}/acknowledge", dependencies=[Depends(require_csrf)])
async def acknowledge_alert(alert_id: str, request: Request):
    principal = await require_authenticated(request)
    try:
        async with async_session.begin() as session:
            status = await acknowledge(session, user_id=principal.user_id, alert_id=alert_id)
            return {"status": status}
    except PolicyDenied as exc:
        raise HTTPException(404, "Alert unavailable") from exc
