"""Read-only period evidence for owned simulator ledgers, never broker PnL."""

from decimal import Decimal, localcontext
from datetime import UTC, datetime

from sqlalchemy import select

from src.db.models import User
from src.execution.models import SimulatorAccount
from src.execution.policy import PolicyDenied, digest
from src.execution.service import account_for_user
from src.execution.valuation import period_performance
from src.execution.reconciliation import reconcile_account

MAX_REPORT_ACCOUNTS = 20
MAX_DISPLAY_EXECUTIONS = 100


def total(rows, field):
    with localcontext() as context:
        context.prec = 80
        return str(sum((Decimal(row[field]) for row in rows), Decimal(0)))


async def collect_execution_period(session, *, user_id, start, end):
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Aware increasing half-open report interval required")
    if not user_id or not await session.scalar(select(User.id).where(User.id == user_id, User.is_active.is_(True))):
        raise PolicyDenied("AUTHENTICATED_ACCOUNT_REQUIRED")
    accounts = (
        await session.scalars(
            select(SimulatorAccount.id)
            .where(
                SimulatorAccount.user_id == user_id,
            )
            .order_by(SimulatorAccount.id)
            .limit(MAX_REPORT_ACCOUNTS + 1)
        )
    ).all()
    result = dict(
        status="partial_failure" if len(accounts) > MAX_REPORT_ACCOUNTS else "complete",
        environment="simulator",
        collection_started_at=datetime.now(UTC).isoformat(),
        start=start.isoformat(),
        end_exclusive=end.isoformat(),
        accounts=[],
        accounts_truncated=len(accounts) > MAX_REPORT_ACCOUNTS,
        period_basis="Local fill booking timestamp; start inclusive, end exclusive",
        fee_basis="Restated with latest retained fee revisions at collection; not fee-payment cash flow",
        portfolio_period_pnl=None,
        limitations=[
            "Only exact observed boundary marks support account period PnL; "
            "no broker performance or cross-currency aggregate"
        ],
    )
    for account_id in accounts[:MAX_REPORT_ACCOUNTS]:
        account = await account_for_user(session, account_id, user_id)
        checked = await reconcile_account(session, account, _include_execution_evidence=True)
        item = dict(
            account_id=account.id,
            base_currency=account.currency,
            reconciliation_status=checked["status"],
            evidence_sha256=checked.get("evidence_sha256"),
        )
        if checked["status"] != "consistent":
            item.update(
                status="unavailable",
                reason="LEDGER_NOT_RECONCILED",
                executions=[],
                realized_pnl=None,
                attributed_fees=None,
                net_external_flows=None,
                cash_flows=[],
                dividend_gross=None,
                dividend_withholding=None,
                dividend_net=None,
                dividends=[],
            )
            result["status"] = "partial_failure"
        else:
            rows = [
                row
                for row in checked["reconciled_executions"]
                if start <= datetime.fromisoformat(row["booked_at"]) < end
            ]
            flows = [
                row
                for row in checked["reconciled_cash_flows"]
                if start <= datetime.fromisoformat(row["booked_at"]) < end
            ]
            actions = [
                row
                for row in checked["reconciled_corporate_actions"]
                if start <= datetime.fromisoformat(row["booked_at"]) < end
            ]
            dividends = [
                row
                for row in checked["reconciled_dividends"]
                if start <= datetime.fromisoformat(row["booked_at"]) < end
            ]
            try:
                performance = await period_performance(
                    session, user_id=user_id, account_id=account_id, start=start, end=end
                )
            except PolicyDenied as exc:
                performance = dict(status="unavailable", portfolio_pnl=None, reason=exc.code)
                result["status"] = "partial_failure"
            if performance["status"] != "complete":
                result["status"] = "partial_failure"
            item.update(
                period_performance=performance,
                portfolio_period_pnl=performance["portfolio_pnl"],
                dividend_count=len(dividends),
                dividends=dividends[:MAX_DISPLAY_EXECUTIONS],
                dividend_details_truncated=len(dividends) > MAX_DISPLAY_EXECUTIONS,
                period_dividends_sha256=digest(dividends),
                dividend_gross=total(dividends, "gross_base"),
                dividend_withholding=total(dividends, "withholding_base"),
                dividend_net=total(dividends, "net_base"),
                corporate_action_count=len(actions),
                corporate_actions=actions[:MAX_DISPLAY_EXECUTIONS],
                corporate_action_details_truncated=len(actions) > MAX_DISPLAY_EXECUTIONS,
                period_corporate_actions_sha256=digest(actions),
                status="complete",
                cash_flow_count=len(flows),
                net_external_flows=total(flows, "amount_base"),
                cash_flows=flows[:MAX_DISPLAY_EXECUTIONS],
                cash_flow_details_truncated=len(flows) > MAX_DISPLAY_EXECUTIONS,
                period_cash_flows_sha256=digest(flows),
                execution_count=len(rows),
                realized_pnl=total(rows, "realized_pnl"),
                attributed_fees=total(rows, "fee_base"),
                executions=rows[:MAX_DISPLAY_EXECUTIONS],
                execution_details_truncated=len(rows) > MAX_DISPLAY_EXECUTIONS,
                period_executions_sha256=digest(rows),
            )
        result["accounts"].append(item)
    result["as_of"] = datetime.now(UTC).isoformat()
    result["evidence_sha256"] = digest(result)
    return result
