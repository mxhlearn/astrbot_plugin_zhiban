"""Ownership/lifecycle regression tests without network or a live AstrBot root."""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import logging
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

RUNTIME_PATH = Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "runtime.py"
spec = importlib.util.spec_from_file_location("zhiban_runtime_under_test", RUNTIME_PATH)
runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime
spec.loader.exec_module(runtime)


class Registry(list):
    def remove(self, item):
        if item in self:
            super().remove(item)


class Tools:
    def __init__(self):
        self.func_list = []

    def remove_func(self, name):
        self.func_list[:] = [t for t in self.func_list if t.name != name]


class ParentConfig(dict):
    saved = 0

    def save_config(self, **kwargs):
        self.saved += 1
        self.snapshot = copy.deepcopy(dict(self))


class Parent:
    __module__ = "testzhiban.main"


class HostTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stars = {"testzhiban.main": types.SimpleNamespace(star_handler_full_names=[])}
        self.registry = []
        self.handlers = Registry()
        self.tools = Tools()
        self.context = types.SimpleNamespace(
            provider_manager=types.SimpleNamespace(llm_tools=self.tools), registered_web_apis=[])

        def add_tools(*tools):
            for tool in tools:
                self.tools.remove_func(tool.name)
                self.tools.func_list.append(tool)

        def add_route(route, handler, methods, desc):
            self.context.registered_web_apis[:] = [api for api in self.context.registered_web_apis
                                                  if (api[0], api[2]) != (route, methods)]
            self.context.registered_web_apis.append((route, handler, methods, desc))

        self.context.add_llm_tools = add_tools
        self.context.register_web_api = add_route
        self.parent = Parent()
        self.parent.context = self.context
        self.parent.logger = logging.getLogger("test.zhiban")
        self.config = ParentConfig(chat={"enabled": True, "settings": {"example": 7}})
        self.specs = [{"key": "chat", "label": "聊天互动", "package": "astrbot_plugin_fake"}]
        self.terminated = 0
        self.imports = 0
        self.fail_initialize = False
        self.fail_terminate = False
        self.register_tool = True
        self.patch_framework = patch.object(runtime, "_framework",
                                            return_value=(self.stars, self.registry, self.handlers, self.tools))
        self.real_import_module = runtime.importlib.import_module
        self.patch_import = patch.object(runtime.importlib, "import_module", side_effect=self.import_module)
        self.patch_framework.start()
        self.patch_import.start()

    def tearDown(self):
        self.patch_import.stop()
        self.patch_framework.stop()
        for key in list(sys.modules):
            if key.startswith("testzhiban.modules."):
                sys.modules.pop(key)
        self.temp.cleanup()

    def import_module(self, name, package=None):
        if not name.startswith("testzhiban.modules."):
            if package is None:
                return self.real_import_module(name)
            return self.real_import_module(name, package)
        self.imports += 1
        outer = self
        module = types.ModuleType(name)
        module.__file__ = str(self.root / "main.py")

        class Child:
            def __init__(self, context, config):
                self.context = context
                self.config = config
                if outer.register_tool:
                    context.add_llm_tools(types.SimpleNamespace(name="fake_tool", handler=None,
                                                               handler_module_path=name, active=True))
                context.register_web_api("/fake", self.web, ["GET"], "test")

            async def initialize(self):
                if outer.fail_initialize:
                    raise ValueError("sensitive config should not appear in status")

            async def terminate(self):
                outer.terminated += 1
                if outer.fail_terminate:
                    raise RuntimeError("failed")

            async def event(self, event):
                event.append(self.config["example"])

            async def web(self):
                return "ok"

        Child.__module__ = name
        Child.event.__module__ = name
        module.Child = Child
        metadata = types.SimpleNamespace(module_path=name, star_cls_type=Child, name="fake", activated=True)
        self.stars[name] = metadata
        self.registry.append(metadata)
        self.handlers.append(types.SimpleNamespace(
            handler_module_path=name, handler_full_name=name + "_event", handler_name="event",
            handler=Child.event, event_filters=["original filter"], extras_configs={"priority": 123}))
        sys.modules[name] = module
        return module

    def host(self):
        return runtime.ModuleHost(self.parent, self.config, self.specs, self.root / "data")

    async def test_bind_ownership_without_changing_filters_and_cleanup(self):
        host = self.host()
        status = await host.start()
        self.assertEqual(status[0]["state"], "running")
        self.assertEqual(self.registry, [])
        self.assertEqual(list(self.stars), ["testzhiban.main"])
        handler = self.handlers[0]
        self.assertEqual(handler.handler_module_path, "testzhiban.main")
        self.assertEqual(handler.event_filters, ["original filter"])
        self.assertEqual(handler.extras_configs["priority"], 123)
        result = []
        await handler.handler(result)
        self.assertEqual(result, [7])
        self.assertEqual(self.tools.func_list[0].handler_module_path, "testzhiban.main")
        await host.close()
        self.assertEqual(self.terminated, 1)
        self.assertEqual(self.handlers, [])
        self.assertEqual(self.tools.func_list, [])
        self.assertEqual(self.context.registered_web_apis, [])
        self.assertEqual(host.status()[0]["state"], "stopped")

    async def test_disabled_module_never_imported(self):
        self.config["chat"]["enabled"] = False
        host = self.host()
        self.assertEqual((await host.start())[0]["state"], "disabled")
        self.assertEqual(self.imports, 0)
        await host.close()

    async def test_running_original_blocks_before_import(self):
        self.registry.append(types.SimpleNamespace(name="fake", root_dir_name="astrbot_plugin_fake",
                                                  activated=True, star_cls=object(), module_path="old.main"))
        host = self.host()
        self.assertEqual((await host.start())[0]["state"], "blocked")
        self.assertEqual(self.imports, 0)
        await host.close()

    async def test_legacy_qzone_name_blocks_bundled_qzone_ultra(self):
        self.specs = [{"key": "qzone", "label": "QQ空间",
                       "package": "astrbot_plugin_qzone_ultra"}]
        self.config["qzone"] = {"enabled": True, "settings": {}}
        self.registry.append(types.SimpleNamespace(
            name="astrbot_plugin_qzone", root_dir_name="astrbot_plugin_qzone",
            activated=True, star_cls=object(),
            module_path="data.plugins.astrbot_plugin_qzone.main"))
        host = self.host()
        status = await host.start()
        self.assertEqual(status[0]["state"], "blocked")
        self.assertEqual(status[0]["error"], "原插件仍在运行：astrbot_plugin_qzone")
        self.assertEqual(self.imports, 0)
        await host.close()

    def test_qzone_runtime_errors_are_reported_without_paths(self):
        state = types.SimpleNamespace(key="qzone")
        self.assertEqual(
            runtime._safe_startup_error(state, RuntimeError("standalone QQ 空间插件仍在运行")),
            "RuntimeError: 独立 QQ 空间插件仍在运行")
        self.assertEqual(
            runtime._safe_startup_error(state, RuntimeError(
                "qzone_bridge resolved outside plugin directory: C:/plugins/astrbot_plugin_qzone/qzone_bridge/__init__.py")),
            "RuntimeError: qzone_bridge 从 astrbot_plugin_qzone 加载")
        self.assertEqual(runtime._safe_startup_error(state, RuntimeError("private detail")), "RuntimeError")

    async def test_initialize_failure_rolls_back_partial_resources(self):
        self.fail_initialize = True
        host = self.host()
        status = await host.start()
        self.assertEqual(status[0]["state"], "failed")
        self.assertEqual(status[0]["error"], "ValueError")
        self.assertEqual(self.terminated, 1)
        self.assertEqual(self.handlers, [])
        self.assertEqual(self.registry, [])
        self.assertEqual(self.tools.func_list, [])
        self.assertEqual(self.context.registered_web_apis, [])
        await host.close()
        self.assertEqual(self.terminated, 1)

    async def test_collision_does_not_replace_another_plugins_tool(self):
        old = types.SimpleNamespace(name="fake_tool", handler=None, handler_module_path="other.main", active=True)
        self.tools.func_list.append(old)
        host = self.host()
        self.assertEqual((await host.start())[0]["state"], "failed")
        self.assertEqual(self.tools.func_list, [old])
        await host.close()

    async def test_previous_disabled_tool_and_route_restored(self):
        old = types.SimpleNamespace(name="fake_tool", handler=None, handler_module_path="other.main", active=False)
        old_handler = lambda: None
        old_route = ("/fake", old_handler, ["GET"], "old")
        self.tools.func_list.append(old)
        self.context.registered_web_apis.append(old_route)
        host = self.host()
        self.assertEqual((await host.start())[0]["state"], "running")
        await host.close()
        self.assertEqual(self.tools.func_list, [old])
        self.assertEqual(self.context.registered_web_apis, [old_route])

    async def test_close_reports_terminate_failure_and_still_cleans_registry(self):
        self.fail_terminate = True
        host = self.host()
        await host.start()
        status = await host.close()
        self.assertEqual(status[0]["state"], "failed")
        self.assertIn("清理失败", status[0]["error"])
        self.assertEqual(self.handlers, [])
        self.assertEqual(self.tools.func_list, [])

    async def test_reload_does_not_duplicate_handlers(self):
        first = self.host()
        await first.start()
        await first.start()
        self.assertEqual(self.imports, 1)
        await first.close()
        await first.close()
        second = self.host()
        await second.start()
        self.assertEqual(self.imports, 2)
        self.assertEqual(len(self.handlers), 1)
        await second.close()

    async def test_reload_module_applies_saved_settings_and_rebinds_handlers(self):
        host = self.host()
        await host.start()
        self.config["chat"]["settings"]["example"] = 19

        status = await host.reload_module("chat")

        self.assertEqual(status[0]["state"], "running")
        self.assertEqual(self.imports, 2)
        self.assertEqual(self.terminated, 1)
        self.assertEqual(len(self.handlers), 1)
        result = []
        await self.handlers[0].handler(result)
        self.assertEqual(result, [19])
        await host.close()

    async def test_reload_module_evicts_untracked_stale_child_modules(self):
        host = self.host()
        await host.start()
        stale_name = "testzhiban.modules.astrbot_plugin_fake.stale"
        stale = types.ModuleType(stale_name)
        sys.modules[stale_name] = stale
        state = next(item for item in host._states.values() if item.key == "chat")
        self.assertNotIn(stale_name, state.imported)

        await host.reload_module("chat")

        self.assertIsNot(sys.modules.get(stale_name), stale)
        self.assertEqual(self.imports, 2)
        await host.close()

    async def test_reload_module_disables_and_reenables_cleanly(self):
        host = self.host()
        await host.start()
        self.config["chat"]["enabled"] = False
        status = await host.reload_module("chat")
        self.assertEqual(status[0]["state"], "disabled")
        self.assertEqual(self.handlers, [])
        self.assertEqual(self.terminated, 1)

        self.config["chat"]["enabled"] = True
        status = await host.reload_module("chat")
        self.assertEqual(status[0]["state"], "running")
        self.assertEqual(self.imports, 2)
        self.assertEqual(len(self.handlers), 1)
        await host.close()

    def test_config_save_preserves_parent_and_deepcopy_has_no_parent_cycle(self):
        self.config["other"] = {"enabled": False}
        schema = {"example": {"type": "int", "default": 3},
                  "nested": {"type": "object", "items": {"enabled": {"type": "bool", "default": True}}}}
        child = runtime.ModuleConfig(self.config, "chat", schema)
        self.assertEqual(child["example"], 7)
        self.assertTrue(child["nested"]["enabled"])
        child.save_config({"example": 9})
        self.assertEqual(self.config.saved, 1)
        self.assertFalse(self.config.snapshot["other"]["enabled"])
        self.assertEqual(self.config.snapshot["chat"]["settings"]["example"], 9)
        self.assertIs(type(self.config.snapshot["chat"]["settings"]), dict)


