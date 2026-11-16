import asyncio
import unittest

from astrbot_plugin_zhiban.coalescing import MessageCoalescer


class CoalescerTests(unittest.IsolatedAsyncioTestCase):
    async def test_consecutive_same_author_merge_once(self):
        c = MessageCoalescer(quiet_seconds=0.08, max_seconds=0.5)
        leader = asyncio.create_task(c.join("group:1|user:1", "第一句", "m1"))
        await asyncio.sleep(0.01)
        follower = await c.join("group:1|user:1", "第二句", "m2")
        await asyncio.sleep(0.01)
        await c.join("group:1|user:1", "第三句", "m3")
        ok, text, ids = await leader
        self.assertTrue(ok)
        self.assertEqual(text, "第一句\n第二句\n第三句")
        self.assertEqual(ids, ["m1", "m2", "m3"])
        self.assertEqual(follower, (False, "", []))
        status = c.status()
        self.assertEqual(status["flushed_batches"], 1)
        self.assertEqual(status["coalesced_messages"], 2)

    async def test_different_conversations_and_authors_are_isolated(self):
        c = MessageCoalescer(quiet_seconds=0.05, max_seconds=0.3)
        a = asyncio.create_task(c.join("group:1|user:a", "A", "a1"))
        b = asyncio.create_task(c.join("group:1|user:b", "B", "b1"))
        c2 = asyncio.create_task(c.join("group:2|user:a", "C", "c1"))
        results = await asyncio.gather(a, b, c2)
        self.assertEqual([r[1] for r in results], ["A", "B", "C"])
        self.assertTrue(all(r[0] for r in results))

    async def test_max_messages_flush_early(self):
        c = MessageCoalescer(quiet_seconds=1.0, max_seconds=5.0, max_messages=3)
        leader = asyncio.create_task(c.join("k", "1", "m1"))
        await asyncio.sleep(0.01)
        await c.join("k", "2", "m2")
        await c.join("k", "3", "m3")
        ok, text, ids = await asyncio.wait_for(leader, timeout=0.5)
        self.assertTrue(ok)
        self.assertEqual(text, "1\n2\n3")
        self.assertEqual(len(ids), 3)

    async def test_max_chars_flush_early(self):
        c = MessageCoalescer(quiet_seconds=1.0, max_seconds=5.0, max_chars=100)
        leader = asyncio.create_task(c.join("k", "a" * 60, "m1"))
        await asyncio.sleep(0.01)
        await c.join("k", "b" * 60, "m2")
        ok, text, ids = await asyncio.wait_for(leader, timeout=0.5)
        self.assertTrue(ok)
        self.assertEqual(text, ("a" * 60) + "\n" + ("b" * 60))
        self.assertEqual(len(ids), 2)

    async def test_close_releases_waiting_leader(self):
        c = MessageCoalescer(quiet_seconds=1.0, max_seconds=5.0)
        leader = asyncio.create_task(c.join("k", "only", "m1"))
        await asyncio.sleep(0.01)
        await c.close()
        ok, text, _ = await asyncio.wait_for(leader, timeout=0.5)
        self.assertTrue(ok)
        self.assertEqual(text, "only")
        self.assertEqual(c.status()["active_batches"], 0)


if __name__ == "__main__":
    unittest.main()
