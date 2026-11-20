"""Persist only the shell's current route, never page content or secrets."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .catalog import GROUPS, MODULES

GROUP_KEYS = {group["key"] for group in GROUPS}
MODULE_GROUP_KEYS = {
    spec["key"]: next(
        (group["key"] for group in GROUPS if group["label"] == spec["group"]),
        "",
    )
    for spec in MODULES
}
MODULE_KEYS = set(MODULE_GROUP_KEYS)
MODULE_SUBPAGES = {
    "meme": {"manage", "catalog", "semantic", "settings"},
}
ROUTE_QUERY_KEYS = {
    "meme": {
        "manage": {"managed_pack_id", "review_collection"},
        "catalog": {"view"},
    },
}
VIEW_KEYS = {"overview", "global", "workbench", "settings"}


def _clean_text(value: Any, limit: int = 120) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if len(text) > limit or any(char in text for char in "\r\n\0"):
        return ""
    return text


def _clean_hash(value: Any) -> str:
    text = _clean_text(value, 120).lstrip("#")
    if not text:
        return ""
    if any(not (char.isalnum() or char in "_-") for char in text):
        return ""
    return text


def _clean_query(module: str, sub: str, value: Any) -> dict[str, str]:
    allowed = ROUTE_QUERY_KEYS.get(module, {}).get(sub, set())
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, raw in value.items():
        if key not in allowed:
            continue
        text = _clean_text(raw, 240)
        if text:
            result[str(key)] = text
    return result


def sanitize_ui_route(payload: Any) -> dict | None:
    """Return a strict route shape; unknown modules/subpages never pass through."""
    if not isinstance(payload, dict):
        return None
    group = _clean_text(payload.get("group"), 32)
    module = _clean_text(payload.get("module"), 32)
    view = _clean_text(payload.get("view"), 32)
    if group not in GROUP_KEYS and group != "overview":
        return None
    if group == "overview" or (not module and view in {"overview", "global"}):
        return {
            "group": "overview",
            "module": "",
            "view": "global" if view == "global" else "overview",
            "sub": "",
            "subhash": "",
            "subq": {},
        }
    if module not in MODULE_KEYS:
        return None
    if group != MODULE_GROUP_KEYS[module]:
        group = MODULE_GROUP_KEYS[module]
    if view not in {"workbench", "settings"}:
        view = "workbench"
    sub = _clean_text(payload.get("sub"), 32)
    if sub not in MODULE_SUBPAGES.get(module, set()):
        sub = ""
    return {
        "group": group,
        "module": module,
        "view": view,
        "sub": sub,
        "subhash": _clean_hash(payload.get("subhash")) if sub else "",
        "subq": _clean_query(module, sub, payload.get("subq")) if sub else {},
    }


class RouteStore:
    """Small atomic JSON store keyed by the validated dashboard username."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def _read_all(self) -> dict[str, dict]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        result: dict[str, dict] = {}
        for username, route in raw.items():
            if not isinstance(username, str) or not username.strip():
                continue
            cleaned = sanitize_ui_route(route)
            if cleaned is not None:
                result[username[:160]] = cleaned
        return result

    def get(self, username: str) -> dict | None:
        name = _clean_text(username, 160)
        if not name:
            return None
        with self._lock:
            return self._read_all().get(name)

    def put(self, username: str, route: Any) -> dict | None:
        name = _clean_text(username, 160)
        cleaned = sanitize_ui_route(route)
        if not name or cleaned is None:
            return None
        with self._lock:
            data = self._read_all()
            data[name] = cleaned
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = None
            temp_path = None
            try:
                handle = tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    delete=False,
                )
                temp_path = Path(handle.name)
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                handle.close()
                handle = None
                os.replace(temp_path, self.path)
                return cleaned
            finally:
                if handle is not None:
                    handle.close()
                if temp_path is not None and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
