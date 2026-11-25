"""What the guideline-points code needs from the outside, as Protocols: a model caller and a spend ledger.

``llm.ClaudePointsCaller`` implements the caller with Claude; the job records spend in the research token ledger, the lab in its own capped ledger, and tests pass fakes. The loop and, later, the bricks depend only on these Protocols, never on the adapter.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class Budget(Protocol):
    """Where each call's spend goes: ``reserve`` before the call (it may refuse), ``settle`` after it with the real usage, returning the cost in USD."""

    def reserve(self, model: str, prompt_chars: int, max_tokens: int) -> Any: ...

    def settle(self, ticket: Any, model: str, usage: dict[str, Any], role: str, error: str | None) -> float | None: ...


class PointsCaller(Protocol):
    """One model role. Returns the parsed answer (None when the call failed or was refused) and the call's record: usage, cost, error, attempts."""

    async def call(self, *, role: str, system: str, prefix: str, user: str, result_type: type[BaseModel], cache: bool = True) -> tuple[BaseModel | None, dict[str, Any]]: ...


__all__ = ["Budget", "PointsCaller"]
