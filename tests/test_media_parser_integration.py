"""Integration contracts for the verified media parser snapshot."""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from astrbot_plugin_zhiban.catalog import MODULES
from astrbot_plugin_zhiban.modules.astrbot_plugin_media_parser.media_budget import host_media_context


ROOT = Path(__file__).parents[1] / "astrbot_plugin_zhiban"


def test_catalog_exposes_parser_as_chat_process_module():
    spec = next(item for item in MODULES if item["key"] == "parser")
    assert spec["package"] == "astrbot_plugin_media_parser"
    assert spec["label"] == "万能解析"
    assert spec["group"] == "聊天系统"


def test_generated_management_schema_contains_parser_settings():
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8-sig"))
    parser = schema["parser"]
    assert parser["description"] == "万能解析"
    assert parser["items"]["settings"]["items"]


class _Budget:
    def __init__(self, limit=1):
        self.active = 0
        self.peak = 0
        self.limit = limit

    @asynccontextmanager
    async def media(self):
        while self.active >= self.limit:
            await asyncio.sleep(0)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            yield
        finally:
            self.active -= 1


class _Context:
    def __init__(self, budget):
        self.zhiban_parent = type("Parent", (), {"scheduler": budget})() if budget else None


def _plugin_with_budget(budget):
    return _Context(budget)


@pytest.mark.asyncio
async def test_parser_uses_host_media_budget_when_available():
    budget = _Budget(limit=1)
    plugin = _plugin_with_budget(budget)

    async def work():
        async with host_media_context(plugin):
            await asyncio.sleep(0)

    await asyncio.gather(*(work() for _ in range(5)))
    assert budget.peak == 1
    assert budget.active == 0


@pytest.mark.asyncio
async def test_parser_budget_context_is_noop_without_host():
    plugin = _plugin_with_budget(None)
    async with host_media_context(plugin):
        assert True
