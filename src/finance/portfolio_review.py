"""Descriptive source exposure, never risk-policy approval or an investment forecast."""

from decimal import Decimal, localcontext
from datetime import datetime
from collections import defaultdict

from src.finance.normalization import decimal_value


def _timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except ValueError:
        return None


def exposure_groups(facts):
    """Only complete, positive-value, same-time, qualified account/currency groups.

    Contract identity is descriptive source identity, not execution qualification.
    Never combine currencies, accounts, duplicate contracts or omitted positions.
    """
    rows = facts.get("positions", [])
    if not rows or facts.get("omitted_positions") or facts.get("source_error_count"):
        return []
    groups = defaultdict(list)
    seen = set()
    for index, row in enumerate(rows, 1):
        key = row.get("account_id"), row.get("source_currency")
        identity = key[0], row.get("contract_id")
        value = decimal_value(row.get("source_market_value"))
        quantity = decimal_value(row.get("quantity"))
        at = _timestamp(row.get("as_of") or facts.get("as_of"))
        if (
            not all(key)
            or not identity[1]
            or identity in seen
            or at is None
            or value is None
            or value < 0
            or abs(value.adjusted()) > 100
            or quantity is None
            or quantity < 0
            or (quantity == 0 and value > 0)
        ):
            return []
        seen.add(identity)
        groups[key].append((index, value, at))
    result = []
    with localcontext() as context:
        context.prec = 128
        for (account, currency), members in groups.items():
            if len({member[2] for member in members}) != 1:
                return []
            total = sum((member[1] for member in members), Decimal(0))
            if total <= 0:
                return []
            largest = max(members, key=lambda member: member[1])
            percent = (largest[1] * 100 / total).quantize(Decimal("0.01"))
            result.append(
                dict(
                    account_id=account,
                    currency=currency,
                    source_total=str(total),
                    largest_position=largest[0],
                    largest_percent=format(percent, "f").rstrip("0").rstrip("."),
                    positions=[member[0] for member in members],
                    as_of=members[0][2].isoformat(),
                )
            )
    return result


def review_text(facts, *, portuguese=False):
    def language(english, portuguese_text):
        return portuguese_text if portuguese else english

    if facts.get("status") == "unavailable":
        return language(
            "Portfolio review is unavailable because the source could not provide valid evidence.",
            "A análise da carteira está indisponível porque a fonte não forneceu dados válidos.",
        )
    rows = facts["positions"]
    if not rows:
        return language(
            "The source returned no positions; this is not proof of a zero account balance.",
            "A fonte não devolveu posições; isto não prova que o saldo da conta seja zero.",
        )
    lines = [
        language(
            f"Review covers {len(rows)} displayed source positions.",
            f"A análise abrange {len(rows)} posições apresentadas pela fonte.",
        )
    ]
    if facts["omitted_positions"]:
        lines.append(
            language(
                f"{facts['omitted_positions']} positions are omitted from this bounded answer.",
                f"{facts['omitted_positions']} posições foram omitidas desta resposta limitada.",
            )
        )
    missing = sum(row.get("source_market_value") is None for row in rows)
    if missing:
        lines.append(
            language(
                f"Source values are missing for {missing} displayed position(s); "
                "prices and quantities are not substituted for qualified valuations.",
                f"Faltam valores de {missing} posições; preços e quantidades não substituem avaliações qualificadas.",
            )
        )
    if any(not _timestamp(row.get("as_of") or facts.get("as_of")) for row in rows):
        lines.append(
            language(
                "Freshness cannot be verified: one or more source timestamps are missing or invalid.",
                "Não é possível verificar a atualidade: faltam datas válidas de uma ou mais fontes.",
            )
        )
    if len({row["source_currency"] for row in rows if row["source_currency"]}) > 1:
        lines.append(
            language(
                "Currencies are kept separate; cross-currency exposure requires verified dated FX.",
                "As moedas são mantidas separadas; a exposição entre moedas exige câmbio verificado e datado.",
            )
        )
    if facts["source_error_count"]:
        lines.append(
            language(
                "One or more sources failed; this is an incomplete account view.",
                "Uma ou mais fontes falharam; a visão das contas está incompleta.",
            )
        )
    groups = exposure_groups(facts)
    for index, group in enumerate(groups, 1):
        members = ", ".join(map(str, group["positions"]))
        lines.append(
            language(
                f"Source account/currency group {index} (evidence positions {members}): "
                f"largest position #{group['largest_position']} is approximately {group['largest_percent']}% "
                f"of {group['source_total']} {group['currency']} in reported holding values, "
                f"excluding cash (as of {group['as_of']}).",
                f"Grupo de conta/moeda {index} (posições {members}): "
                f"a maior posição, #{group['largest_position']}, "
                f"representa aproximadamente {group['largest_percent']}% "
                f"de {group['source_total']} {group['currency']} dos valores das posições, "
                f"excluindo dinheiro (data {group['as_of']}).",
            )
        )
    if not groups:
        lines.append(
            language(
                "Holding concentration is unavailable: complete values, unique contract/account "
                "identities and comparable timestamps are required.",
                "A concentração das posições está indisponível: exige valores completos, "
                "identidades únicas de contrato/conta e datas comparáveis.",
            )
        )
    lines.append(
        language(
            "These are source-reported holdings, not reconciled total wealth. Position weights do not "
            "establish fund look-through diversification, suitability, returns or trading permission.",
            "Estas posições vêm das fontes, não representam património total reconciliado. Os pesos não "
            "demonstram a diversificação interna dos fundos, adequação, rendimentos ou autorização para negociar.",
        )
    )
    return "\n\n".join(lines)
