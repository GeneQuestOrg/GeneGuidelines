from __future__ import annotations

import unittest

from backend.memory.inmemory import InMemoryMemoryStore


class InMemoryMemoryStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_context_empty(self) -> None:
        store = InMemoryMemoryStore()
        ctx = await store.get_context(ticket_id=1, flow_key="f", recent_n=5)
        self.assertEqual(ctx.latest_summary_text, "")
        self.assertEqual(ctx.recent_turns, [])
        self.assertEqual(ctx.recent_as_text, "")

    async def test_append_turns_updates_latest_summary_and_recent(self) -> None:
        store = InMemoryMemoryStore()
        await store.append_turns(
            ticket_id=1,
            flow_key="f",
            node_id="n1",
            user_content="u1",
            assistant_content="a1",
            latest_summary_text="latest1",
        )
        ctx = await store.get_context(ticket_id=1, flow_key="f", recent_n=10)
        self.assertEqual(ctx.latest_summary_text, "latest1")
        # Two turns: user + assistant.
        self.assertEqual(len(ctx.recent_turns), 2)
        self.assertEqual(ctx.recent_turns[0].role, "user")
        self.assertEqual(ctx.recent_turns[0].content_text, "u1")
        self.assertEqual(ctx.recent_turns[1].role, "assistant")
        self.assertEqual(ctx.recent_turns[1].content_text, "a1")
        self.assertIn("user: u1", ctx.recent_as_text)
        self.assertIn("assistant: a1", ctx.recent_as_text)

    async def test_recent_n_truncation(self) -> None:
        store = InMemoryMemoryStore()
        await store.append_turns(
            ticket_id=1,
            flow_key="f",
            node_id="n1",
            user_content="u1",
            assistant_content="a1",
            latest_summary_text="latest1",
        )
        await store.append_turns(
            ticket_id=1,
            flow_key="f",
            node_id="n2",
            user_content="u2",
            assistant_content="a2",
            latest_summary_text="latest2",
        )
        # recent_n=1 => just last turn (assistant of second node)
        ctx = await store.get_context(ticket_id=1, flow_key="f", recent_n=1)
        self.assertEqual(ctx.latest_summary_text, "latest2")
        self.assertEqual(len(ctx.recent_turns), 1)
        self.assertEqual(ctx.recent_turns[0].role, "assistant")
        self.assertEqual(ctx.recent_turns[0].content_text, "a2")


if __name__ == "__main__":
    unittest.main()

