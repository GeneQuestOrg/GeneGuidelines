from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List

from .store import MemoryContext, MemoryStore, MemoryTurn, memory_excerpt


@dataclass(frozen=True)
class _PgConfig:
    dsn: str


def _load_pg_config() -> _PgConfig:
    dsn = (os.environ.get("MEMORY_POSTGRES_DSN") or "").strip()
    if not dsn:
        raise RuntimeError("MEMORY_POSTGRES_DSN is not set")
    return _PgConfig(dsn=dsn)


class PostgresMemoryStore(MemoryStore):
    """
    Postgres-backed memory store.
    Tables:
      - memory_conversations(ticket_id, flow_key, latest_summary_text, updated_at)
      - memory_turns(id, ticket_id, flow_key, node_id, turn_index, role, content_text, created_at)
    """

    def __init__(self) -> None:
        self._config: _PgConfig | None = None

    def _ensure_config(self) -> _PgConfig:
        if self._config is None:
            self._config = _load_pg_config()
        return self._config

    async def ensure_schema(self) -> None:
        cfg = self._ensure_config()

        def _sync() -> None:
            import psycopg

            with psycopg.connect(cfg.dsn, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS memory_conversations (
                          ticket_id BIGINT NOT NULL,
                          flow_key TEXT NOT NULL,
                          latest_summary_text TEXT NOT NULL DEFAULT '',
                          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                          PRIMARY KEY(ticket_id, flow_key)
                        );
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS memory_turns (
                          id BIGSERIAL PRIMARY KEY,
                          ticket_id BIGINT NOT NULL,
                          flow_key TEXT NOT NULL,
                          node_id TEXT NOT NULL,
                          turn_index INTEGER NOT NULL,
                          role TEXT NOT NULL,
                          content_text TEXT NOT NULL,
                          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );
                        """
                    )
                    cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_memory_turns_conv
                        ON memory_turns(ticket_id, flow_key, created_at DESC);
                        """
                    )

        await asyncio.to_thread(_sync)

    async def get_context(self, *, ticket_id: int, flow_key: str, recent_n: int) -> MemoryContext:
        cfg = self._ensure_config()
        rn = max(0, int(recent_n))

        def _sync() -> MemoryContext:
            import psycopg

            with psycopg.connect(cfg.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT latest_summary_text FROM memory_conversations WHERE ticket_id=%s AND flow_key=%s",
                        (ticket_id, flow_key),
                    )
                    row = cur.fetchone()
                    latest_summary_text = str(row[0]) if row and row[0] is not None else ""

                    if rn <= 0:
                        return MemoryContext(latest_summary_text=latest_summary_text, recent_turns=[])

                    cur.execute(
                        """
                        SELECT role, content_text, created_at
                        FROM memory_turns
                        WHERE ticket_id=%s AND flow_key=%s
                        ORDER BY created_at DESC, id DESC
                        LIMIT %s
                        """,
                        (ticket_id, flow_key, rn),
                    )
                    rows = cur.fetchall()
                    # Reverse to preserve chronological order for prompting.
                    rows.reverse()
                    recent_turns: List[MemoryTurn] = []
                    for role, content_text, created_at in rows:
                        if not role:
                            continue
                        created_dt = created_at if isinstance(created_at, datetime) else datetime.now()
                        recent_turns.append(
                            MemoryTurn(role=str(role), content_text=str(content_text or ""), created_at=created_dt)
                        )
                    return MemoryContext(latest_summary_text=latest_summary_text, recent_turns=recent_turns)

        return await asyncio.to_thread(_sync)

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
        cfg = self._ensure_config()

        # Best-effort trim to avoid gigantic prompt payloads.
        user_content_s = memory_excerpt(str(user_content or ""), max_chars=8000)
        assistant_content_s = memory_excerpt(str(assistant_content or ""), max_chars=8000)
        latest_summary_text_s = memory_excerpt(str(latest_summary_text or ""), max_chars=4000)

        def _sync() -> None:
            import psycopg

            with psycopg.connect(cfg.dsn, autocommit=True) as conn:
                with conn.cursor() as cur:
                    # Get next turn_index.
                    cur.execute(
                        "SELECT COALESCE(MAX(turn_index), 0) FROM memory_turns WHERE ticket_id=%s AND flow_key=%s",
                        (ticket_id, flow_key),
                    )
                    max_idx = cur.fetchone()[0] or 0
                    next_idx = int(max_idx)

                    user_role = "user"
                    assistant_role = "assistant"
                    # user
                    cur.execute(
                        """
                        INSERT INTO memory_turns(ticket_id, flow_key, node_id, turn_index, role, content_text)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (ticket_id, flow_key, node_id, next_idx + 1, user_role, user_content_s),
                    )
                    # assistant
                    cur.execute(
                        """
                        INSERT INTO memory_turns(ticket_id, flow_key, node_id, turn_index, role, content_text)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (ticket_id, flow_key, node_id, next_idx + 2, assistant_role, assistant_content_s),
                    )

                    cur.execute(
                        """
                        INSERT INTO memory_conversations(ticket_id, flow_key, latest_summary_text, updated_at)
                        VALUES (%s, %s, %s, NOW())
                        ON CONFLICT(ticket_id, flow_key)
                        DO UPDATE SET latest_summary_text=EXCLUDED.latest_summary_text, updated_at=NOW()
                        """,
                        (ticket_id, flow_key, latest_summary_text_s),
                    )

        await asyncio.to_thread(_sync)

