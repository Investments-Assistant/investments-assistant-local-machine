"""Exact, attributable portfolio facts for chat; model prose cannot set amounts."""

import re
import json
from decimal import Decimal

from src.finance.normalization import decimal_value
from src.finance.portfolio_review import review_text


def _number(row, *keys):
    for key in keys:
        value = decimal_value(row.get(key))
        if value is not None:
            return str(value)
    return None


def _text(value, maximum=100):
    return value if isinstance(value, str) and len(value) <= maximum else None


def portfolio_facts(serialized):
    try:
        result = json.loads(serialized, parse_float=Decimal)
    except (TypeError, ValueError):
        return {"status": "unavailable", "reason": "INVALID_PORTFOLIO_EVIDENCE"}
    if not isinstance(result, dict):
        return {"status": "unavailable", "reason": "INVALID_PORTFOLIO_EVIDENCE"}
    if result.get("error") or result.get("error_code") or result.get("status") in {"blocked", "unavailable"}:
        return {"status": "unavailable", "reason": "PORTFOLIO_SOURCE_UNAVAILABLE"}
    rows = result.get("positions", result.get("holdings"))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return {"status": "unavailable", "reason": "INVALID_PORTFOLIO_POSITIONS"}
    positions = []
    for row in rows[:20]:
        currency = row.get("currency")
        currency = currency if isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency) else None
        positions.append(
            {
                "symbol": _text(row.get("symbol", row.get("asset"))),
                "contract_id": str(row["con_id"])
                if re.fullmatch(r"[1-9][0-9]{0,19}", str(row.get("con_id")))
                else None,
                "account_id": _text(row.get("account_id", result.get("account_id"))),
                "quantity": _number(row, "quantity_exact", "qty", "quantity", "available", "free"),
                "source_currency": currency,
                "source_price": _number(row, "current_price", "market_price", "price") if currency else None,
                "source_market_value": _number(row, "market_value", "value") if currency else None,
                "source_unrealized_pnl": _number(row, "unrealized_pnl", "unrealized_pl") if currency else None,
                "as_of": _text(row.get("as_of")),
            }
        )
    errors = result.get("errors")
    return {
        "status": "source_evidence_only",
        "source_valuation_status": _text(result.get("valuation_status")) or "unavailable",
        "as_of": _text(result.get("as_of")),
        "reported_total_market_value_usd": (
            _number(result, "total_market_value_usd_exact", "total_market_value_usd") if not errors else None
        ),
        "reported_total_unrealized_pnl_usd": (
            _number(result, "total_unrealized_pnl_usd_exact", "total_unrealized_pnl_usd") if not errors else None
        ),
        "positions": positions,
        "omitted_positions": max(0, len(rows) - 20),
        "source_error_count": len(errors) if isinstance(errors, list) else int(bool(errors)),
    }


def financial_answer(results, *, portuguese=False):
    """Render known financial facts and preserve independent requested evidence."""
    if "get_portfolio_summary" not in results:
        return None
    heading = "Dados da carteira" if portuguese else "Portfolio evidence"
    note = (
        "Valores provenientes das fontes. null significa indisponível. "
        "Não foram inferidos totais entre contas ou moedas, câmbio ou execuções."
        if portuguese
        else "Amounts are source-reported. null means unavailable. "
        "No totals across accounts or currencies, FX rates or executions were inferred."
    )
    facts = portfolio_facts(results["get_portfolio_summary"])
    review_heading = "Análise da carteira" if portuguese else "Portfolio review"
    blocks = [
        f"## {review_heading}",
        review_text(facts, portuguese=portuguese),
        f"## {heading}",
        note,
        "```json\n" + json.dumps(facts, ensure_ascii=False, indent=2).replace("`", "\\u0060") + "\n```",
    ]
    for name, raw in results.items():
        if name == "get_portfolio_summary":
            continue
        try:
            evidence = json.loads(raw)
        except (TypeError, ValueError):
            evidence = {"status": "invalid_evidence"}
        if len(raw) > 4000:
            evidence = {"status": "evidence_budget_exceeded", "message": "Full result retained in the tool event."}
        blocks.extend(
            [
                f"## {name}",
                "```json\n" + json.dumps(evidence, ensure_ascii=False, indent=2).replace("`", "\\u0060") + "\n```",
            ]
        )
    return "\n\n".join(blocks)
