from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1]))
from astrbot_plugin_zhiban.main import ZhibanPlugin


class UiStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_includes_live_scheduler_metrics(self):
        scheduler = {
            "running": 2,
            "waiting": 1,
            "media_running": True,
            "rejected": 3,
        }
        plugin = SimpleNamespace(
            host=SimpleNamespace(status=lambda: [], instances={}),
            config={"management": {"menu_order": []}},
            scheduler=SimpleNamespace(status=lambda: scheduler),
        )

        result = await ZhibanPlugin._ui_status(plugin)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["scheduler"], scheduler)


    async def test_qzone_requires_bound_cookie_for_business_readiness(self):
        class Controller:
            def __init__(self, cookie_count):
                self.cookie_count = cookie_count
                self.calls = 0

            async def get_status(self, probe_daemon=False):
                self.calls += 1
                return {"cookie_count": self.cookie_count, "needs_rebind": False, "daemon_state": "ready"}

        plugin = SimpleNamespace(host=SimpleNamespace(instances={"qzone": SimpleNamespace(controller=Controller(0))}))
        missing = await ZhibanPlugin._module_readiness(
            plugin,
            {"key": "qzone", "enabled": True, "running": True, "state": "running"},
        )
        self.assertEqual(missing["state"], "not_ready")
        self.assertIn("Cookie", missing["detail"])
        await ZhibanPlugin._module_readiness(
            plugin,
            {"key": "qzone", "enabled": True, "running": True, "state": "running"},
        )
        self.assertEqual(plugin.host.instances["qzone"].controller.calls, 1)

        plugin.host.instances["qzone"] = SimpleNamespace(controller=Controller(2))
        plugin._readiness_cache.clear()
        ready = await ZhibanPlugin._module_readiness(
            plugin,
            {"key": "qzone", "enabled": True, "running": True, "state": "running"},
        )
        self.assertEqual(ready["state"], "ready")

    async def test_memory_readiness_is_separate_from_running_lifecycle(self):
        initializer = SimpleNamespace(is_failed=False, is_initialized=False)
        plugin = SimpleNamespace(host=SimpleNamespace(instances={"memory": SimpleNamespace(initializer=initializer)}))
        result = await ZhibanPlugin._module_readiness(
            plugin,
            {"key": "memory", "enabled": True, "running": True, "state": "running"},
        )
        self.assertEqual(result["state"], "starting")
        initializer.is_initialized = True
        result = await ZhibanPlugin._module_readiness(
            plugin,
            {"key": "memory", "enabled": True, "running": True, "state": "running"},
        )
        self.assertEqual(result["state"], "ready")

    async def test_disabled_module_is_not_reported_as_running_or_ready(self):
        plugin = SimpleNamespace(host=SimpleNamespace(instances={}))
        result = await ZhibanPlugin._module_readiness(
            plugin,
            {"key": "heart", "enabled": False, "running": False, "state": "disabled"},
        )
        self.assertEqual(result["state"], "disabled")


if __name__ == "__main__":
    unittest.main()
