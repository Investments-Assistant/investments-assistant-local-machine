"""Authenticated expense categorization; no broker or model scope."""

from fastapi import Depends, Request, APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from src.web.auth import require_csrf, require_authenticated
from src.db.models import ExpenseTransaction
from src.db.database import async_session
from src.expenses.models import ExpenseAudit
from src.expenses.categories import CATEGORY_TAXONOMY

router = APIRouter(prefix="/api/expenses", dependencies=[Depends(require_authenticated)])


class CategoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str
    subcategory: str | None = None


@router.patch("/{transaction_id}/category", dependencies=[Depends(require_csrf)])
async def set_category(transaction_id: str, body: CategoryInput, request: Request):
    principal = await require_authenticated(request)
    if not principal.user_id or principal.mechanism != "cookie":
        raise HTTPException(403, "An authenticated browser account is required")
    definition = CATEGORY_TAXONOMY.get(body.category)
    if not definition or (body.subcategory and body.subcategory not in definition["subcategories"]):
        raise HTTPException(400, "Select a supported category and subcategory")
    subcategory = body.subcategory or definition["subcategories"][0]
    async with async_session.begin() as session:
        row = await session.scalar(
            select(ExpenseTransaction)
            .where(
                ExpenseTransaction.id == transaction_id,
                ExpenseTransaction.user_id == principal.user_id,
            )
            .with_for_update()
        )
        if row is None:
            raise HTTPException(404, "Transaction not found")
        before = dict(
            category=row.category, subcategory=row.subcategory, override=row.category_override
        )
        row.category, row.subcategory, row.category_override = body.category, subcategory, True
        after = dict(category=row.category, subcategory=row.subcategory, override=True)
        if before != after:
            session.add(
                ExpenseAudit(
                    user_id=principal.user_id,
                    transaction_id=row.id,
                    action="category_override",
                    changes=dict(before=before, after=after),
                )
            )
    from src.web.routes import _publish_expense_event

    await _publish_expense_event(principal.user_id, {"kind": "category_changed"})
    return dict(status="updated", category=body.category, subcategory=subcategory)
