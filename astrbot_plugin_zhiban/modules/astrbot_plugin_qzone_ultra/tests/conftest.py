"""Isolate module reloads performed by QQ 空间 security tests."""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def isolate_qzone_runtime_modules():
    """Restore qzone_bridge and main after tests that import them with stubs."""
    saved_qzone = {
        name: module
        for name, module in sys.modules.items()
        if name == "qzone_bridge" or name.startswith("qzone_bridge.")
    }
    saved_main = sys.modules.get("main")
    yield
    for name in list(sys.modules):
        if name == "qzone_bridge" or name.startswith("qzone_bridge.") or name == "main":
            sys.modules.pop(name, None)
    sys.modules.update(saved_qzone)
    if saved_main is not None:
        sys.modules["main"] = saved_main
