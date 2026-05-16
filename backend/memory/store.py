from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MemoryTurn:
    role: str  # "user" | "assistant"
    content_text: str
    created_at: datetime


@dataclass(frozen=True)
class MemoryContext:
    latest_summary_text: str
    recent_turns: list[MemoryTurn]

    @property
    def recent_as_text(self) -> str:
        # Friendly-to-prompt formatting.
        lines: list[str] = []
        for t in self.recent_turns:
            role = (t.role or "").strip()
            lines.append(f"{role}: {t.content_text}".strip())
        return "\n".join(lines) if lines else ""


class MemoryStore(abc.ABC):
    """
    Persistent conversation memory.

    Contract:
    - get_context() returns latest summary + last N turns.
    - append_turns() stores new user/assistant turns and updates latest summary best-effort.
    """

    @abc.abstractmethod
    async def ensure_schema(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_context(self, *, ticket_id: int, flow_key: str, recent_n: int) -> MemoryContext:
        raise NotImplementedError

    @abc.abstractmethod
    async def append_turns(
        self,
        *,
        ticket_id: int,
        flow_key: str,
        node_id: str,
        user_content: str,
        assistant_content: str,
        latest_summary_text: str,
    ) -> None:
        raise NotImplementedError


def memory_excerpt(s: str, max_chars: int = 1200) -> str:
    s = (s or "").strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "…"

