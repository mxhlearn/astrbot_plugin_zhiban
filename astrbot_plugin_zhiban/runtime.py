"""Lifecycle adapter for the production plugins bundled inside 知伴.

Business handlers retain AstrBot's filters and priority ordering.  Only ownership
and instance binding change: AstrBot sees a single plugin and can disable/unload
all of its handlers and tools together. No global monkey-patching is used.
"""
from __future__ import annotations

import asyncio
import copy
import functools
import importlib
import inspect
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _framework():
    from astrbot.core.provider.register import llm_tools
    from astrbot.core.star.star import star_map, star_registry
    from astrbot.core.star.star_handler import star_handlers_registry

    return star_map, star_registry, star_handlers_registry, llm_tools


def _get(spec: Any, name: str, default: Any = None) -> Any:
    return spec.get(name, default) if isinstance(spec, dict) else getattr(spec, name, default)


def _defaults(schema: dict) -> dict:
    result = {}
    fallback = {"string": "", "text": "", "int": 0, "float": 0.0,
                "bool": False, "list": [], "template_list": [], "dict": {}}
    for key, item in schema.items():
        if not isinstance(item, dict):
            continue
        if item.get("type") == "object":
            result[key] = _defaults(item.get("items", {}))
        else:
            result[key] = copy.deepcopy(item.get("default", fallback.get(item.get("type"))))
    return result


