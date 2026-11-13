"""Smoke the adapter against the installed real AstrBot registry in a sandbox.

The child interpreter owns its own temporary AstrBot root. No providers,
platforms or existing plugin data are loaded, and no messages are sent.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class FrameworkRuntimeTests(unittest.TestCase):
    def test_real_registration_reload_and_command_tool_binding(self):
        workspace = Path(__file__).parents[1]
        child_source = '''
from astrbot.api.star import Star, register
from astrbot.api.event import filter
@register("fixture", "test", "sandbox", "1.0")
class Fixture(Star):
    def __init__(self, context, config):
        super().__init__(context)
        self.config = config
    @filter.command("fixture")
    async def command(self, event, value: str):
        event.append("command:" + value)
    @filter.on_llm_request(priority=543)
    async def on_request(self, event, request):
        event.append(self.config.get("value"))
    @filter.llm_tool(name="zhiban_fixture_tool")
    async def fixture_tool(self, event, text: str):
        """A sandbox tool.

        Args:
            text(string): sandbox text
        """
        return "tool:" + text
'''
        runner = r'''
import asyncio, logging, sys, site, importlib.util
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
# A dedicated test venv may reuse the existing framework through a .pth file.
# Process that site's pywin32 paths as well, without changing either environment.
astrbot_spec=importlib.util.find_spec("astrbot")
if astrbot_spec and astrbot_spec.origin:
    site.addsitedir(str(Path(astrbot_spec.origin).parent.parent))
from astrbot_plugin_zhiban.runtime import ModuleHost
from astrbot.core.star.star import star_map, star_registry, StarMetadata
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.provider.register import llm_tools
class Parent:
    __module__ = "sandbox_zhiban.main"
parent=Parent()
parent.context=SimpleNamespace(provider_manager=SimpleNamespace(llm_tools=llm_tools), registered_web_apis=[])
parent.logger=logging.getLogger("sandbox")
md=StarMetadata(name="astrbot_plugin_zhiban", module_path=Parent.__module__, star_cls=parent)
star_map[Parent.__module__]=md
star_registry.append(md)
async def run():
    baseline_handlers=len(star_handlers_registry)
    baseline_tools=len(llm_tools.func_list)
    for _ in range(2):
        host=ModuleHost(parent,{"fixture":{"enabled":True,"settings":{"value":7}}},
            [{"key":"fixture","label":"测试","package":"astrbot_plugin_fixture"}],Path(sys.argv[2])/"module_data")
        result=await host.start()
        assert result[0]["state"]=="running", result
        assert len(star_registry)==1, star_registry
        owned=[h for h in star_handlers_registry if h.handler_module_path==Parent.__module__]
        assert len(owned)==3, owned
        event=[]
        request=next(h for h in owned if h.handler_name=="on_request")
        assert request.extras_configs["priority"]==543
        await request.handler(event,None)
        command=next(h for h in owned if h.handler_name=="command")
        await command.handler(event,"x")
        assert event==[7,"command:x"], event
        tool=next(t for t in llm_tools.func_list if t.name=="zhiban_fixture_tool")
        assert tool.handler_module_path==Parent.__module__
        assert await tool.handler(None,"y")=="tool:y"
        await host.close()
        assert len(star_handlers_registry)==baseline_handlers
        assert len(llm_tools.func_list)==baseline_tools
        assert len(star_registry)==1
    print("FRAMEWORK_RUNTIME_OK")
asyncio.run(run())
'''
        with tempfile.TemporaryDirectory(prefix="zhiban-runtime-test-") as tmp:
            root = Path(tmp)
            fixture = root / "sandbox_zhiban/modules/astrbot_plugin_fixture"
            fixture.mkdir(parents=True)
            (fixture / "main.py").write_text(textwrap.dedent(child_source), encoding="utf-8")
            env = dict(os.environ, ASTRBOT_ROOT=tmp, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            result = subprocess.run(
                [sys.executable, "-c", runner, str(workspace), tmp],
                cwd=tmp, env=env, capture_output=True, text=True, encoding="utf-8", timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-4000:])
            self.assertIn("FRAMEWORK_RUNTIME_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
