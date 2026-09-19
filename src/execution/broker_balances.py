"""Typed broker balance snapshots; source currencies remain separate."""

from typing import Literal
from decimal import Decimal, localcontext
from datetime import datetime

from pydantic import Field, BaseModel, ConfigDict, field_validator, model_validator


class PositionFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    con_id: int = Field(gt=0, strict=True)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    security_type: str = Field(min_length=1, max_length=16)
    # Source JSON evidence is independent of the simulator's Numeric(28,10).
    quantity: Decimal = Field(max_digits=40, decimal_places=20, allow_inf_nan=False)
    average_cost_reported: Decimal = Field(max_digits=40, decimal_places=20, allow_inf_nan=False)


class CashFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Decimal = Field(max_digits=40, decimal_places=20, allow_inf_nan=False)
    source_tag: Literal["CashBalance", "$LEDGER-CashBalance"]


class BalanceFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_started_at: datetime
    positions: list[PositionFact] = Field(max_length=500)
    cash: list[CashFact] = Field(max_length=100)
    position_request_complete: bool = Field(strict=True)
    cash_request_complete: bool = Field(strict=True)
    atomic_snapshot: Literal[False] = False
    valuation_basis: Literal["broker_reported_no_fx_conversion"] = "broker_reported_no_fx_conversion"

    @field_validator("request_started_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Snapshot requires an aware request time")
        return value

    @model_validator(mode="after")
    def unique_facts(self):
        if len({p.con_id for p in self.positions}) != len(self.positions):
            raise ValueError("Ambiguous duplicate contract")
        if len({c.currency for c in self.cash}) != len(self.cash):
            raise ValueError("Ambiguous duplicate currency")
        if self.cash_request_complete and not self.cash:
            raise ValueError("Missing currency balances are not complete zero cash")
        return self


def exact_difference(after, before):
    with localcontext() as context:
        context.prec = 60
        return str(after - before)


def compare_balance_evidence(rows):
    """Compare observations, never replace balances or classify changes as PnL."""
    from src.execution.policy import digest

    snapshots = [row for row in rows if row["kind"] == "balance_snapshot"]
    result = {
        "status": "unavailable",
        "snapshot_count": len(snapshots),
        "differences": [],
        "reason_codes": [],
        "balance_reconciliation": "not_established",
        "limitations": [
            "Sequential broker requests are not an atomic balance snapshot",
            "Flows, corporate actions and execution coverage require reconciliation",
        ],
    }
    if not snapshots:
        return result
    try:
        # Row timestamps come from the journal, not publisher-supplied sort keys.
        snapshots.sort(key=lambda row: (datetime.fromisoformat(row["observed_at"]), row["payload_sha256"]))
        selected = snapshots[-2:]
        facts = [BalanceFacts.model_validate(row["payload"]["balances"]) for row in selected]
        for row, fact in zip(selected, facts, strict=True):
            observed = datetime.fromisoformat(row["observed_at"])
            if observed.tzinfo is None or fact.request_started_at > observed:
                raise ValueError("Invalid snapshot time window")
        if any(digest(row["payload"]) != row["payload_sha256"] for row in selected):
            raise ValueError("Invalid evidence hash")
    except (KeyError, TypeError, ValueError):
        result.update(status="needs_review", reason_codes=["INVALID_BALANCE_EVIDENCE"])
        return result
    result["inputs_sha256"] = digest(selected)
    if any(not item.position_request_complete or not item.cash_request_complete for item in facts):
        result.update(status="needs_review", reason_codes=["BALANCE_REQUEST_INCOMPLETE"])
        return result
    if len(facts) == 1:
        result["status"] = "baseline_only"
        return result
    before, after = facts
    if datetime.fromisoformat(selected[0]["observed_at"]) >= after.request_started_at:
        result.update(status="needs_review", reason_codes=["OVERLAPPING_BALANCE_WINDOWS"])
        return result
    old_positions = {item.con_id: item for item in before.positions}
    new_positions = {item.con_id: item for item in after.positions}
    differences = []
    for contract in sorted(old_positions.keys() | new_positions.keys()):
        old, new = old_positions.get(contract), new_positions.get(contract)
        if old and new and (old.currency, old.security_type) != (new.currency, new.security_type):
            result["reason_codes"].append("CONTRACT_METADATA_CHANGED")
            continue
        prior_quantity = old.quantity if old else Decimal(0)
        current_quantity = new.quantity if new else Decimal(0)
        if prior_quantity != current_quantity:
            differences.append(
                dict(
                    kind="position_quantity",
                    con_id=contract,
                    before=str(prior_quantity),
                    after=str(current_quantity),
                    delta=exact_difference(current_quantity, prior_quantity),
                )
            )
        if old and new and old.average_cost_reported != new.average_cost_reported:
            differences.append(
                dict(
                    kind="broker_reported_average_cost",
                    con_id=contract,
                    before=str(old.average_cost_reported),
                    after=str(new.average_cost_reported),
                )
            )
    old_cash = {item.currency: item.amount for item in before.cash}
    new_cash = {item.currency: item.amount for item in after.cash}
    if old_cash.keys() != new_cash.keys():
        result["reason_codes"].append("CASH_CURRENCY_SET_CHANGED")
    for currency in sorted(old_cash.keys() & new_cash.keys()):
        if old_cash[currency] != new_cash[currency]:
            differences.append(
                dict(
                    kind="cash",
                    currency=currency,
                    before=str(old_cash[currency]),
                    after=str(new_cash[currency]),
                    delta=exact_difference(new_cash[currency], old_cash[currency]),
                )
            )
    result.update(
        status="needs_review" if result["reason_codes"] else "changed" if differences else "unchanged",
        differences=differences[:100],
        difference_count=len(differences),
        differences_truncated=len(differences) > 100,
    )
    # Even an unchanged balance pair does not establish complete executions/PnL.
    result["evidence_sha256"] = digest(result)
    return result
