from __future__ import annotations

import asyncio
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

QZONE_ROOT = Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "modules" / "astrbot_plugin_qzone_ultra"
sys.path.insert(0, str(QZONE_ROOT))
from qzone_bridge.controller import QzoneDaemonController  # noqa: E402


class _BudgetProbe:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.enters = 0
        self.exits = 0

    @asynccontextmanager
    async def maintenance(self):
        self.enters += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            yield
        finally:
            self.active -= 1
            self.exits += 1


class QzoneDaemonBudgetTests(unittest.IsolatedAsyncioTestCase):
    def _controller(self, budget):
        controller = object.__new__(QzoneDaemonController)
        controller._lock = asyncio.Lock()
        controller._budget = budget
        controller._budget_events = {"starts": 0, "stops": 0, "rejections": 0}
        return controller

    async def test_daemon_start_and_stop_hold_shared_maintenance_ticket(self):
        budget = _BudgetProbe()
        controller = self._controller(budget)

        async def start_locked():
            self.assertEqual(budget.active, 1)
            return {"daemon_state": "ready"}

        async def stop_locked():
            self.assertEqual(budget.active, 1)

        controller._ensure_running_locked = start_locked
        controller._stop_daemon_locked = stop_locked
        self.assertEqual(await controller.ensure_running(), {"daemon_state": "ready"})
        await controller.stop_daemon()
        self.assertEqual(budget.enters, 2)
        self.assertEqual(budget.exits, 2)
        self.assertEqual(budget.active, 0)
        self.assertEqual(budget.max_active, 1)
        self.assertEqual(controller._budget_events, {"starts": 1, "stops": 1, "rejections": 0})

    async def test_daemon_lifecycle_still_works_without_budget(self):
        controller = self._controller(None)

        async def start_locked():
            return {"daemon_state": "ready"}

        async def stop_locked():
            return None

        controller._ensure_running_locked = start_locked
        controller._stop_daemon_locked = stop_locked
        self.assertEqual(await controller.ensure_running(), {"daemon_state": "ready"})
        await controller.stop_daemon()
        self.assertEqual(controller._budget_events, {"starts": 1, "stops": 1, "rejections": 0})


if __name__ == "__main__":
    unittest.main()
