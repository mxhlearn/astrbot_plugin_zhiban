"""Allowlisted routing from the 知伴 shell to a bundled module's own APIs."""
from __future__ import annotations

from .ui_assets import MODULE_API_NAMES


def module_api_target(module: str, api_path: str) -> str | None:
    plugin_name = MODULE_API_NAMES.get(module)
    path = str(api_path or "").strip()
    parts = path.split("/")
    if (
        not plugin_name
        or not path
        or path.startswith("/")
        or path.endswith("/")
        or "\\" in path
        or "://" in path
        or "?" in path
        or "#" in path
        or any(part in {"", ".", ".."} for part in parts)
    ):
        return None
    return f"{plugin_name}/{path}"


def dashboard_session_authorized(request_context: object, api_key_username_prefix: str) -> bool:
    """Check AstrBot's validated PluginRequest identity, not raw token text.

    AstrBot binds the validated username to ``PluginRequest`` after its route
    dependency checks the JWT or dashboard cookie. API-key callers are marked
    with ``API_KEY_USERNAME_PREFIX`` and are intentionally excluded here.
    """
    try:
        username = getattr(request_context, "username", None)
    except RuntimeError:
        return False
    if not isinstance(username, str) or not username.strip():
        return False
    return not username.startswith(api_key_username_prefix)


