"""Explicit download of one owned replay's immutable source/result evidence."""

import json

from fastapi import Depends, Request, Response, APIRouter, HTTPException
from sqlalchemy import select

from src.web.auth import require_authenticated
from src.db.models import SimulationResult
from src.db.database import async_session

router = APIRouter(prefix="/api/simulations", dependencies=[Depends(require_authenticated)])


@router.get("/{simulation_id}/evidence")
async def replay_evidence(simulation_id: str, request: Request):
    principal = await require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(401, "Authenticated owner required")
    async with async_session() as session:
        row = await session.scalar(
            select(SimulationResult).where(
                SimulationResult.id == simulation_id, SimulationResult.user_id == principal.user_id
            )
        )
        if row is None or not row.strategy.get("research"):
            raise HTTPException(404, "Replay evidence unavailable")
        evidence = row.strategy["research"]
    return Response(
        json.dumps(evidence, default=str),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="replay-evidence.json"',
            "Cache-Control": "no-store",
        },
    )
