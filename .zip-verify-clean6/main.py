"""知伴唯一插件入口。业务模块保留原处理器，统一管理生命周期。"""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
import time
from pathlib import Path

from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from quart import request

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.api.web import request as plugin_request

from .catalog import MODULES, ordered_modules
from .reply_debounce import ReplyDebounceCoordinator
from .scheduling import BudgetScheduler
from .ui_assets import MODULE_UI_ROOTS, resolve_module_ui_asset
from .module_api import module_api_target
from .settings_service import (
    SettingsConflictError,
    SettingsValidationError,
    apply_module_patch,
    config_revision,
    read_module_config,
)
from .ui_route import RouteStore, sanitize_ui_route
from .usage_service import UsageService, global_provider_summary


class ZhibanPlugin(Star):
    def __init__(self, context: Context, config):
        super().__init__(context)
        self.config = config
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_zhiban")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.ui_routes = RouteStore(self.data_dir / "ui_route.json")
        timezone_name = config.get("timezone") if isinstance(config, dict) else None
        self.usage = UsageService(self.data_dir / "usage.sqlite3", timezone_name)
        self.usage.ensure_started()
        management = config.get("management", {})
        self.scheduler = BudgetScheduler(
            management.get("queue_limit", 20),
            management.get("session_queue_limit", 4),
            management.get("wait_seconds", 90),
            chat_concurrency=management.get("chat_concurrency", 1),
            media_concurrency=management.get("media_concurrency", 1),
            maintenance_concurrency=management.get("maintenance_concurrency", 1),
            media_queue_limit=management.get("media_queue_limit", 8),
            maintenance_queue_limit=management.get("maintenance_queue_limit", 8),
        )
        self.reply_debounce = ReplyDebounceCoordinator(
            context,
            config=self._reply_debounce_config(),
            usage_recorder=self.usage.record_event,
            style_provider=self._reply_debounce_style,
        )
        self.host = None
        self.persona = None
        self._settings_lock = asyncio.Lock()
        self._readiness_cache: dict[str, tuple[float, dict]] = {}
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
            "/astrbot_plugin_zhiban/ui/usage",
            self._ui_usage,
            ["GET"],
            "知伴可识别模型调用与 AstrBot 全局用量摘要",
        )
        register(
            "/astrbot_plugin_zhiban/ui/route",
            self._ui_route,
            ["GET", "POST"],
            "读取或保存知伴工作台的路由位置",
        )
        register(
            "/astrbot_plugin_zhiban/ui/global",
            self._ui_global_config,
            ["GET", "POST"],
            "读取或保存知伴跨模块调度与全局资源设置",
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

    async def _ui_route(self):
        username = self._dashboard_username()
        if not username:
            return JSONResponse({"status": "error", "message": "未授权"}, status_code=401)
        if request.method.upper() == "GET":
            return JSONResponse({"status": "ok", "data": self.ui_routes.get(username)})
        body = await request.get_json(silent=True)
        route = sanitize_ui_route(body)
        if route is None:
            return JSONResponse({"status": "error", "message": "路由格式无效"}, status_code=400)
        try:
            saved = self.ui_routes.put(username, route)
        except OSError:
            return JSONResponse({"status": "error", "message": "路由保存失败"}, status_code=503)
        if saved is None:
            return JSONResponse({"status": "error", "message": "路由格式无效"}, status_code=400)
        return JSONResponse({"status": "ok", "data": saved})

    def _ui_usage(self):
        summary = self.usage.summary()
        # StarTools stores plugin data under AstrBot/data/plugin_data; the
        # global AstrBot SQLite database is one level above that directory.
        global_db = Path(self.data_dir).parent.parent / "data_v4.db"
        global_summary = global_provider_summary(global_db, self.usage.timezone)
        payload = {
            "scope": summary.get("scope", "zhiban"),
            "timezone": summary.get("timezone"),
            "started_at": summary.get("started_at"),
            "started_day": summary.get("started_day"),
            "days": summary.get("days"),
            "zhiban": summary,
            "astrbot_global": global_summary,
        }
        return JSONResponse(payload)

    def _global_config_payload(self) -> dict:
        management_schema = self._config_schema.get("management", {})
        if not isinstance(management_schema, dict):
            management_schema = {"type": "object", "items": {}}
        section = self.config.get("management", {})
        if not isinstance(section, dict):
            section = {}
        snapshot = read_module_config(
            {"type": "object", "items": {"settings": management_schema}},
            {"enabled": True, "settings": section},
        )
        status_map = {item["key"]: item for item in self.host.status()} if self.host else {}
        module_rows = []
        for spec in MODULES:
            configured = self.config.get(spec["key"], {})
            if not isinstance(configured, dict):
                configured = {}
            state = status_map.get(spec["key"], {})
            module_rows.append({
                "key": spec["key"],
                "label": spec["label"],
                "group": spec.get("group", ""),
                "enabled": bool(configured.get("enabled", True)),
                "revision": config_revision(configured),
                "state": state.get("state", "starting"),
                "running": bool(state.get("running", False)),
                "readiness": state.get("readiness"),
            })
        return {
            "settings": snapshot["settings"],
            "schema": management_schema,
            "revision": snapshot["revision"],
            "scheduler": self.scheduler.status(),
            **({"reply_debounce": self.reply_debounce.status()} if getattr(self, "reply_debounce", None) is not None else {}),
            "modules": module_rows,
        }

    async def _ui_global_config(self):
        if not self._dashboard_session_authorized():
            return JSONResponse({"status": "error", "message": "未授权"}, status_code=401)
        if request.method.upper() == "GET":
            payload = self._global_config_payload()
            return JSONResponse({"status": "ok", "data": payload})

        body = await request.get_json(silent=True)
        if not isinstance(body, dict):
            return JSONResponse({"status": "error", "message": "请求格式无效"}, status_code=400)
        revision = body.get("revision")
        changes = body.get("changes", {})
        module_updates = body.get("modules", {})
        apply_changes = bool(body.get("apply"))
        if not isinstance(revision, str) or not isinstance(changes, dict) or not isinstance(module_updates, dict):
            return JSONResponse({"status": "error", "message": "全局配置格式无效"}, status_code=400)

        management_schema = self._config_schema.get("management", {})
        wrapper_schema = {"type": "object", "items": {"settings": management_schema}}
        current_management = self.config.get("management", {})
        if not isinstance(current_management, dict):
            current_management = {}
        current_wrapper = {"enabled": True, "settings": current_management}
        if changes:
            try:
                updated_wrapper = apply_module_patch(
                    wrapper_schema,
                    current_wrapper,
                    expected_revision=revision,
                    changes=changes,
                )
            except SettingsConflictError as exc:
                return JSONResponse({"status": "conflict", "message": str(exc)}, status_code=409)
            except SettingsValidationError as exc:
                return JSONResponse({"status": "error", "message": str(exc)}, status_code=422)
        else:
            if revision != config_revision(current_wrapper):
                return JSONResponse(
                    {"status": "conflict", "message": "全局配置已被其他操作更新，请重新载入后再保存"},
                    status_code=409,
                )
            updated_wrapper = current_wrapper

        pending = {}
        for key, update in module_updates.items():
            spec = next((item for item in MODULES if item["key"] == key), None)
            if spec is None or not isinstance(update, dict):
                return JSONResponse({"status": "error", "message": f"模块更新无效：{key}"}, status_code=422)
            enabled = update.get("enabled")
            module_revision = update.get("revision")
            if not isinstance(enabled, bool) or not isinstance(module_revision, str):
                return JSONResponse({"status": "error", "message": f"模块更新缺少版本号：{key}"}, status_code=422)
            section = self.config.get(key, {})
            if not isinstance(section, dict):
                section = {}
            try:
                pending[key] = apply_module_patch(
                    self._module_schema(key) or {},
                    section,
                    expected_revision=module_revision,
                    changes={},
                    enabled=enabled,
                )
            except SettingsConflictError as exc:
                return JSONResponse({"status": "conflict", "message": f"{spec['label']}：{exc}"}, status_code=409)
            except SettingsValidationError as exc:
                return JSONResponse({"status": "error", "message": str(exc)}, status_code=422)

        previous_management = copy.deepcopy(current_management)
        previous_modules = {key: copy.deepcopy(self.config.get(key, {})) for key in pending}
        try:
            self.config["management"] = updated_wrapper.get("settings", {})
            for key, updated in pending.items():
                self.config[key] = updated
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
            self.config["management"] = previous_management
            for key, previous in previous_modules.items():
                self.config[key] = previous
            self.logger.exception("知伴全局配置保存失败")
            return JSONResponse({"status": "error", "message": "全局配置保存失败，请检查 AstrBot 日志"}, status_code=500)

        self._apply_runtime_controls()

        failures = []
        applied = []
        if apply_changes and self.host is not None:
            for key in pending:
                try:
                    statuses = await self.host.reload_module(key)
                    self._readiness_cache.pop(key, None)
                    state = next((item for item in statuses if item["key"] == key), None)
                    if state and state.get("state") in {"failed", "blocked"}:
                        failures.append({"key": key, "message": state.get("error") or "模块启动失败"})
                    else:
                        applied.append(key)
                except Exception as exc:
                    failures.append({"key": key, "message": str(exc) or type(exc).__name__})

        payload = self._global_config_payload()
        return JSONResponse({
            "status": "partial" if failures else "ok",
            "message": "部分模块应用失败" if failures else "全局设置已保存并应用",
            "data": {**payload, "applied_modules": applied, "failures": failures},
        }, status_code=207 if failures else 200)

    async def _memory_provider_readiness(self) -> dict | None:
        """Report missing or unavailable LLM/embedding providers honestly."""
        manager = getattr(self.context, "provider_manager", None)
        if manager is None:
            return None
        try:
            from astrbot.core.provider.entities import ProviderType
        except ImportError:
            return None
        counts: dict[object, int] = {}
        for instance in getattr(manager, "inst_map", {}).values():
            try:
                provider_type = instance.meta().provider_type
            except Exception:
                continue
            counts[provider_type] = counts.get(provider_type, 0) + 1
        try:
            chat = await manager.get_using_provider_async(ProviderType.CHAT_COMPLETION)
            embedding = await manager.get_using_provider_async(ProviderType.EMBEDDING)
        except Exception:
            return None
        if chat is None:
            if counts.get(ProviderType.CHAT_COMPLETION, 0) == 0:
                return {
                    "state": "not_ready",
                    "label": "未配置",
                    "detail": "未配置可用的语言模型 Provider（LLM Provider）；记忆组件会继续重试，请先在 AstrBot 中配置语言模型。",
                }
            return {
                "state": "not_ready",
                "label": "暂不可用",
                "detail": "语言模型 Provider 已配置但当前不可用；记忆组件会继续重试。",
            }
        if embedding is None:
            if counts.get(ProviderType.EMBEDDING, 0) == 0:
                return {
                    "state": "not_ready",
                    "label": "未配置",
                    "detail": "未配置可用的嵌入模型 Provider；记忆检索无法就绪。",
                }
            return {
                "state": "not_ready",
                "label": "暂不可用",
                "detail": "嵌入模型 Provider 已配置但当前不可用；记忆组件会继续重试。",
            }
        return None

    async def _module_readiness(self, module: dict) -> dict:
        """Return lifecycle-independent business readiness with honest unknowns."""
        key = module.get("key")
        state = module.get("state")
        if not module.get("enabled", True):
            return {"state": "disabled", "label": "已关闭", "detail": "模块开关当前关闭"}
        if state in {"failed", "blocked"}:
            return {
                "state": "failed",
                "label": "不可用",
                "detail": module.get("error") or "模块启动失败",
            }
        if state in {None, "starting", "stopping", "stopped"}:
            return {"state": "starting", "label": "初始化中", "detail": "模块尚未完成启动"}
        if state != "running" or self.host is None:
            return {"state": "unknown", "label": "未检测", "detail": "没有可用的运行实例"}

        instance = self.host.instances.get(key)
        readiness_checker = getattr(instance, "module_readiness", None)
        if callable(readiness_checker):
            try:
                readiness = readiness_checker()
                if inspect.isawaitable(readiness):
                    readiness = await readiness
                if isinstance(readiness, dict) and readiness.get("state"):
                    return readiness
            except Exception:
                pass
        if key == "memory":
            initializer = getattr(instance, "initializer", None)
            if getattr(initializer, "is_failed", False):
                return {
                    "state": "failed",
                    "label": "不可用",
                    "detail": getattr(initializer, "error_message", None)
                    or "记忆组件初始化失败，请检查模型提供商与嵌入配置",
                }
            if not getattr(initializer, "is_initialized", False):
                missing = []
                # Only an explicit None means the provider is absent. A test
                # double or older initializer without these attributes is an
                # unknown state, not proof that the deployment is unconfigured.
                if getattr(initializer, "llm_provider", "unknown") is None:
                    missing.append("语言模型 Provider（LLM Provider）")
                if getattr(initializer, "embedding_provider", "unknown") is None:
                    missing.append("嵌入模型 Provider")
                if missing:
                    return {
                        "state": "not_ready",
                        "label": "未就绪",
                        "detail": f"未就绪 Provider：{'、'.join(missing)}；请先在 AstrBot 中完成配置，记忆组件会继续重试。",
                    }
                checker = getattr(self, "_memory_provider_readiness", None)
                provider_issue = await checker() if callable(checker) else None
                if provider_issue is not None:
                    return provider_issue
                return {
                    "state": "starting",
                    "label": "初始化中",
                    "detail": "记忆组件仍在等待嵌入索引或内部初始化完成",
                }

        if key == "qzone":
            cache_store = getattr(self, "_readiness_cache", {})
            self._readiness_cache = cache_store
            cached = cache_store.get("qzone")
            if cached and time.monotonic() - cached[0] < 5.0:
                return dict(cached[1])
            def remember(result: dict) -> dict:
                cache_store["qzone"] = (time.monotonic(), dict(result))
                return result
            controller = getattr(instance, "controller", None)
            get_status = getattr(controller, "get_status", None)
            if not callable(get_status):
                return remember({"state": "unknown", "label": "未检测", "detail": "空间连接状态接口不可用"})
            try:
                status = await asyncio.wait_for(
                    get_status(probe_daemon=False),
                    timeout=1.5,
                )
            except Exception as exc:
                return remember({
                    "state": "unknown",
                    "label": "检测失败",
                    "detail": f"未取得空间连接状态：{type(exc).__name__}",
                })
            try:
                cookie_count = int(status.get("cookie_count") or 0) if isinstance(status, dict) else 0
            except (TypeError, ValueError):
                cookie_count = 0
            needs_rebind = bool(status.get("needs_rebind")) if isinstance(status, dict) else True
            if not cookie_count or needs_rebind:
                return remember({
                    "state": "not_ready",
                    "label": "待配置",
                    "detail": "没有可用空间 Cookie，动态功能尚未就绪",
                })
            daemon_state = str(status.get("daemon_state") or "")
            if daemon_state and daemon_state not in {"ready", "running"}:
                result = {
                    "state": "not_ready",
                    "label": "待连接",
                    "detail": f"空间守护进程状态：{daemon_state}",
                }
                return remember(result)
            return remember({"state": "ready", "label": "业务可用", "detail": "模块已运行并完成启动检查"})

        return {"state": "ready", "label": "业务可用", "detail": "模块已运行并完成启动检查"}

    async def _ui_status(self):
        modules = self.host.status() if self.host else []
        menu_order = self.config.get("management", {}).get("menu_order", [])
        for module in modules:
            module["readiness"] = await self._module_readiness(module)
        return {
            "status": "ok",
            "data": {
                "modules": modules,
                "menu_order": [item["key"] for item in ordered_modules(menu_order)],
                "scheduler": self.scheduler.status(),
                **({"reply_debounce": self.reply_debounce.status()} if getattr(self, "reply_debounce", None) is not None else {}),
            },
        }

    @staticmethod
    def _dashboard_username() -> str | None:
        """Use AstrBot's already-validated plugin request identity."""
        try:
            from astrbot.core.workspace import API_KEY_USERNAME_PREFIX
            username = plugin_request.username
        except (ImportError, RuntimeError, AttributeError):
            return None
        if not isinstance(username, str):
            return None
        username = username.strip()
        if not username or username.startswith(API_KEY_USERNAME_PREFIX):
            return None
        return username

    @staticmethod
    def _dashboard_session_authorized() -> bool:
        return bool(ZhibanPlugin._dashboard_username())

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

        if module == "heart":
            self._apply_runtime_controls()
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
            self._readiness_cache.pop(module, None)
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
        # UI HTML is materialized by build_views, which already injects the
        # first-paint theme, module adapter and SDK before business scripts.
        # Serve those files verbatim so both direct and signed asset routes use
        # the same controlled artifact, without re-injecting through handlers.
        if module not in MODULE_UI_ROOTS:
            return JSONResponse({"status": "error", "message": "模块页面不存在"}, status_code=404)
        path = resolve_module_ui_asset(Path(__file__).parent, module, asset_path)
        if path is None:
            return JSONResponse({"status": "error", "message": "页面资源不存在"}, status_code=404)
        headers = {"X-Content-Type-Options": "nosniff"}
        if path.suffix.lower() == ".html":
            headers["Cache-Control"] = "no-store, max-age=0"
        return FileResponse(path, headers=headers)

    def _reply_debounce_config(self) -> dict:
        """Read private-chat reply debounce from 聊天互动; never from global settings."""
        heart = self.config.get("heart", {}) if isinstance(self.config, dict) else {}
        settings = heart.get("settings", {}) if isinstance(heart, dict) else {}
        raw = settings.get("reply_debounce", {}) if isinstance(settings, dict) else {}
        if not isinstance(raw, dict):
            raw = {}
        return {
            "enabled": self._safe_bool(raw.get("enabled"), True),
            "thinking": self._safe_bool(
                raw.get("enable_thinking", raw.get("thinking")), True
            ),
            "think_provider_id": str(raw.get("think_provider_id") or "").strip(),
            "think_style": str(raw.get("think_style") or "").strip(),
            "think_context": self._safe_bool(raw.get("think_context"), True),
            "think_context_chars": raw.get("think_context_chars", 4000),
            "think_voice": str(raw.get("think_voice") or "human").strip().lower(),
            "min_wait": raw.get("min_wait", 3),
            "max_wait": raw.get("max_wait", 8),
            "max_window": raw.get("max_window", 30),
            "max_passes": raw.get("max_passes", 4),
            "max_followups": raw.get("max_followups", 8),
            "max_chars": raw.get("max_chars", 16384),
            "max_bytes": raw.get("max_bytes", 16384),
            "forward_images": self._safe_bool(raw.get("forward_images"), True),
            "draft_concurrency": raw.get("draft_concurrency", 1),
        }

    async def _reply_debounce_style(self, event: AstrMessageEvent) -> str:
        """Use Zhiban's current effective persona voice for private drafts."""

        parts = []
        try:
            # AstrBot normally injects the selected base persona through
            # persona_manager; reuse that resolved value instead of guessing.
            manager = getattr(self.context, "persona_manager", None)
            resolver = getattr(manager, "resolve_selected_persona", None)
            if callable(resolver):
                umo = str(getattr(event, "unified_msg_origin", "") or "")
                conversation_persona_id = None
                conversations = getattr(self.context, "conversation_manager", None)
                get_current = getattr(conversations, "get_current_conversation", None)
                if callable(get_current) and umo:
                    try:
                        value = get_current(umo)
                        if inspect.isawaitable(value):
                            value = await value
                        conversation = value
                        conversation_persona_id = getattr(
                            conversation, "persona_id", None
                        )
                        if conversation_persona_id is None and isinstance(
                            conversation, dict
                        ):
                            conversation_persona_id = conversation.get("persona_id")
                    except Exception:
                        conversation_persona_id = None
                resolved = await resolver(
                    umo=umo,
                    conversation_persona_id=conversation_persona_id,
                    platform_name=event.get_platform_name(),
                )
                persona = resolved[1] if isinstance(resolved, tuple) and len(resolved) > 1 else None
                text = getattr(persona, "prompt", None)
                if text is None and isinstance(persona, dict):
                    text = persona.get("prompt")
                if text:
                    parts.append(str(text).strip())
        except Exception:
            parts = []

        try:
            from .memory_control import scope_for_event

            persona = getattr(self, "persona", None)
            if persona is not None:
                approved = await persona.approved_text(scope_for_event(event))
                if approved:
                    parts.append(str(approved).strip())
        except Exception:
            pass

        merged = "\n".join(part for part in parts if part)
        return merged[:2000]

    @staticmethod
    def _safe_bool(value, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "on", "启用", "开启"}:
                return True
            if text in {"0", "false", "no", "off", "禁用", "关闭"}:
                return False
        return bool(default if value is None else value)

    @staticmethod
    def _safe_management_value(value, default, low, high, *, integer=False, floating=False):
        try:
            converted = float(value) if floating else int(value)
        except (TypeError, ValueError, OverflowError):
            converted = float(default) if floating else int(default)
        if not converted == converted:
            converted = float(default) if floating else int(default)
        return max(low, min(high, converted))

    def _apply_runtime_controls(self) -> None:
        """Apply global resource limits and heart-owned chat behavior in-process."""
        management = self.config.get("management", {}) if isinstance(self.config, dict) else {}
        if not isinstance(management, dict):
            management = {}
        self.scheduler.configure(
            queue_limit=self._safe_management_value(management.get("queue_limit"), 20, 1, 100),
            session_queue_limit=self._safe_management_value(management.get("session_queue_limit"), 4, 1, 10),
            wait_seconds=self._safe_management_value(management.get("wait_seconds"), 90, 1, 600, floating=True),
            chat_concurrency=self._safe_management_value(management.get("chat_concurrency"), 1, 1, 4),
            media_concurrency=self._safe_management_value(management.get("media_concurrency"), 1, 1, 2),
            maintenance_concurrency=self._safe_management_value(management.get("maintenance_concurrency"), 1, 1, 2),
            media_queue_limit=self._safe_management_value(management.get("media_queue_limit"), 8, 1, 32),
            maintenance_queue_limit=self._safe_management_value(management.get("maintenance_queue_limit"), 8, 1, 32),
        )

        reply_debounce = getattr(self, "reply_debounce", None)
        if reply_debounce is not None:
            reply_debounce.configure(**self._reply_debounce_config())

    @filter.on_waiting_llm_request(priority=1000000)
    async def admit(self, event: AstrMessageEvent):
        async def admit_pipeline(candidate):
            return await self.scheduler.admit_pipeline(candidate)

        admitted = await self.reply_debounce.hold(event, admit_pipeline)
        if admitted:
            try:
                event.set_extra("_zhiban_usage_admitted", True)
            except Exception:
                pass
        else:
            self.logger.info("知伴：请求被回复协调器停止，或因队列限制未进入模型流程")

    @filter.on_llm_request(priority=40)
    async def merge_reply_request(self, event, req):
        """Inject the finished draft window after AngelHeart and before persona."""
        if getattr(self, "usage", None) is not None:
            try:
                current = event.get_extra("_zhiban_usage_call_id")
                if not current:
                    event.set_extra("_zhiban_usage_call_id", self.usage.new_call_id())
            except Exception:
                pass
        continued = await self.reply_debounce.merge_request(event, req)
        if not continued:
            event.stop_event()

    @filter.on_llm_response()
    async def record_llm_usage(self, event, response):
        if self.usage is None:
            return
        try:
            source = event.get_extra("_zhiban_usage_source")
            admitted = event.get_extra("_zhiban_usage_admitted")
            call_id = event.get_extra("_zhiban_usage_call_id")
        except Exception:
            source = None
            admitted = None
        if not source and not admitted:
            return
        status = "failed" if getattr(response, "role", "") == "err" else "completed"
        inserted = self.usage.record_event(
            event,
            response,
            source=str(source or "heart"),
            status=status,
            call_id=call_id,
            is_final=True,
        )
        if inserted:
            try:
                event.set_extra("_zhiban_usage_recorded", True)
            except Exception:
                pass

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
            report = {"调度": self.scheduler.status(), "回复防抖": self.reply_debounce.status(), "模块": self.host.status() if self.host else {}}
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
        await self.reply_debounce.close()
        # Shut down hosted modules while their maintenance tickets can still be
        # acquired; close the scheduler only after module resources are released.
        try:
            if self.host is not None:
                await self.host.close()
            if self.persona is not None and hasattr(self.persona, "close"):
                result = self.persona.close()
                if hasattr(result, "__await__"):
                    await result
        finally:
            await self.scheduler.close()
