from __future__ import annotations

import json
from pathlib import Path

import pytest

from astrbot_plugin_anysearch.main import AnySearchPlugin


MODULE_ROOT = Path(__file__).resolve().parents[1]


class ToolManager:
    def __init__(self):
        self.removed = []

    def remove_func(self, name):
        self.removed.append(name)


class ProviderManager:
    def __init__(self):
        self.llm_tools = ToolManager()


class FakeContext:
    def __init__(self):
        self.provider_manager = ProviderManager()
        self.registered = []

    def add_llm_tools(self, *tools):
        self.registered.extend(tools)


def test_config_marks_key_secret_and_disables_tools_by_default():
    config = json.loads((MODULE_ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    assert config["api_key"]["secret"] is True
    assert config["enable_llm_tools"]["default"] is False
    assert config["max_concurrency"]["default"] == 2


def test_plugin_defaults_to_no_llm_tools_and_redacted_status():
    context = FakeContext()
    plugin = AnySearchPlugin(context, {"api_key": "do-not-print"})
    assert plugin.tools == []
    assert context.registered == []
    assert plugin.client._session is None
    status = plugin._status_text()
    assert "未配置" not in status
    assert "do-not-print" not in status
    assert "LLM 工具 默认关闭" in status


def test_plugin_registers_tools_only_when_explicitly_enabled():
    context = FakeContext()
    plugin = AnySearchPlugin(context, {"api_key": "key", "enable_llm_tools": True})
    assert [tool.name for tool in plugin.tools] == [
        "anysearch_search",
        "anysearch_extract",
        "anysearch_batch_search",
    ]
    assert context.registered == plugin.tools


@pytest.mark.asyncio
async def test_terminate_removes_tools_and_closes_client():
    context = FakeContext()
    plugin = AnySearchPlugin(context, {"api_key": "key", "enable_llm_tools": True})
    await plugin.terminate()
    assert set(context.provider_manager.llm_tools.removed) == {
        "anysearch_search",
        "anysearch_extract",
        "anysearch_batch_search",
    }
    assert plugin.client._session is None


def test_upstream_source_is_locked_and_licensed():
    upstream = (MODULE_ROOT / "UPSTREAM.md").read_text(encoding="utf-8")
    license_text = (MODULE_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "983a7acb2f6940ab441a521be684085e0913738e" in upstream
    assert "MIT" in license_text
    assert "Copyright (c) 2026 AgIzT" in license_text

def test_missing_key_is_business_not_ready_without_network():
    context = FakeContext()
    plugin = AnySearchPlugin(context, {})
    readiness = plugin.module_readiness()
    assert readiness["state"] == "not_ready"
    assert "API Key" in readiness["detail"]
    assert plugin.client._session is None


def test_configured_key_is_business_ready_without_probe():
    context = FakeContext()
    plugin = AnySearchPlugin(context, {"api_key": "configured"})
    readiness = plugin.module_readiness()
    assert readiness["state"] == "ready"
    assert plugin.client._session is None
