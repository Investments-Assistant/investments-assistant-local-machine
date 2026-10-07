"""Owner-declared pending/booked identity resolution, never fuzzy provider matching."""

from decimal import Decimal, InvalidOperation
import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import Text, cast, func, select
from sqlalchemy.orm import defer
from sqlalchemy.orm.attributes import flag_modified

from src.db.models import ExpenseTransaction
from src.expenses.models import ExpenseAudit, ExpenseRetirement
from src.execution.policy import PolicyDenied, digest
from src.expenses.persistence import expense_write_lock, retirement_identity
from src.expenses.history_retention import export_row


async def reconciliation_plan(session, *, user_id, pending_id, booked_id, as_of, now=None):
    now = now or datetime.now(UTC)
    if as_of.tzinfo is None or now.tzinfo is None or as_of > now or now - as_of > timedelta(minutes=10):
        raise PolicyDenied("RECONCILIATION_PREVIEW_EXPIRED")
    if pending_id == booked_id:
        raise PolicyDenied("DISTINCT_TRANSACTIONS_REQUIRED")
    await expense_write_lock(session, user_id)
    records = (await session.execute(select(
        ExpenseTransaction,
        func.encode(func.sha256(func.convert_to(cast(ExpenseTransaction.raw_data, Text), "UTF8")), "hex"),
        ExpenseTransaction.raw_data["signed_amount"].as_string(),
    ).options(defer(ExpenseTransaction.raw_data)).where(
        ExpenseTransaction.user_id == user_id,
        ExpenseTransaction.id.in_([pending_id, booked_id]),
    ).order_by(ExpenseTransaction.id).with_for_update())).all()
    indexed = {row.id: (row, raw_hash, signed) for row, raw_hash, signed in records}
    if pending_id not in indexed or booked_id not in indexed:
        raise PolicyDenied("TRANSACTIONS_NOT_OWNED")
    pending, booked = indexed[pending_id][0], indexed[booked_id][0]
    if (not pending.pending or pending.lifecycle != "pending"
            or booked.pending or booked.lifecycle not in {"booked", "revised"}):
        raise PolicyDenied("PENDING_AND_SETTLED_REQUIRED")
    unspecified = hashlib.sha256((pending.provider + "|import-unspecified").encode()).hexdigest()
    if (pending.provider != booked.provider or pending.account_key != booked.account_key
            or pending.account_key in {unspecified, "legacy-unassigned", ""}
            or pending.currency != booked.currency or pending.transaction_type != booked.transaction_type):
        raise PolicyDenied("RECONCILIATION_SCOPE_MISMATCH")
    if pending.transaction_type == "transfer":
        try:
            signs = [Decimal(str(indexed[key][2])) for key in (pending_id, booked_id)]
            if not all(value.is_finite() and value != 0 for value in signs) or (signs[0] > 0) != (signs[1] > 0):
                raise ValueError("Unknown or mismatched direction")
        except (ValueError, InvalidOperation):
            raise PolicyDenied("TRANSFER_DIRECTION_UNVERIFIED") from None
    if pending.category_override and booked.category_override and (
        pending.category, pending.subcategory
    ) != (booked.category, booked.subcategory):
        raise PolicyDenied("CATEGORY_OVERRIDE_CONFLICT")
    exported = dict(schema=1, scope="owner_declared_pending_resolution", pending=export_row(pending),
                    booked=export_row(booked), excludes="raw provider payloads")
    exported["pending"]["signed_amount"] = indexed[pending_id][2]
    exported["booked"]["signed_amount"] = indexed[booked_id][2]
    export_sha = digest(exported)
    copy_category = pending.category_override and not booked.category_override
    plan = dict(pending_id=pending_id, booked_id=booked_id, as_of=as_of.isoformat(), export_sha256=export_sha,
                copy_pending_category=copy_category,
                booked_category_after=pending.category if copy_category else booked.category,
                pending_removed=True, booked_amount_unchanged=True, matching_pending_imports_blocked=True)
    plan["plan_sha256"] = digest(dict(owner=user_id, plan=plan,
                                     raw_hashes={key: value[1] for key, value in sorted(indexed.items())}))
    return plan, exported, pending, booked


async def reconcile_pending(session, *, user_id, pending_id, booked_id, as_of, expected_plan, export_sha256, now=None):
    plan, exported, pending, booked = await reconciliation_plan(
        session, user_id=user_id, pending_id=pending_id, booked_id=booked_id, as_of=as_of, now=now)
    if plan["plan_sha256"] != expected_plan:
        raise PolicyDenied("RECONCILIATION_PLAN_CHANGED")
    if plan["export_sha256"] != export_sha256:
        raise PolicyDenied("RECONCILIATION_EXPORT_MISMATCH")
    if plan["copy_pending_category"]:
        # A category edit is not a new provider receipt. Force the retained clock
        # into UPDATE so the legacy model onupdate default cannot overwrite it.
        flag_modified(booked, "synced_at")
        booked.category, booked.subcategory, booked.category_override = pending.category, pending.subcategory, True
    identity = retirement_identity(user_id, exported["pending"])
    session.add(ExpenseRetirement(user_id=user_id, identity_sha256=identity, plan_sha256=expected_plan))
    session.add(ExpenseAudit(user_id=user_id, transaction_id=pending.id, action="pending_reconciled", changes=dict(
        basis="explicit_owner_confirmation", booked_transaction_id=booked.id, plan_sha256=expected_plan,
        export_sha256=export_sha256, pending_identity_sha256=identity,
        category_copied=plan["copy_pending_category"], booked_amount_changed=False,
    )))
    await session.delete(pending)
    await session.flush()
    return dict(status="complete", removed_pending=1, booked_amount_changed=False,
                matching_pending_imports_blocked=True)
