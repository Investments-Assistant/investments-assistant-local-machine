"""Expense categories used by the dashboard and provider adapters.

The taxonomy deliberately keeps a stable top-level category and a more
specific subcategory. Providers can supply their own labels, but the
normaliser maps them into this set so summaries remain comparable over time.
"""

from __future__ import annotations

from typing import TypedDict
from collections.abc import Iterable


class CategoryDefinition(TypedDict):
    label: str
    icon: str
    subcategories: list[str]


CATEGORY_TAXONOMY: dict[str, CategoryDefinition] = {
    "housing": {
        "label": "Housing",
        "icon": "⌂",
        "subcategories": [
            "rent",
            "mortgage",
            "electricity",
            "water",
            "gas",
            "internet",
            "mobile phone",
            "home insurance",
            "property tax",
            "home maintenance",
            "household supplies",
            "cleaning services",
            "security",
        ],
    },
    "food": {
        "label": "Food & dining",
        "icon": "◌",
        "subcategories": [
            "groceries",
            "restaurants",
            "takeaway",
            "food delivery",
            "cafes",
            "coffee",
            "alcohol",
            "snacks",
        ],
    },
    "transport": {
        "label": "Transport",
        "icon": "⌁",
        "subcategories": [
            "car fuel",
            "car maintenance",
            "car insurance",
            "car payment",
            "vehicle tax",
            "vehicle registration",
            "parking",
            "tolls",
            "public transport",
            "taxi & rideshare",
            "bike & scooter",
        ],
    },
    "health": {
        "label": "Health",
        "icon": "+",
        "subcategories": [
            "doctor",
            "dentist",
            "pharmacy",
            "mental health",
            "health insurance",
            "fitness",
            "wellness",
            "optician",
        ],
    },
    "personal": {
        "label": "Personal",
        "icon": "✦",
        "subcategories": [
            "clothing",
            "personal care",
            "hair & beauty",
            "childcare",
            "education",
            "professional development",
            "electronics",
            "services",
        ],
    },
    "leisure": {
        "label": "Leisure & pleasure",
        "icon": "✧",
        "subcategories": [
            "entertainment",
            "streaming",
            "music",
            "games",
            "books",
            "hobbies",
            "sport",
            "events",
            "travel",
            "flights",
            "hotels",
        ],
    },
    "financial": {
        "label": "Financial",
        "icon": "€",
        "subcategories": [
            "bank fees",
            "interest",
            "taxes",
            "debt repayment",
            "investments",
            "cash withdrawal",
            "currency exchange",
        ],
    },
    "family": {
        "label": "Family & gifts",
        "icon": "♡",
        "subcategories": ["gifts", "donations", "child support", "family support", "weddings"],
    },
    "pets": {
        "label": "Pets",
        "icon": "◇",
        "subcategories": ["pet food", "vet", "pet insurance", "pet care", "pet supplies"],
    },
    "work": {
        "label": "Work & business",
        "icon": "▣",
        "subcategories": [
            "office supplies",
            "software",
            "client meals",
            "work travel",
            "coworking",
        ],
    },
    "income": {
        "label": "Income",
        "icon": "↗",
        "subcategories": [
            "salary",
            "freelance",
            "interest income",
            "dividend",
            "refund",
            "other income",
        ],
    },
    "transfers": {
        "label": "Transfers",
        "icon": "↔",
        "subcategories": ["between own accounts", "card payment", "cash deposit", "other transfer"],
    },
    "other": {
        "label": "Other",
        "icon": "•",
        "subcategories": ["uncategorised"],
    },
}


