"""知伴唯一插件入口。业务模块保留原处理器，统一管理生命周期。"""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from quart import request

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.api.web import request as plugin_request

from .catalog import MODULES, ordered_modules
from .scheduling import BudgetScheduler
from .ui_assets import MODULE_UI_ROOTS, prepare_module_ui_html, resolve_module_ui_asset
from .module_api import dashboard_session_authorized, module_api_target
from .settings_service import (
    SettingsConflictError,
    SettingsValidationError,
    apply_module_patch,
    read_module_config,
)


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
        self._settings_lock = asyncio.Lock()
        self._config_schema = json.loads(
            (Path(__file__).parent / "_conf_schema.json").read_text(encoding="utf-8")
        )

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
        self._register_ui_routes()
        try:
            await self.host.start()
        except BaseException:
            await self.host.close()
            await self.scheduler.close()
            raise

    def _register_ui_routes(self):
        register = getattr(self.context, "register_web_api", None)
        if not callable(register):
            return
        register(
            "/astrbot_plugin_zhiban/ui/status",
            self._ui_status,
            ["GET"],
            "知伴应用的模块运行状态",
        )
        register(
            "/astrbot_plugin_zhiban/ui/config/<module>",
            self._ui_config,
            ["GET", "POST"],
            "读取或保存知伴模块配置",
        )
        register(
            "/astrbot_plugin_zhiban/ui/apply/<module>",
            self._ui_apply_module,
            ["POST"],
            "应用并重载知伴模块配置",
        )
        register(
            "/astrbot_plugin_zhiban/ui/module_api/<module>/<path:api_path>",
            self._ui_module_api,
            ["GET", "POST", "PUT", "PATCH", "DELETE"],
            "在 Dashboard 登录态下代理知伴内嵌模块 API",
        )
        register(
            "/astrbot_plugin_zhiban/ui/<module>/<path:asset_path>",
            self._serve_module_ui_asset,
            ["GET"],
            "知伴应用内置模块页面资源",
        )

    async def _ui_status(self):
        modules = self.host.status() if self.host else []
        menu_order = self.config.get("management", {}).get("menu_order", [])
        memory_instance = self.host.instances.get("memory") if self.host else None
        initializer = getattr(memory_instance, "initializer", None)
        memory_state = next((item for item in modules if item["key"] == "memory"), None)
        if memory_state and memory_state["state"] == "running" and initializer:
            if getattr(initializer, "is_failed", False):
                memory_state["state"] = "failed"
                memory_state["error"] = "LivingMemoryInitializationFailed"
            elif not getattr(initializer, "is_initialized", False):
                memory_state["state"] = "starting"
                memory_state["detail"] = "正在等待记忆组件与模型提供商初始化"
        return {
            "status": "ok",
            "data": {
                "modules": modules,
                "menu_order": [item["key"] for item in ordered_modules(menu_order)],
            },
        }

    @staticmethod
    def _dashboard_session_authorized() -> bool:
        """Use AstrBot's already-validated plugin request identity."""
        try:
            from astrbot.core.workspace import API_KEY_USERNAME_PREFIX
        except (ImportError, RuntimeError):
            return False
        return dashboard_session_authorized(plugin_request, API_KEY_USERNAME_PREFIX)

    def _module_schema(self, module: str) -> dict | None:
        if not any(item["key"] == module for item in MODULES):
            return None
        schema = self._config_schema.get(module)
        return schema if isinstance(schema, dict) else {"type": "object", "items": {}}

    def _module_config_payload(self, module: str) -> dict | None:
        schema = self._module_schema(module)
        if schema is None:
            return None
        spec = next(item for item in MODULES if item["key"] == module)
        section = self.config.get(module, {})
        if not isinstance(section, dict):
            section = {}
        snapshot = read_module_config(schema, section)
        state = next(
            (item for item in self.host.status() if item["key"] == module),
            {"key": module, "label": spec["label"], "state": "starting", "error": None},
        ) if self.host else {"key": module, "label": spec["label"], "state": "starting", "error": None}
        settings_schema = snapshot["schema"].get("items", {})
        provider_options = self._provider_options()
        return {
            "module": module,
            "label": spec["label"],
            "package": spec["package"],
            "enabled": snapshot["enabled"],
            "settings": snapshot["settings"],
            "schema": settings_schema,
            "secret_fields": snapshot["secret_fields"],
            "configured_secrets": snapshot["configured_secrets"],
            "providers": provider_options,
            "revision": snapshot["revision"],
            "state": state,
            "has_dedicated_page": module in MODULE_UI_ROOTS,
        }

    def _provider_options(self) -> dict:
        result = {"chat_completion": [], "embedding": [], "rerank": []}
        manager = getattr(self.context, "provider_manager", None)
        configurations = getattr(manager, "providers_config", [])
        try:
            from astrbot.core.provider.register import provider_cls_map
        except ImportError:
            provider_cls_map = {}
        seen = set()
        for config in configurations:
            if not isinstance(config, dict):
                continue
            provider_id = str(config.get("id") or "").strip()
            provider_type_name = str(config.get("type") or "").strip()
            if not provider_id:
                continue
            metadata = provider_cls_map.get(provider_type_name)
            provider_type = getattr(metadata, "provider_type", None)
            provider_kind = getattr(provider_type, "value", "chat_completion")
            if provider_kind not in result:
                continue
            identity = (provider_kind, provider_id)
            if identity in seen:
                continue
            seen.add(identity)
            label = str(
                config.get("name")
                or getattr(metadata, "provider_display_name", None)
                or config.get("model")
                or provider_id
            )
            result[provider_kind].append({"id": provider_id, "label": label})
        return result

    async def _ui_config(self, module: str):
        if not self._dashboard_session_authorized():
            return JSONResponse({"status": "error", "message": "未授权"}, status_code=401)
        schema = self._module_schema(module)
        if schema is None:
            return JSONResponse({"status": "error", "message": "模块不存在"}, status_code=404)
        if request.method.upper() == "GET":
            return JSONResponse({"status": "ok", "data": self._module_config_payload(module)})

        body = await request.get_json(silent=True)
        if not isinstance(body, dict):
            return JSONResponse({"status": "error", "message": "请求格式无效"}, status_code=400)
        changes = body.get("changes", {})
        clear_secrets = body.get("clear_secrets", [])
        if not isinstance(changes, dict) or not isinstance(clear_secrets, list):
            return JSONResponse({"status": "error", "message": "配置更改格式无效"}, status_code=400)

        async with self._settings_lock:
            section = self.config.get(module)
            if not isinstance(section, dict):
                section = {}
                self.config[module] = section
            revision = body.get("revision")
            if not isinstance(revision, str):
                return JSONResponse({"status": "error", "message": "缺少配置版本号，请重新载入"}, status_code=400)
            try:
                updated = apply_module_patch(
                    schema,
                    section,
                    expected_revision=revision,
                    changes=changes,
                    enabled=body.get("enabled"),
                    clear_secrets=clear_secrets,
                )
            except SettingsConflictError as exc:
                return JSONResponse({"status": "conflict", "message": str(exc)}, status_code=409)
            except SettingsValidationError as exc:
                return JSONResponse({"status": "error", "message": str(exc)}, status_code=422)

            settings_object = section.get("settings")
            original_settings = copy.deepcopy(dict(settings_object)) if isinstance(settings_object, dict) else None
            had_settings = "settings" in section
            original_enabled = section.get("enabled", True)
            try:
                if isinstance(settings_object, dict):
                    settings_object.clear()
                    settings_object.update(updated.get("settings", {}))
                elif "settings" in updated:
                    section["settings"] = updated["settings"]
                section["enabled"] = updated.get("enabled", original_enabled)
                save_async = getattr(self.config, "save_config_async", None)
                if callable(save_async):
                    saved = await save_async()
                    if saved is False:
                        raise RuntimeError("配置保存被较新的设置覆盖")
                else:
                    save = getattr(self.config, "save_config", None)
                    if not callable(save):
                        raise RuntimeError("配置存储不支持保存")
                    save()
            except Exception:
                if isinstance(settings_object, dict) and original_settings is not None:
                    settings_object.clear()
                    settings_object.update(original_settings)
                    section["settings"] = settings_object
                elif had_settings:
                    section["settings"] = settings_object
                else:
                    section.pop("settings", None)
                section["enabled"] = original_enabled
                self.logger.exception("知伴模块配置保存失败：%s", module)
                return JSONResponse({"status": "error", "message": "配置保存失败，请检查 AstrBot 日志"}, status_code=500)

        payload = self._module_config_payload(module)
        payload["requires_reload"] = True
        return JSONResponse({"status": "ok", "message": "配置已保存，请应用后生效", "data": payload})

    async def _ui_apply_module(self, module: str):
        if not self._dashboard_session_authorized():
            return JSONResponse({"status": "error", "message": "未授权"}, status_code=401)
        if self._module_schema(module) is None:
            return JSONResponse({"status": "error", "message": "模块不存在"}, status_code=404)
        if self.host is None:
            return JSONResponse({"status": "error", "message": "模块宿主尚未就绪"}, status_code=503)
        try:
            statuses = await self.host.reload_module(module)
        except KeyError:
            return JSONResponse({"status": "error", "message": "模块不存在"}, status_code=404)
        except Exception:
            self.logger.exception("知伴模块应用失败：%s", module)
            return JSONResponse({"status": "error", "message": "模块应用失败，请检查 AstrBot 日志"}, status_code=500)
        state = next((item for item in statuses if item["key"] == module), None)
        if state is None:
            return JSONResponse({"status": "error", "message": "未找到模块状态"}, status_code=500)
        if state["state"] in {"failed", "blocked"}:
            return JSONResponse({"status": "error", "message": state.get("error") or "模块启动失败", "data": state}, status_code=409)
        return JSONResponse({"status": "ok", "message": "配置已应用", "data": state})

    async def _ui_module_api(self, module: str, api_path: str):
        """Dispatch to a registered child API without exposing its auth token."""
        if not self._dashboard_session_authorized():
            return JSONResponse({"status": "error", "message": "未授权"}, status_code=401)
        try:
            username = plugin_request.username
            raw_request = getattr(plugin_request, "_request", None)
        except RuntimeError:
            username = None
            raw_request = None
        target = module_api_target(module, api_path)
        if target is None or raw_request is None:
            return JSONResponse({"status": "error", "message": "模块接口不存在"}, status_code=404)
        try:
            from astrbot.dashboard.api.plugins import _call_plugin_extension

            return await _call_plugin_extension(
                target,
                raw_request,
                username,
            )
        except Exception:
            self.logger.exception("知伴模块接口转发失败：%s/%s", module, api_path)
            return JSONResponse({"status": "error", "message": "模块接口调用失败"}, status_code=500)

    async def _serve_module_ui_asset(self, module: str, asset_path: str):
        if module not in MODULE_UI_ROOTS:
            return JSONResponse({"status": "error", "message": "模块页面不存在"}, status_code=404)
        path = resolve_module_ui_asset(Path(__file__).parent, module, asset_path)
        if path is None:
            return JSONResponse({"status": "error", "message": "页面资源不存在"}, status_code=404)
        if path.name.lower() == "index.html":
            html = path.read_text(encoding="utf-8")
            plugin_name = MODULE_UI_ROOTS[module][0]
            depth = 2 + len(Path(asset_path).parent.parts)
            bridge_src = "../" * depth + "module_bridge.js"
            return HTMLResponse(
                prepare_module_ui_html(html, plugin_name, module_bridge_src=bridge_src)
            )
        return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})

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
