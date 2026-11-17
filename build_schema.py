"""从整合模块生成按常用程度排列的中文统一配置。"""
from pathlib import Path
import json
import importlib.util

ROOT = Path(__file__).resolve().parent / "astrbot_plugin_zhiban"
spec = importlib.util.spec_from_file_location("catalog", ROOT / "catalog.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def build():
    output_path = ROOT / "_conf_schema.json"
    existing = {}
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    schema = {}
    for item in catalog.MODULES:
        path = ROOT / "modules" / item["package"] / "_conf_schema.json"
        settings = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        # 默认不启动额外管理服务、遥测或更新轮询；业务主动问候保留。
        if item["key"] == "proactive":
            for group in ("web_admin", "telemetry_config", "notification_settings"):
                field = settings.get(group, {}).get("items", {}).get("enabled")
                if field is not None:
                    field["default"] = False
            settings.get("friend_settings", {}).get("items", {}).get("enable", {})["default"] = True
            settings.get("group_settings", {}).get("items", {}).get("enable", {})["default"] = False
        schema[item["key"]] = {
            "type": "object", "description": item["label"],
            "hint": "保留服务器现用实现；更改启用状态后重载知伴。",
            "items": {
                "enabled": {"type": "bool", "description": "启用" + item["label"], "default": True},
                "settings": {"type": "object", "description": item["label"] + "设置", "items": settings},
            },
        }
    previous_management = existing.get("management", {}) if isinstance(existing, dict) else {}
    management = previous_management if isinstance(previous_management, dict) else {}
    management.setdefault("type", "object")
    management.setdefault("description", "调度与管理")
    management_items = management.get("items")
    if not isinstance(management_items, dict):
        management_items = {}
        management["items"] = management_items
    # Keep the five global resource controls stable even when a previous schema
    # was produced by an older generator that only knew the chat queue fields.
    defaults = {
        "chat_concurrency": {
            "type": "int", "description": "资源调度 · 聊天并发上限（个）",
            "default": 1, "slider": {"min": 1, "max": 4},
            "hint": "默认 1；提高会增加同时生成回复的内存占用。",
        },
        "media_concurrency": {
            "type": "int", "description": "资源调度 · 媒体处理并发上限（个）",
            "default": 1, "slider": {"min": 1, "max": 2},
        },
        "maintenance_concurrency": {
            "type": "int", "description": "资源调度 · 后台维护并发上限（个）",
            "default": 1, "slider": {"min": 1, "max": 2},
        },
        "media_queue_limit": {
            "type": "int", "description": "高级保护 · 媒体排队上限（条）",
            "default": 8, "slider": {"min": 1, "max": 32},
        },
        "maintenance_queue_limit": {
            "type": "int", "description": "高级保护 · 后台维护排队上限（条）",
            "default": 8, "slider": {"min": 1, "max": 32},
        },
        "queue_limit": {
            "type": "int", "description": "高级保护 · 全局排队消息上限（条）",
            "default": 20, "slider": {"min": 1, "max": 100},
        },
        "session_queue_limit": {
            "type": "int", "description": "高级保护 · 单会话排队消息上限（条）",
            "default": 4, "slider": {"min": 1, "max": 10},
        },
        "wait_seconds": {
            "type": "int", "description": "高级保护 · 排队等待上限（秒）",
            "default": 90, "slider": {"min": 1, "max": 600},
        },
    }
    for key, value in defaults.items():
        management_items.setdefault(key, value)
    management_items["menu_order"] = {
        "type": "list",
        "description": "菜单排列顺序",
        "default": [s["key"] for s in catalog.MODULES],
        "hint": "默认按预期使用频率排列，不是实测使用统计。",
    }
    schema["management"] = management
    output_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return schema


if __name__ == "__main__":
    result = build()
    print("生成中文配置分组：", "、".join(v["description"] for v in result.values()))
