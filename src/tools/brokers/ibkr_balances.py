"""Normalize completed IBKR balance requests without flattening currencies."""

import uuid
from datetime import UTC, datetime

from src.execution.broker_balances import CashFact


def _fresh_cash(ib, actual):
    """One owner-thread subscription window, never the SDK's retained cache.

    The sole selected account's primary download completed during startup. End
    only that account's old read subscription, then request a new initial
    download. ib_async's blocking call waits for accountDownloadEnd, but its
    wrapper ignores that callback's account argument. The temporary guard below
    requires the selected account before allowing the SDK future to complete.
    Decoder.wrap resolves the wrapper method at dispatch time in pinned 2.1.0.
    """
    wrapper, client = ib.wrapper, ib.client
    original_end = wrapper.accountDownloadEnd
    original_value = wrapper.updateAccountValue
    original_request = client.reqAccountUpdates
    missing = object()
    restored_attributes = [
        (wrapper, name, vars(wrapper).get(name, missing))
        for name in ("updateAccountValue", "accountDownloadEnd")
    ] + [(client, "reqAccountUpdates", vars(client).get("reqAccountUpdates", missing))]
    values = {}
    accepting = completed = ready = invalid = requested = False
    primary_failure = False

    def account_value(tag, value, currency, account):
        nonlocal ready, invalid
        try:
            original_value(tag, value, currency, account)
            if not accepting or account != actual:
                return
            if tag in {"AccountReady", "accountReady"}:
                if value == "true":
                    ready = True
                else:
                    invalid = True
                return
            if tag not in {"CashBalance", "$LEDGER-CashBalance"} or currency == "BASE":
                return
            if invalid:
                return
            if not isinstance(value, str) or len(value) > 128:
                invalid = True
                return
            fact = CashFact(currency=currency, amount=value, source_tag=tag)
            if fact.currency not in values:
                if len(values) >= 100:
                    invalid = True
                    return
                values[fact.currency] = {}
            sources = values[fact.currency]
            # Repeated updates of one key replace its previous exact value.
            # Different source tags for a currency must agree; never sum them.
            if any(old.amount != fact.amount for tag, old in sources.items() if tag != fact.source_tag):
                invalid = True
                return
            sources[fact.source_tag] = fact
        except Exception:
            # Event handlers must not throw into the SDK logger, whose callback
            # diagnostics could otherwise include financial values/account IDs.
            invalid = True

    def account_request(subscribed, account):
        nonlocal accepting, requested
        if subscribed is not True or account != actual or requested:
            raise RuntimeError("BROKER_ACCOUNT_UPDATE_REQUEST_SCOPE")
        original_request(True, actual)
        # reqAccountUpdatesAsync sends synchronously before pumping the SDK loop.
        # Ignore queued callbacks delivered before this exact request was sent.
        requested = accepting = True

    def account_end(account):
        nonlocal accepting, completed, invalid
        if not accepting or account != actual:
            return
        accepting = False
        try:
            original_end(account)
            completed = True
        except Exception:
            invalid = True

    try:
        # The SDK portfolio cache stops receiving primary updates on unsubscribe.
        # Persistent-owner reads must not relabel that cache with a fresh as_of.
        ib._ia_primary_portfolio_stale = True
        original_request(False, actual)
        # Multi-account updates emit accountValueEvent too, even with empty
        # modelCode. Capture the primary callback channel only, never that event.
        wrapper.updateAccountValue = account_value
        wrapper.accountDownloadEnd = account_end
        client.reqAccountUpdates = account_request
        ib.reqAccountUpdates(account=actual)
    except BaseException:
        primary_failure = True
        raise
    finally:
        accepting = False
        cleanup_failed = False
        for target, name, previous in restored_attributes:
            try:
                if previous is missing:
                    if name in vars(target):
                        delattr(target, name)
                else:
                    setattr(target, name, previous)
            except Exception:
                cleanup_failed = True
        try:
            original_request(False, actual)
        except Exception:
            cleanup_failed = True
        if cleanup_failed and not primary_failure:
            raise RuntimeError("BROKER_ACCOUNT_UPDATE_CLEANUP_FAILED")
    if invalid or not completed or not ready or not values:
        return [], False
    cash = []
    for currency, sources in sorted(values.items()):
        fact = sources.get("$LEDGER-CashBalance") or sources["CashBalance"]
        cash.append(dict(currency=currency, amount=str(fact.amount), source_tag=fact.source_tag))
    return cash, True


def collect_balances(ib, actual):
    from src.tools.brokers.ibkr import require_selected_account

    require_selected_account(ib, actual)
    started = datetime.now(UTC)
    # Each synchronous call resolves its SDK end marker or raises/ times out.
    positions = ib.reqPositions()
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
    cash, cash_complete = _fresh_cash(ib, actual)
    require_selected_account(ib, actual)
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
            cash_request_complete=cash_complete,
        ),
    )
