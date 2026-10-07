"""Attribution quality for source-declared language and entity mentions.

These observations never qualify a contract or confer execution authority.
"""

import re

_CURRENCIES = {"EUR", "USD", "GBP", "JPY", "CHF", "CAD"}


def language_observation(value):
    # Conservative supported tag syntax, not a language detector or a complete
    # language-registry validator. Unrecognized input is explicitly unavailable.
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8}){0,3}", value):
        return {"tag": "unknown", "status": "unavailable", "method": "source_declaration_v1"}
    return {"tag": value.lower(), "status": "declared_unverified", "method": "source_declaration_v1"}


def entity_observations(tags):
    candidates = tags if isinstance(tags, list) else []
    return [
        {"mention": tag, "kind": "currency_code_candidate" if tag in _CURRENCIES else "ticker_candidate",
         "method": "source_tag_v1", "mapping_status": "unresolved", "qualified_instrument": None}
        for tag in sorted({tag for tag in candidates[:100]
                           if isinstance(tag, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9.:-]{0,31}", tag)})
    ]
