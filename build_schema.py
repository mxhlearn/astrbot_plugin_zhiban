"""从整合模块生成按常用程度排列的中文统一配置。"""
from pathlib import Path
import json
import importlib.util

ROOT = Path(__file__).resolve().parent / "astrbot_plugin_zhiban"
spec = importlib.util.spec_from_file_location("catalog", ROOT / "catalog.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def build():
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
    schema["management"] = {
        "type": "object", "description": "调度与管理", "items": {
            "menu_order": {"type": "list", "description": "菜单排列顺序", "default": [s["key"] for s in catalog.MODULES],
                           "hint": "默认按预期使用频率排列，不是实测使用统计。"},
            "queue_limit": {"type": "int", "description": "聊天等待总数", "default": 20},
            "session_queue_limit": {"type": "int", "description": "单会话等待数", "default": 4},
            "wait_seconds": {"type": "int", "description": "聊天等待上限（秒）", "default": 90},
        },
    }
    (ROOT / "_conf_schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return schema


if __name__ == "__main__":
    result = build()
    print("生成中文配置分组：", "、".join(v["description"] for v in result.values()))
