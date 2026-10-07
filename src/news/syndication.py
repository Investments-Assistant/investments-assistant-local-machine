"""Conservative copy grouping; distinct text never proves independent reporting."""

from __future__ import annotations

import hashlib
import unicodedata

METHOD = "normalized_exact_text_v1"


def fingerprint(article: dict) -> dict:
    """Fingerprint substantive text, never a shared short headline or topic tag.

    No fuzzy similarity: preserve numbers, punctuation and case so corrections
    remain distinct. Missing/short text falls back to the attributed URL/hash.
    """
    text = article.get("content") or article.get("summary") or ""
    normalized = " ".join(unicodedata.normalize("NFKC", text).split())
    matchable = len(normalized) >= 80 and len(normalized.split()) >= 12
    basis = normalized if matchable else str(article.get("url")) + "\0" + str(article.get("content_hash"))
    return {
        "method": METHOD if matchable else "attributed_record_v1",
        "group_id": hashlib.sha256(basis.encode()).hexdigest(),
    }


def group_evidence(articles: list[dict]) -> list[dict]:
    """Collapse copies only inside this already authorized, time-filtered batch.

    Preserve ranking and the first representative. Copy references retain their
    own availability: they are not retroactive corroboration of earlier copies.
    Never look up other owners or future revisions to count a group.
    """
    grouped = {}
    for article in articles:
        item = dict(article)
        identity = item.pop("_syndication", None) or fingerprint(item)
        key = (identity["method"], identity["group_id"])
        copy = {
            field: item.get(field)
            for field in ("url", "source", "available_at", "content_hash", "revision_id")
        }
        if key not in grouped:
            item["syndication"] = {
                **identity,
                "scope": "authorized_retrieved_batch_only",
                "independent_corroboration": "unverified",
                "copies": [],
            }
            grouped[key] = item
        grouped[key]["syndication"]["copies"].append(copy)
    return list(grouped.values())
