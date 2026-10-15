"""Publish only caller-owned error codes, never arbitrary exception text."""

from collections.abc import Collection


def safe_exception_code(
    exc: BaseException, *, fallback: str, allowed_codes: Collection[str] = (),
) -> str:
    """Preserve an explicitly permitted complete code, otherwise use the fallback.

    Both the fallback and allowlist must be fixed application definitions. A
    provider error, account identifier or credentialed URL cannot define them.
    Avoid even formatting an exception when no message is eligible for reuse.
    """
    if not allowed_codes:
        return fallback
    try:
        code = str(exc)
    except Exception:
        return fallback
    return code if code in allowed_codes else fallback
