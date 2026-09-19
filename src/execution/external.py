"""The external-write gate is closed until independently accepted and mandated.

No environment variable, model tool, simulator approval or port number opens it.
Retained SDK write functions are preserved behind this shared boundary for future
contract implementation; no caller can accidentally invoke their legacy bodies.
"""

from functools import wraps


def external_write_denied(operation: str) -> dict:
    return {
        "blocked": True,
        "success": False,
        "reason_code": "EXTERNAL_WRITES_NOT_AUTHORIZED",
        "reason": (f"External {operation} requires verified account acceptance and explicit authority."),
    }


def disabled_external_write(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        return external_write_denied(function.__name__)

    return guarded
