"""Bounded, repeatable-read expense export with explicit completion trailer."""

import json
from time import monotonic
import asyncio
from datetime import UTC, date, time, datetime, timedelta

from fastapi import Depends, Request, APIRouter, HTTPException
from sqlalchemy import func, text, select, tuple_
from fastapi.responses import StreamingResponse

from src.web.auth import require_authenticated
from src.db.models import ExpenseTransaction
from src.db.database import async_session

router = APIRouter(prefix="/api/expenses", dependencies=[Depends(require_authenticated)])
MAX_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 100_000
BATCH_SIZE = 500


@router.get("/export")
async def export_expenses(request: Request, from_date: date, to_date: date):
    principal = await require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(401, "Authenticated owner required")
    if from_date > to_date or (to_date - from_date).days > 36525 or to_date == date.max:
        raise HTTPException(400, "Choose a valid date interval of at most 100 years")
    start = datetime.combine(from_date, time.min, UTC)
    end = datetime.combine(to_date + timedelta(days=1), time.min, UTC)
    owner = principal.user_id

    def line(value):
        return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()

    async def generate():
        count, size = 0, 0
        yield line(
            {
                "kind": "manifest",
                "schema": 1,
                "scope": "selected_period_all_categories",
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "state": "streaming",
                "amounts": "decimal strings in original currency",
                "requires_completion_trailer": True,
            }
        )
        try:
            async with asyncio.timeout(60), async_session() as session, session.begin():
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                snapshot_at = await session.scalar(select(func.transaction_timestamp()))
                yield line({"kind": "snapshot", "started_at": snapshot_at.isoformat()})
                checked_at = monotonic()
                last = None
                while True:
                    current = await require_authenticated(request)
                    if current.user_id != owner:
                        raise HTTPException(401, "Owner changed")
                    conditions = [
                        ExpenseTransaction.user_id == owner,
                        ExpenseTransaction.occurred_at >= start,
                        ExpenseTransaction.occurred_at < end,
                    ]
                    if last is not None:
                        conditions.append(tuple_(ExpenseTransaction.occurred_at, ExpenseTransaction.id) > last)
                    rows = (
                        (
                            await session.execute(
                                select(ExpenseTransaction)
                                .where(*conditions)
                                .order_by(ExpenseTransaction.occurred_at, ExpenseTransaction.id)
                                .limit(BATCH_SIZE)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    if not rows:
                        break
                    from src.web.routes import _expense_payload

                    for row in rows:
                        if monotonic() - checked_at >= 1:
                            current = await require_authenticated(request)
                            if current.user_id != owner:
                                raise HTTPException(401, "Owner changed")
                            checked_at = monotonic()
                        value = {
                            **_expense_payload(row),
                            "amount": str(row.amount),
                            "account_handle": row.account_key,
                            "category_override": row.category_override,
                            "received_at": row.synced_at.isoformat() if row.synced_at else None,
                        }
                        encoded = line({"kind": "transaction", "transaction": value})
                        if count >= MAX_RECORDS or size + len(encoded) > MAX_BYTES:
                            yield line(
                                {
                                    "kind": "completion",
                                    "status": "partial",
                                    "records": count,
                                    "reason_code": "EXPORT_LIMIT",
                                    "next_step": "Choose a narrower date interval.",
                                }
                            )
                            return
                        yield encoded
                        count += 1
                        size += len(encoded)
                    last = (rows[-1].occurred_at, rows[-1].id)
                current = await require_authenticated(request)
                if current.user_id != owner:
                    raise HTTPException(401, "Owner changed")
            yield line({"kind": "completion", "status": "complete", "records": count})
        except (asyncio.CancelledError, GeneratorExit):
            raise
        except Exception:
            yield line(
                {"kind": "completion", "status": "partial", "records": count, "reason_code": "EXPORT_INTERRUPTED"}
            )

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="expenses.jsonl"',
            "X-Accel-Buffering": "no",
        },
    )
