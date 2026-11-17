from __future__ import annotations

import unittest
from types import SimpleNamespace

from astrbot_plugin_zhiban.main import ZhibanPlugin


class TerminationOrderingTests(unittest.IsolatedAsyncioTestCase):
    async def test_hosted_modules_are_closed_before_scheduler(self):
        order = []

        class Host:
            async def close(self):
                order.append("host")

        class ReplyDebounce:
            async def close(self):
                order.append("reply_debounce")

        class Persona:
            async def close(self):
                order.append("persona")

        class Scheduler:
            async def close(self):
                order.append("scheduler")

        plugin = object.__new__(ZhibanPlugin)
        plugin.reply_debounce = ReplyDebounce()
        plugin.host = Host()
        plugin.persona = Persona()
        plugin.scheduler = Scheduler()
        await plugin.terminate()
        self.assertEqual(order, ["reply_debounce", "host", "persona", "scheduler"])

    async def test_scheduler_closes_even_when_host_cleanup_fails(self):
        order = []

        class Host:
            async def close(self):
                order.append("host")
                raise RuntimeError("failed")

        class ReplyDebounce:
            async def close(self):
                order.append("reply_debounce")

        class Scheduler:
            async def close(self):
                order.append("scheduler")

        plugin = object.__new__(ZhibanPlugin)
        plugin.reply_debounce = ReplyDebounce()
        plugin.host = Host()
        plugin.persona = None
        plugin.scheduler = Scheduler()
        with self.assertRaisesRegex(RuntimeError, "failed"):
            await plugin.terminate()
        self.assertEqual(order, ["reply_debounce", "host", "scheduler"])


if __name__ == "__main__":
    unittest.main()
