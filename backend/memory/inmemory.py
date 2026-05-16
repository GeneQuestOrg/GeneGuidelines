from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List

from .store import MemoryContext, MemoryStore, MemoryTurn


@dataclass
class _Conversation:
    latest_summary_text: str = ""
    turns: List[MemoryTurn] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.turns is None:
            self.turns = []


class InMemoryMemoryStore(MemoryStore):
    """
    MVP fallback for tests / dev:
    - keeps memory in process memory only
    - matches MemoryStore contract
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._conversations: Dict[tuple[int, str], _Conversation] = {}

    async def ensure_schema(self) -> None:
        # Nothing to do.
        return

    async def get_context(self, *, ticket_id: int, flow_key: str, recent_n: int) -> MemoryContext:
        async with self._lock:
            conv = self._conversations.get((ticket_id, flow_key))
            if not conv:
                return MemoryContext(latest_summary_text="", recent_turns=[])
            recent_turns = (conv.turns or [])[-max(0, int(recent_n)) :]
            return MemoryContext(latest_summary_text=conv.latest_summary_text or "", recent_turns=recent_turns)

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
        async with self._lock:
            key = (ticket_id, flow_key)
            conv = self._conversations.get(key)
            if not conv:
                conv = _Conversation()
                self._conversations[key] = conv

            now = datetime.now()
            conv.latest_summary_text = latest_summary_text or conv.latest_summary_text

            # Keep it explicit: user then assistant.
            conv.turns.append(MemoryTurn(role="user", content_text=str(user_content or ""), created_at=now))
            conv.turns.append(MemoryTurn(role="assistant", content_text=str(assistant_content or ""), created_at=now + timedelta(milliseconds=1)))

