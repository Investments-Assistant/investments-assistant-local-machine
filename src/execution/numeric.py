"""Task-local exact intermediate precision at execution arithmetic boundaries."""

from decimal import Context, localcontext
from inspect import iscoroutinefunction
from functools import wraps


def execution_precision(function):
    """Independent of caller precision/rounding/traps; restore them on every exit.

    Inputs are bounded fixed-point values. 128 digits cover products of four
    28-digit ledger values and the bounded account aggregates.
    This does not round ledger writes or relax their ten-decimal validation.
    """
    if iscoroutinefunction(function):

        @wraps(function)
        async def asynchronous(*args, **kwargs):
            with localcontext(Context(prec=128)):
                return await function(*args, **kwargs)

        return asynchronous

    @wraps(function)
    def synchronous(*args, **kwargs):
        with localcontext(Context(prec=128)):
            return function(*args, **kwargs)

    return synchronous
