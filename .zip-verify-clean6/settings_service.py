"""Schema-backed, secret-safe configuration operations for the app shell."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any


class SettingsValidationError(ValueError):
    """A submitted setting does not match the plugin schema."""


class SettingsConflictError(ValueError):
    """The configuration changed after the editor loaded it."""


_SECRET_NAMES = {
    "api_key",
    "apikey",
    "access_key",
    "access_key_id",
    "secret",
    "secret_access_key",
    "client_secret",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "passwd",
    "cookie",
    "cookies",
    "cookies_str",
    "authorization",
    "private_key",
}


def is_secret_field(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    return normalized in _SECRET_NAMES


def settings_schema(module_schema: dict) -> dict:
    items = module_schema.get("items", {}) if isinstance(module_schema, dict) else {}
    schema = items.get("settings") if isinstance(items, dict) else None
    if isinstance(schema, dict) and schema.get("type") == "object":
        return schema
    return {"type": "object", "description": "此模块使用专用配置页面", "items": {}}


def _schema_defaults(schema: dict) -> Any:
    if schema.get("type") == "object":
        return {
            key: _schema_defaults(value)
            for key, value in schema.get("items", {}).items()
            if isinstance(value, dict)
        }
    return copy.deepcopy(schema.get("default"))


def _merge_existing(default: Any, existing: Any) -> Any:
    if isinstance(default, dict) and isinstance(existing, dict):
        result = copy.deepcopy(default)
        for key, value in existing.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = _merge_existing(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result
    return copy.deepcopy(existing) if existing is not None else copy.deepcopy(default)


def _collect_secrets(schema: dict, value: Any, path: tuple[str, ...] = ()):
    if schema.get("type") == "object":
        current = value if isinstance(value, dict) else {}
        for key, child_schema in schema.get("items", {}).items():
            if isinstance(child_schema, dict):
                yield from _collect_secrets(child_schema, current.get(key), path + (key,))
        return
    if path and is_secret_field(path[-1]):
        configured = isinstance(value, str) and bool(value.strip())
        yield ".".join(path), configured


def _redact_secrets(schema: dict, value: Any, field_name: str | None = None) -> Any:
    if schema.get("type") == "object":
        current = value if isinstance(value, dict) else {}
        return {
            key: _redact_secrets(child_schema, current.get(key), key)
            for key, child_schema in schema.get("items", {}).items()
            if isinstance(child_schema, dict)
        }
    if schema.get("_secret") or (field_name and is_secret_field(field_name)):
        return ""
    return copy.deepcopy(value)


def config_revision(section: dict) -> str:
    canonical = json.dumps(
        dict(section or {}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def read_module_config(module_schema: dict, section: dict) -> dict:
    schema = settings_schema(module_schema)
    settings = section.get("settings", {}) if isinstance(section, dict) else {}
    merged = _merge_existing(_schema_defaults(schema), settings)
    secrets = list(_collect_secrets(schema, merged))
    return {
        "enabled": bool(section.get("enabled", True)) if isinstance(section, dict) else True,
        "settings": _redact_secrets(schema, merged),
        "schema": copy.deepcopy(schema),
        "secret_fields": [path for path, _ in secrets],
        "configured_secrets": [path for path, configured in secrets if configured],
        "revision": config_revision(section or {}),
    }


def _validate_value(schema: dict, value: Any, path: tuple[str, ...]) -> Any:
    kind = schema.get("type")
    label = ".".join(path) or "settings"
    if kind == "string" or kind == "text":
        if not isinstance(value, str):
            raise SettingsValidationError(f"{label} 必须是文本")
        min_length = schema.get("min_length")
        max_length = schema.get("max_length")
        if min_length is not None and len(value) < min_length:
            raise SettingsValidationError(f"{label} 字数过少")
        if max_length is not None and len(value) > max_length:
            raise SettingsValidationError(f"{label} 字数超出限制")
        return value
    if kind == "bool":
        if not isinstance(value, bool):
            raise SettingsValidationError(f"{label} 必须是布尔值")
        return value
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SettingsValidationError(f"{label} 必须是整数")
        number = value
    elif kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SettingsValidationError(f"{label} 必须是数字")
        number = float(value)
        if not math.isfinite(number):
            raise SettingsValidationError(f"{label} 数值无效")
    elif kind in {"list", "template_list"}:
        if not isinstance(value, list):
            raise SettingsValidationError(f"{label} 必须是列表")
        item_schema = schema.get("item")
        if isinstance(item_schema, dict):
            return [
                _validate_value(item_schema, item, path + (str(index),))
                for index, item in enumerate(value)
            ]
        return copy.deepcopy(value)
    elif kind == "dict":
        if not isinstance(value, dict):
            raise SettingsValidationError(f"{label} 必须是对象")
        return copy.deepcopy(value)
    else:
        raise SettingsValidationError(f"{label} 的配置类型不受支持")

    slider = schema.get("slider")
    minimum = slider.get("min") if isinstance(slider, dict) else schema.get("min")
    maximum = slider.get("max") if isinstance(slider, dict) else schema.get("max")
    if minimum is not None and number < minimum:
        raise SettingsValidationError(f"{label} 不能小于 {minimum}")
    if maximum is not None and number > maximum:
        raise SettingsValidationError(f"{label} 不能大于 {maximum}")
    return number


def _patch_object(
    schema: dict,
    current: dict,
    patch: dict,
    path: tuple[str, ...],
    clear_secrets: set[str],
) -> dict:
    if not isinstance(patch, dict):
        raise SettingsValidationError(f"{'.'.join(path) or 'settings'} 必须是对象")
    items = schema.get("items", {})
    result = copy.deepcopy(current if isinstance(current, dict) else {})
    for key, value in patch.items():
        if key not in items or not isinstance(items[key], dict):
            raise SettingsValidationError(f"未知配置项：{'.'.join(path + (str(key),))}")
        child_schema = items[key]
        child_path = path + (key,)
        if child_schema.get("type") == "object":
            result[key] = _patch_object(
                child_schema,
                result.get(key, {}),
                value,
                child_path,
                clear_secrets,
            )
            continue
        new_value = _validate_value(child_schema, value, child_path)
        if is_secret_field(key) and new_value == "" and result.get(key):
            if ".".join(child_path) not in clear_secrets:
                continue
        result[key] = new_value
    return result


def _schema_at_path(schema: dict, path: str) -> tuple[dict, tuple[str, ...]] | None:
    parts = tuple(part for part in str(path).replace("/", ".").split(".") if part)
    if not parts:
        return None
    current = schema
    for part in parts:
        if current.get("type") != "object":
            return None
        current = current.get("items", {}).get(part)
        if not isinstance(current, dict):
            return None
    return current, parts


def apply_module_patch(
    module_schema: dict,
    section: dict,
    *,
    expected_revision: str,
    changes: dict,
    enabled: bool | None = None,
    clear_secrets: list[str] | None = None,
) -> dict:
    current = dict(section or {})
    if expected_revision != config_revision(current):
        raise SettingsConflictError("配置已被其他操作更新，请重新载入后再保存")
    if enabled is not None and not isinstance(enabled, bool):
        raise SettingsValidationError("模块开关必须是布尔值")

    schema = settings_schema(module_schema)
    if not changes and enabled is None and not clear_secrets:
        raise SettingsValidationError("没有可保存的配置更改")
    settings = _patch_object(
        schema,
        current.get("settings", {}),
        changes or {},
        (),
        {str(path).replace("/", ".") for path in (clear_secrets or [])},
    )
    result = copy.deepcopy(current)
    if enabled is not None:
        result["enabled"] = enabled
    if "settings" in current or settings:
        result["settings"] = settings

    for secret_path in clear_secrets or []:
        entry = _schema_at_path(schema, secret_path)
        if entry is None or not is_secret_field(entry[1][-1]) or entry[0].get("type") not in {"string", "text"}:
            raise SettingsValidationError(f"不是有效的密钥配置项：{secret_path}")
        target: Any = result.setdefault("settings", {})
        for key in entry[1][:-1]:
            target = target.setdefault(key, {})
        target[entry[1][-1]] = ""
    return result
