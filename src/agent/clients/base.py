"""Abstract base class for all LLM clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from collections.abc import AsyncGenerator


class BaseLLMClient(ABC):
    """
    Common interface every LLM backend must implement.

    stream_response() drives the full agent loop — text streaming *and*
    tool-use — so the orchestrator stays provider-agnostic.
    """

    @abstractmethod
    async def stream_response(
        self,
        messages: list[dict[str, Any]],
        system: str,
        max_tokens: int | None = None,
        response_schema: dict | None = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Async generator that yields typed events until the turn is complete.

        response_schema selects tool-free structured inference. The caller must
        validate domain semantics; valid JSON/schema shape is not factual proof.
        Structured inference never routes requests to tools or prose repair.

        Events
        ------
        {"type": "final_answer", "text": str}
        {"type": "tool_call",    "name": str, "input": dict, "id": str}
        {"type": "tool_result",  "name": str, "result": str, "id": str}
        {"type": "done"}
        """
        # Make the abstract method a proper async generator for type-checking.
        # Subclasses override this; the yield here satisfies the return type.
        yield {}  # pragma: no cover
