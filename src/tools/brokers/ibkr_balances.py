"""Normalize completed IBKR balance requests without flattening currencies."""

import uuid
from datetime import UTC, datetime


def collect_balances(ib, actual):
    started = datetime.now(UTC)
    # Each synchronous call resolves its SDK end marker or raises/ times out.
    positions = ib.reqPositions()
    ib.reqAccountSummary()
    values = ib.accountSummary(account=actual)
    selected_positions = []
    for position in positions:
        if position.account != actual:
            continue
        if len(selected_positions) >= 500:
            raise ValueError("BROKER_POSITION_CAPACITY")
        contract = position.contract
        selected_positions.append(
            dict(
                con_id=contract.conId,
                currency=contract.currency,
                security_type=contract.secType,
                quantity=str(position.position),
                average_cost_reported=str(position.avgCost),
            )
        )
    cash = []
    for value in values:
        if value.account != actual or value.tag not in {"CashBalance", "$LEDGER-CashBalance"}:
            continue
        # BASE aggregates are not an original currency and cannot be mixed into cash.
        if value.currency == "BASE":
            continue
        if len(cash) >= 100:
            raise ValueError("BROKER_CURRENCY_CAPACITY")
        cash.append(dict(currency=value.currency, amount=value.value, source_tag=value.tag))
    return dict(
        kind="balance_snapshot",
        actual_account=actual,
        event_id="balance-" + uuid.uuid4().hex,
        observed_at=datetime.now(UTC),
        balances=dict(
            request_started_at=started,
            positions=sorted(selected_positions, key=lambda row: row["con_id"]),
            cash=sorted(cash, key=lambda row: row["currency"]),
            position_request_complete=True,
            cash_request_complete=bool(cash),
        ),
    )
