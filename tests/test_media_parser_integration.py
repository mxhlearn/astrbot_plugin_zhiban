"""Integration contracts for the verified media parser snapshot."""

import json
from pathlib import Path

from astrbot_plugin_zhiban.catalog import MODULES
from astrbot_plugin_zhiban.modules.astrbot_plugin_media_parser.main import VideoParserPlugin


ROOT = Path(__file__).parents[1] / "astrbot_plugin_zhiban"


def test_catalog_exposes_parser_as_chat_process_module():
    spec = next(item for item in MODULES if item["key"] == "parser")
    assert spec["package"] == "astrbot_plugin_media_parser"
    assert spec["label"] == "万能解析"
    assert spec["group"] == "聊天系统"


def test_parser_readiness_is_honest_about_optional_enhancements():
    readiness = VideoParserPlugin.module_readiness(None)
    assert readiness["state"] == "ready"
    assert readiness["label"] == "业务可用"
    assert "基础链接解析" in readiness["detail"]


def test_generated_management_schema_contains_parser_settings():
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8-sig"))
    parser = schema["parser"]
    assert parser["description"] == "万能解析"
    assert parser["items"]["settings"]["items"]