if __name__ == "__main__":
    unittest.main()


class ToolReloadTests(unittest.TestCase):
    def _context(self):
        manager = types.SimpleNamespace(func_list=[])
        parent = types.SimpleNamespace(
            provider_manager=types.SimpleNamespace(llm_tools=manager),
            add_llm_tools=lambda *tools: manager.func_list.extend(tools),
        )
        state = types.SimpleNamespace(key="memory", tools=[], previous_tools={}, instance=None)
        def own(state, tool):
            tool.zhiban_module_key = state.key
            tool.handler_module_path = "owner"
            state.tools.append(tool)
        context = object.__new__(runtime._ModuleContext)
        context._context = parent
        context._state = state
        context._host = types.SimpleNamespace(_own_tool=own)
        return context, manager, state

    def test_same_module_reregistration_replaces_stale_tool(self):
        context, manager, _ = self._context()
        tool = types.SimpleNamespace(name="recall_long_term_memory", handler=None, active=True)
        context.add_llm_tools(tool)
        context.add_llm_tools(tool)
        self.assertEqual([item.name for item in manager.func_list], ["recall_long_term_memory"])

    def test_cross_module_tool_conflict_is_still_rejected(self):
        context, manager, _ = self._context()
        manager.func_list.append(types.SimpleNamespace(
            name="recall_long_term_memory", handler=None, active=True, zhiban_module_key="other"
        ))
        with self.assertRaisesRegex(RuntimeError, "recall_long_term_memory"):
            context.add_llm_tools(types.SimpleNamespace(
                name="recall_long_term_memory", handler=None, active=True
            ))