# These are intentionally conservative fallbacks. A later categorisation pass
# can refine a transaction without changing its provider identity.
_KEYWORD_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("housing", "rent", ("rent", "landlord", "arrendamento")),
    ("housing", "mortgage", ("mortgage", "hipoteca")),
    ("housing", "electricity", ("electric", "edp", "energia")),
    ("housing", "water", ("water", "aguas", "água")),
    ("housing", "gas", ("gas", "galp")),
    ("housing", "internet", ("internet", "vodafone", "nos", "meo")),
    ("housing", "home insurance", ("home insurance", "seguro casa")),
    ("housing", "household supplies", ("ikea", "leroy", "household")),
    (
        "food",
        "groceries",
        ("continente", "pingo doce", "lidl", "aldi", "mercadona", "supermarket", "grocery"),
    ),
    ("food", "food delivery", ("uber eats", "ubereats", "glovo", "bolt food", "deliveroo")),
    ("food", "takeaway", ("takeaway", "mcdonald", "burger king", "pizza")),
    ("food", "cafes", ("cafe", "café", "bakery", "pastelaria")),
    (
        "transport",
        "car fuel",
        ("galp", "repsol", "bp ", "shell", "fuel", "combustivel", "combustível", "gas station"),
    ),
    (
        "transport",
        "car maintenance",
        ("garage", "oficina", "mechanic", "midas", "norauto", "tyre", "pneu"),
    ),
    ("transport", "car insurance", ("car insurance", "seguro auto")),
    ("transport", "parking", ("parking", "parque", "emel")),
    ("transport", "tolls", ("toll", "portagem", "via verde")),
    (
        "transport",
        "public transport",
        ("metro", "carris", "cp ", "train", "comboio", "bus", "autocarro"),
    ),
    ("transport", "taxi & rideshare", ("uber", "bolt", "taxi")),
    ("health", "pharmacy", ("pharmacy", "farmacia", "farmácia")),
    ("health", "doctor", ("hospital", "clinic", "clinica", "clínica", "doctor", "médico")),
    ("health", "dentist", ("dentist", "dentista")),
    ("health", "fitness", ("gym", "fitness", "solinca", "fitness hut")),
    ("personal", "clothing", ("zara", "h&m", "uniqlo", "clothing", "clothes")),
    ("personal", "hair & beauty", ("hair", "cabeleireiro", "beauty", "barber", "barbeiro")),
    ("personal", "electronics", ("fnac", "worten", "apple store", "electronics")),
    (
        "leisure",
        "streaming",
        ("netflix", "spotify", "disney+", "prime video", "youtube premium", "hbo"),
    ),
    ("leisure", "games", ("steam", "playstation", "xbox", "nintendo")),
    ("leisure", "travel", ("airbnb", "booking.com", "ryanair", "easyjet", "flight", "hotel")),
    ("financial", "bank fees", ("bank fee", "commission", "comissão", "maintenance fee")),
    ("financial", "cash withdrawal", ("atm", "cash withdrawal", "levantamento")),
    ("family", "donations", ("donation", "donativo", "charity")),
    ("pets", "vet", ("vet", "veterin", "veterinário")),
)


def _text(values: Iterable[object]) -> str:
    return " ".join(str(value or "") for value in values).strip().lower()


def normalise_category(
    category: object,
    subcategory: object,
    merchant: object,
    description: object,
    transaction_type: str,
) -> tuple[str, str]:
    """Return a valid taxonomy pair, inferring it when the provider omitted one."""
    category_key = str(category or "").strip().lower().replace(" ", "_")
    subcategory_value = str(subcategory or "").strip().lower()
    if category_key in CATEGORY_TAXONOMY:
        valid_subcategories = {
            str(item) for item in CATEGORY_TAXONOMY[category_key]["subcategories"]
        }
        if subcategory_value in valid_subcategories:
            return category_key, subcategory_value
        return category_key, subcategory_value or str(
            CATEGORY_TAXONOMY[category_key]["subcategories"][0]
        )

    if transaction_type == "refund":
        return "income", "refund"
    if transaction_type == "income":
        return "income", subcategory_value or "other income"
    if transaction_type == "transfer":
        return "transfers", subcategory_value or "other transfer"

    haystack = _text((merchant, description))
    for candidate_category, candidate_subcategory, keywords in _KEYWORD_RULES:
        if any(keyword in haystack for keyword in keywords):
            return candidate_category, candidate_subcategory
    return "other", "uncategorised"


def category_label(category: str) -> str:
    definition = CATEGORY_TAXONOMY.get(category)
    return str(definition["label"]) if definition else category.replace("_", " ").title()
