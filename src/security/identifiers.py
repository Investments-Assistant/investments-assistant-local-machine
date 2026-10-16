"""Exact local login identifiers; no case folding or Unicode normalization."""

import hashlib


def username_key(username: str) -> bytes:
    """Bound index size without changing the identifier's original UTF-8 text."""
    if not isinstance(username, str):
        raise TypeError("Login ID must be a string")
    return hashlib.sha256(username.encode("utf-8")).digest()
