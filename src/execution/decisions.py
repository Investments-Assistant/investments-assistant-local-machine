"""Retained signal inputs and outcomes; caller owns account lock and transaction."""

from src.execution.models import StrategyDecision
from src.execution.policy import digest


async def retain_decision(session, *, account, mandate, tick_key, instrument, now, risk, result,
                          quantity=None, side=None):
    evidence = dict(
        version=1, account_id=account.id, user_id=account.user_id, mandate_id=mandate.id,
        mandate_hash=mandate.details_hash, tick_key=tick_key, observed_at=now.isoformat(),
        instrument=dict(id=instrument.id, price=str(instrument.price), currency=instrument.currency,
                        fx_to_base=str(instrument.fx_to_base), multiplier=str(instrument.multiplier),
                        as_of=instrument.as_of.isoformat()),
        side=side, quantity=str(quantity) if quantity is not None else None,
        risk=risk, result=result,
    )
    row = StrategyDecision(account_id=account.id, user_id=account.user_id, mandate_id=mandate.id,
                           tick_key=tick_key, evidence=evidence, evidence_hash=digest(evidence), created_at=now)
    session.add(row)
    await session.flush()
    return dict(result, decision_id=row.id)