def _merge_defaults(value: dict, default: dict) -> dict:
    result = copy.deepcopy(default)
    for key, item in value.items():
        if isinstance(item, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_defaults(item, result[key])
        else:
            result[key] = copy.deepcopy(item)
    return result


class ModuleConfig(dict):
    """Upstream-compatible configuration backed by one parent settings object."""

    def __init__(self, parent: dict, key: str, schema: dict | None = None):
        self._parent = parent
        self._key = key
        self.zhiban_module = True
        self.schema = schema or {}
        self.default_config = _defaults(self.schema)
        section = parent.setdefault(key, {})
        settings = section.setdefault("settings", {})
        super().__init__(_merge_defaults(settings, self.default_config))
        # Do not expose the parent's file path as a child's writable JSON file.
        # Modules must persist through save_config(), not overwrite a flat file.
        self.config_path = None
        self.first_deploy = not bool(settings)
        section["settings"] = self

    def save_config(self, replace_config: dict | None = None, *, indent: int = 2):
        if replace_config:
            self.update(replace_config)
        self._parent[self._key]["settings"] = self
        save = getattr(self._parent, "save_config", None)
        if callable(save):
            save(indent=indent)

    async def save_config_async(self, replace_config: dict | None = None, *, indent: int = 2):
        if replace_config:
            self.update(replace_config)
        self._parent[self._key]["settings"] = self
        save = getattr(self._parent, "save_config_async", None)
        if callable(save):
            return await save(indent=indent)
        self.save_config(indent=indent)
        return True

    def __deepcopy__(self, memo):
        # Parent AstrBotConfig snapshots must not copy the parent reference,
        # its locks, or its complete configuration through this child view.
        return copy.deepcopy(dict(self), memo)


@dataclass
class _ModuleState:
    key: str
    label: str
    package: str
    prefix: str
    state: str = "disabled"
    error: str | None = None
    instance: Any = None
    context: Any = None
    handlers: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    previous_tools: dict = field(default_factory=dict)
    routes: list = field(default_factory=list)
    previous_routes: dict = field(default_factory=dict)
    imported: dict = field(default_factory=dict)


class _ModuleContext:
    """Forward framework services, while tracking resources owned by a module."""

    def __init__(self, host: "ModuleHost", state: _ModuleState):
        self._host = host
        self._state = state
        self._context = host.parent.context
        if state.key == "memory":
            self.zhiban_data_dir = host.data_dir / "memory"
        else:
            from astrbot.core.star.star_tools import StarTools
            self.zhiban_data_dir = Path(StarTools.get_data_dir(state.package))
        self.zhiban_data_dir.mkdir(parents=True, exist_ok=True)
        self.zhiban_module_key = state.key
        self.zhiban_parent = host.parent

    def __getattr__(self, name):
        return getattr(self._context, name)

    def add_llm_tools(self, *tools):
        manager = self._context.provider_manager.llm_tools
        for tool in tools:
            old = next((item for item in manager.func_list if item.name == tool.name), None)
            if old is not None and all(old is not owned for owned in self._state.tools):
                if getattr(old, "active", True):
                    raise RuntimeError(f"工具名称冲突: {tool.name}")
                self._state.previous_tools.setdefault(tool.name, old)
        self._context.add_llm_tools(*tools)
        for tool in tools:
            self._host._own_tool(self._state, tool)

    def register_web_api(self, route, view_handler, methods, desc):
        key = (route, tuple(methods))
        existing = next((api for api in self._context.registered_web_apis
                         if api[0] == route and tuple(api[2]) == tuple(methods)), None)
        if key not in self._state.previous_routes:
            self._state.previous_routes[key] = existing
        self._context.register_web_api(route, view_handler, methods, desc)
        self._state.routes.append((route, view_handler, tuple(methods)))


class ModuleHost:
    """Load migrated plugins as modules owned by the single 知伴 Star instance."""

    def __init__(self, parent, config: dict, specs, data_dir: Path):
        self.parent = parent
        self.config = config
        self.specs = tuple(specs)
        self.data_dir = Path(data_dir)
        self.owner = type(parent).__module__
        self.package = self.owner.rsplit(".", 1)[0]
        self.log = getattr(parent, "logger", logging.getLogger("astrbot.zhiban"))
        self._states: dict[str, _ModuleState] = {}
        self._started = False
        self._closed = False
        self._lock = asyncio.Lock()

    @property
    def instances(self) -> dict[str, Any]:
        return {key: state.instance for key, state in self._states.items()
                if state.state == "running"}

    def status(self) -> list[dict]:
        return [{"key": s.key, "label": s.label, "state": s.state,
                 "error": s.error, "handlers": len(s.handlers), "tools": len(s.tools)}
                for s in self._states.values()]

    async def start(self):
        async with self._lock:
            if self._started:
                return self.status()
            if self._closed:
                raise RuntimeError("已关闭的模块宿主不能重复启动，请重新加载插件")
            self._started = True
            for spec in self.specs:
                key = _get(spec, "key")
                package = _get(spec, "package")
                state = _ModuleState(key, _get(spec, "label", key), package,
                                     f"{self.package}.modules.{package}")
                self._states[key] = state
                section = self.config.get(key, {})
                if not isinstance(section, dict) or not section.get("enabled", True):
                    continue
                conflict = self._active_original(state)
                if conflict:
                    state.state = "blocked"
                    state.error = f"原插件仍在运行：{conflict}"
                    continue
                await self._start_module(state)
            self._refresh_owner_handlers()
            return self.status()

    def _active_original(self, state):
        _, registry, _, _ = _framework()
        names = {state.package, state.package.removeprefix("astrbot_plugin_")}
        for metadata in registry:
            if metadata.module_path == self.owner:
                continue
            if (getattr(metadata, "name", None) in names
                    or getattr(metadata, "root_dir_name", None) == state.package):
                if getattr(metadata, "activated", False) and getattr(metadata, "star_cls", None) is not None:
                    return getattr(metadata, "name", state.package)
        return None

    async def _start_module(self, state):
        star_map, registry, handlers, global_tools = _framework()
        state.state = "starting"
        before_handlers = {id(h) for h in handlers}
        managers = self._tool_managers(global_tools)
        before_tools = {id(t): t for manager in managers for t in manager.func_list}
        before_tool_names = {t.name: t for t in before_tools.values()}
        before_modules = set(sys.modules)
        try:
            module = importlib.import_module(state.prefix + ".main")
            metadata = star_map.get(module.__name__)
            cls = getattr(metadata, "star_cls_type", None)
            if cls is None:
                raise RuntimeError("模块未注册 AstrBot Star 类")
            schema_path = Path(module.__file__).parent / "_conf_schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8-sig")) if schema_path.exists() else {}
            config = ModuleConfig(self.config, state.key, schema)
            state.context = _ModuleContext(self, state)
            # Match the framework's pre-instantiation identity injection, but
            # namespace KV storage so old plugin state is not overwritten.
            cls.name = state.package
            cls.author = "zhiban"
            cls.plugin_id = f"zhiban/{state.key}"
            instance = cls.__new__(cls)
            state.instance = instance
            args = {"context": state.context}
            if "config" in inspect.signature(cls.__init__).parameters:
                args["config"] = config
            cls.__init__(instance, **args)
            metadata.star_cls = instance
            metadata.config = config
            metadata.module = module
            metadata.root_dir_name = state.package
            self._bind_handlers(state, before_handlers)
            self._collect_tools(state, before_tools, before_tool_names)
            initialize = getattr(instance, "initialize", None)
            if callable(initialize):
                result = initialize()
                if inspect.isawaitable(result):
                    await asyncio.wait_for(result, timeout=60)
            self._bind_handlers(state, before_handlers)
            self._collect_tools(state, before_tools, before_tool_names)
            state.state = "running"
        except asyncio.CancelledError:
            state.error = "启动已取消"
            await self._terminate_instance(state)
            self._collect_failed_registration(state, before_handlers, before_tools, before_tool_names)
            self._cleanup_registration(state)
            state.state = "failed"
            raise
        except Exception as exc:
            # Avoid serializing provider URLs, tokens or configuration in status.
            state.error = type(exc).__name__
            self.log.error("知伴模块 %s 启动失败（%s）", state.label, type(exc).__name__)
            await self._terminate_instance(state)
            self._collect_failed_registration(state, before_handlers, before_tools, before_tool_names)
            self._cleanup_registration(state)
            state.state = "failed"
        finally:
            state.imported.update({name: value for name, value in tuple(sys.modules.items())
                                   if name not in before_modules and self._is_module_file(state, name, value)})
            # Children are implementation details, not additional dashboard plugins.
            self._remove_child_metadata(state)
            if state.state == "failed":
                self._evict_modules(state)

    def _is_module_file(self, state, name, value):
        if name == state.prefix or name.startswith(state.prefix + "."):
            return True
        filename = getattr(value, "__file__", None)
        if not filename:
            return False
        expected = Path(__file__).parent / "modules" / state.package
        try:
            return Path(filename).resolve().is_relative_to(expected.resolve())
        except (ValueError, OSError):
            return False

    def _tool_managers(self, global_tools):
        actual = self.parent.context.provider_manager.llm_tools
        return [actual] if actual is global_tools else [actual, global_tools]

    def _own_tool(self, state, tool):
        tool.handler_module_path = self.owner
        if all(tool is not other for other in state.tools):
            state.tools.append(tool)

    def _collect_tools(self, state, before_tools, before_names):
        _, _, _, global_tools = _framework()
        for manager in self._tool_managers(global_tools):
            for tool in list(manager.func_list):
                handler = getattr(tool, "handler", None)
                raw = handler.func if isinstance(handler, functools.partial) else handler
                path = getattr(tool, "handler_module_path", None) or getattr(raw, "__module__", "")
                owned = path == state.prefix or path.startswith(state.prefix + ".")
                owned |= any(tool is t for t in state.tools)
                if not owned:
                    continue
                if id(tool) not in before_tools and tool.name in before_names:
                    state.previous_tools.setdefault(tool.name, before_names[tool.name])
                    old = before_names[tool.name]
                    if getattr(old, "active", True) and old is not tool:
                        self._own_tool(state, tool)
                        raise RuntimeError(f"工具名称冲突: {tool.name}")
                if raw is not None and getattr(raw, "__module__", "").startswith(state.prefix + "."):
                    # Decorator tools have an unbound self parameter. Dynamic
                    # FunctionTool subclasses usually implement call() instead.
                    if not inspect.ismethod(handler) and not isinstance(handler, functools.partial):
                        params = list(inspect.signature(raw).parameters)
                        if params and params[0] == "self":
                            tool.handler = functools.partial(raw, state.instance)
                self._own_tool(state, tool)

    def _bind_handlers(self, state, before_handlers):
        _, _, handlers, _ = _framework()
        for handler in list(handlers):
            if any(handler is h for h in state.handlers):
                continue
            if (id(handler) not in before_handlers
                    and (handler.handler_module_path == state.prefix
                         or handler.handler_module_path.startswith(state.prefix + "."))):
                raw = handler.handler
                if not inspect.ismethod(raw) and not isinstance(raw, functools.partial):
                    handler.handler = functools.partial(raw, state.instance)
                handler.handler_module_path = self.owner
                state.handlers.append(handler)

    def _collect_failed_registration(self, state, before_handlers, before_tools, before_names):
        _, _, handlers, _ = _framework()
        for h in list(handlers):
            if id(h) not in before_handlers and h.handler_module_path.startswith(state.prefix + "."):
                if all(h is not owned for owned in state.handlers):
                    state.handlers.append(h)
        # Failure cleanup must not re-raise a collision detected during binding.
        _, _, _, global_tools = _framework()
        for manager in self._tool_managers(global_tools):
            for tool in list(manager.func_list):
                path = getattr(tool, "handler_module_path", None) or ""
                raw = getattr(tool, "handler", None)
                if isinstance(raw, functools.partial):
                    raw = raw.func
                raw_path = getattr(raw, "__module__", "")
                if (path.startswith(state.prefix + ".") or raw_path.startswith(state.prefix + ".")
                        or any(tool is owned for owned in state.tools)):
                    if id(tool) not in before_tools and tool.name in before_names:
                        state.previous_tools.setdefault(tool.name, before_names[tool.name])
                    self._own_tool(state, tool)

    def _remove_child_metadata(self, state):
        star_map, registry, _, _ = _framework()
        paths = [path for path in star_map if path == state.prefix or path.startswith(state.prefix + ".")]
        for path in paths:
            star_map.pop(path, None)
        registry[:] = [metadata for metadata in registry if not (
            getattr(metadata, "module_path", "") == state.prefix
            or (getattr(metadata, "module_path", "") or "").startswith(state.prefix + "."))]

    def _refresh_owner_handlers(self):
        star_map, _, handlers, _ = _framework()
        metadata = star_map.get(self.owner)
        if metadata is not None:
            metadata.star_handler_full_names = [h.handler_full_name for h in handlers
                                               if h.handler_module_path == self.owner]

    async def _terminate_instance(self, state):
        if state.instance is None:
            return
        terminate = getattr(state.instance, "terminate", None)
        if callable(terminate):
            try:
                result = terminate()
                if inspect.isawaitable(result):
                    await asyncio.wait_for(result, timeout=20)
            except Exception as exc:
                state.error = f"{state.error + '; ' if state.error else ''}清理失败:{type(exc).__name__}"
                self.log.error("知伴模块 %s 清理失败（%s）", state.label, type(exc).__name__)

    def _cleanup_registration(self, state):
        _, _, handlers, global_tools = _framework()
        for handler in state.handlers:
            handlers.remove(handler)
        state.handlers.clear()
        for manager in self._tool_managers(global_tools):
            manager.func_list[:] = [tool for tool in manager.func_list
                                   if all(tool is not owned for owned in state.tools)]
            for name, old in state.previous_tools.items():
                if not any(tool.name == name for tool in manager.func_list):
                    manager.func_list.append(old)
        state.tools.clear()
        routes = self.parent.context.registered_web_apis
        routes[:] = [api for api in routes if not any(
            api[0] == route and api[1] is handler and tuple(api[2]) == methods
            for route, handler, methods in state.routes)]
        for key, old in state.previous_routes.items():
            if old is not None and not any((api[0], tuple(api[2])) == key for api in routes):
                routes.append(old)
        state.routes.clear()
        self._remove_child_metadata(state)

    def _evict_modules(self, state):
        for name, module in reversed(tuple(state.imported.items())):
            if sys.modules.get(name) is module:
                sys.modules.pop(name, None)
        state.imported.clear()

    async def close(self):
        async with self._lock:
            if self._closed:
                return self.status()
            self._closed = True
            for state in reversed(tuple(self._states.values())):
                was_running = state.state == "running"
                if was_running:
                    state.state = "stopping"
                    await self._terminate_instance(state)
                self._cleanup_registration(state)
                self._evict_modules(state)
                if was_running:
                    state.state = "failed" if state.error else "stopped"
            self._refresh_owner_handlers()
            return self.status()
