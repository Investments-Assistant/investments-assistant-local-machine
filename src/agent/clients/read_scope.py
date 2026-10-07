"""Conservative explicit read exclusions from user turns, never tool evidence.

This narrows existing authorization; it cannot grant an account capability.
"""

import re

_SCOPES = {
    "portfolio": r"\b(?:portfolio|holdings|positions|broker account|carteira|posições)\b",
    "news": r"\b(?:news|headlines?|notícias|noticias)\b",
    "report": r"\b(?:reports?|relatório|relatorio)\b",
    "simulation": r"\b(?:simulation|simulate|backtest|simulação|simulacao)\b",
    "market": r"\b(?:market overview|market snapshot|visão do mercado)\b",
}
TOOLS = {
    "portfolio": {"get_portfolio_summary", "get_account_info", "get_trade_history", "generate_report", "execute_trade"},
    "news": {"search_market_news", "search_stored_news", "get_latest_news", "generate_report"},
    "market": {"get_market_overview", "generate_report"},
    "report": {"generate_report"},
    "simulation": {"run_simulation"},
}
_NEGATION = re.compile(r"\b(?:do not|don't|don’t|dont|never|without|exclude|skip|avoid|não|nao)\b", re.I)
_ALLOW = re.compile(
    r"\b(?:you may access|you may read|allow access to|allow reading|podes aceder|pode acessar)\b", re.I
)
_CLAUSES = re.compile(r"[.!?;\n]+|\b(?:but|instead|mas)\b", re.I)


def read_exclusions(messages):
    denied = set()
    for message in messages:
        if message.get("role") != "user":
            continue
        for clause in _CLAUSES.split(str(message.get("content", ""))):
            scopes = {scope for scope, pattern in _SCOPES.items() if re.search(pattern, clause, re.I)}
            if _NEGATION.search(clause):
                denied.update(scopes)
            elif _ALLOW.search(clause):
                denied.difference_update(scopes)
    return denied


def denied_tools(messages):
    return set().union(*(TOOLS[scope] for scope in read_exclusions(messages)))


def positive_request(messages):
    """Remove excluded scope mentions before the existing factual classifier.

    Keep unrelated clauses so an explicit no-portfolio instruction does not prevent
    a news request. Ambiguous negative clauses conservatively exclude named scopes.
    """
    latest = next((str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"), "")
    denied = read_exclusions(messages)
    if not denied and not _NEGATION.search(latest):
        return latest
    clauses = [clause for clause in _CLAUSES.split(latest) if not _NEGATION.search(clause)]
    text = ". ".join(clauses)
    for scope in denied:
        text = re.sub(_SCOPES[scope], "", text, flags=re.I)
    return text


_REFRESH_READ = re.compile(
    r"(?:please\s+)?(?:refresh(?:\s+(?:that|it|those|this))?|"
    r"update\s+(?:that|it|those|this)|check\s+again|"
    r"atualiza(?:r)?\s+(?:isso|isto)|verifica\s+novamente)[.!?\s]*", re.I
)


def read_request(messages):
    """Resolve explicit refreshes of the latest user read request only.

    This context is for read routing, never report creation, simulation or orders.
    A different intervening user topic is a boundary; assistant/tool text cannot
    supply a scope. All exclusions from the original history still apply at dispatch.
    """
    users = [m for m in messages if m.get("role") == "user"]
    while len(users) > 1 and _REFRESH_READ.fullmatch(str(users[-1].get("content", "")).strip()):
        users.pop()
    if not users:
        return ""
    request = positive_request(users)
    # A follow-up must not turn a prior action into a read or repeat its authority.
    if len(users) != sum(m.get("role") == "user" for m in messages) and re.search(
        r"\b(?:buy|sell|order|execute|cancel|confirm|approve|mode|mandate|"
        r"comprar|vender|aprovar|ordem)\b", request, re.I
    ):
        return ""
    return request


def read_exclusion_answer(messages):
    """Explain a requested but excluded scope using only the user's own turns."""
    users = [m for m in messages if m.get("role") == "user"]
    while len(users) > 1 and _REFRESH_READ.fullmatch(str(users[-1].get("content", "")).strip()):
        users.pop()
    latest = str(users[-1].get("content", "")) if users else ""
    blocked = sorted(scope for scope in read_exclusions(messages)
                     if re.search(_SCOPES[scope], latest, re.I))
    if not blocked:
        return None
    names = ", ".join(blocked)
    preference = "market overview" if blocked[0] == "market" else blocked[0]
    return (f"I did not access {names} data because you excluded that scope in this conversation. "
            f'To change your read preference, explicitly say "You may access my {preference}". '
            "This does not grant trading permission or change account access.")
