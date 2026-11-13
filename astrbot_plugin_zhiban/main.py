"""知伴唯一插件入口。业务模块保留原处理器，统一管理生命周期。"""
from __future__ import annotations

import json

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools

from .catalog import MODULES, ordered_modules
from .scheduling import BudgetScheduler


class ZhibanPlugin(Star):
    def __init__(self, context: Context, config):
        super().__init__(context)
        self.config = config
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_zhiban")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        management = config.get("management", {})
        self.scheduler = BudgetScheduler(
            management.get("queue_limit", 20),
            management.get("session_queue_limit", 4),
            management.get("wait_seconds", 90),
        )
        self.host = None
        self.persona = None

    async def initialize(self):
        from astrbot.core.utils.astrbot_path import get_astrbot_config_path
        from .legacy_config import import_legacy_settings
        from .runtime import ModuleHost
        from .memory_control import MemoryControl
        imported = import_legacy_settings(self.config, get_astrbot_config_path())
        if imported:
            self.logger.info("知伴：已导入旧模块设置 %s", "、".join(imported))
        self.persona = MemoryControl(self.data_dir / "memory" / "persona.sqlite3")
        self.host = ModuleHost(self, self.config, MODULES, self.data_dir)
        try:
            await self.host.start()
        except BaseException:
            await self.host.close()
            await self.scheduler.close()
            raise

    @filter.on_waiting_llm_request(priority=1000000)
    async def admit(self, event: AstrMessageEvent):
        if not await self.scheduler.admit_pipeline(event):
            self.logger.info("知伴：请求因队列限制或停止状态未进入模型流程")

    @filter.on_llm_request(priority=-100000)
    async def persona_context(self, event, request):
        if not self.config.get("memory", {}).get("enabled", True) or self.persona is None:
            return
        from .memory_control import scope_for_event
        text = await self.persona.approved_text(scope_for_event(event))
        if text:
            request.system_prompt = (request.system_prompt or "") + "\n[管理员批准的知伴人格补充]\n" + text[:1500]

    @filter.command("知伴", alias={"知伴菜单"}, priority=1000001)
    async def menu(self, event: AstrMessageEvent, action: str = "菜单", value: str = ""):
        """知伴 菜单/状态/人格建议/批准 编号/拒绝 编号/回滚。"""
        if action in ("菜单", "帮助"):
            order = self.config.get("management", {}).get("menu_order", [])
            lines = ["知伴 · 功能菜单"]
            for i, item in enumerate(ordered_modules(order), 1):
                enabled = self.config.get(item["key"], {}).get("enabled", True)
                lines.append(f"{i}. {item['label']} · {'启用' if enabled else '关闭'}")
            lines.append("管理：/知伴 状态；/知伴 人格建议；/知伴 批准 编号；/知伴 拒绝 编号；/知伴 回滚")
            lines.append("各模块原有命令与工具保留，设置在 AstrBot → 插件 → 知伴。")
            yield event.plain_result("\n".join(lines))
            event.stop_event()
            return
        if not event.is_admin():
            yield event.plain_result("此操作仅管理员可用。")
            event.stop_event()
            return
        if action == "状态":
            report = {"调度": self.scheduler.status(), "模块": self.host.status() if self.host else {}}
            yield event.plain_result(json.dumps(report, ensure_ascii=False, indent=2))
        elif action in ("人格建议", "批准", "拒绝", "回滚"):
            if self.persona is None:
                yield event.plain_result("人格管理尚未就绪。")
            else:
                from .memory_control import scope_for_event
                scope = scope_for_event(event)
                actor = str(event.get_sender_id())
                try:
                    if action == "人格建议":
                        result = await self.persona.list_proposals(scope)
                    elif action == "批准":
                        result = await self.persona.approve(scope, int(value), actor, is_admin=True)
                    elif action == "拒绝":
                        result = await self.persona.reject(scope, int(value), actor, is_admin=True)
                    else:
                        result = await self.persona.rollback(scope, actor, is_admin=True)
                    yield event.plain_result(json.dumps(result, ensure_ascii=False, default=str)[:6000])
                except (ValueError, LookupError, PermissionError) as exc:
                    yield event.plain_result("操作未完成：" + str(exc))
        else:
            yield event.plain_result("未知操作，请发送 /知伴 菜单。")
        event.stop_event()

    async def terminate(self):
        await self.scheduler.close()
        if self.host is not None:
            await self.host.close()
        if self.persona is not None and hasattr(self.persona, "close"):
            result = self.persona.close()
            if hasattr(result, "__await__"):
                await result
