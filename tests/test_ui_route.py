import json
import shutil
import tempfile
from pathlib import Path

import pytest

from astrbot_plugin_zhiban.ui_route import RouteStore, sanitize_ui_route


def test_sanitize_meme_settings_deep_link():
    route = sanitize_ui_route({
        "group": "creative",
        "module": "meme",
        "view": "settings",
        "sub": "settings",
        "subhash": "config-group-semantic-models",
        "subq": {},
    })
    assert route == {
        "group": "creative",
        "module": "meme",
        "view": "settings",
        "sub": "settings",
        "subhash": "config-group-semantic-models",
        "subq": {},
    }


def test_sanitize_catalog_query_and_rejects_unknown_query_keys():
    route = sanitize_ui_route({
        "group": "creative",
        "module": "meme",
        "view": "workbench",
        "sub": "catalog",
        "subq": {"view": "catalog", "redirect": "https://example.invalid"},
    })
    assert route["subq"] == {"view": "catalog"}


@pytest.mark.parametrize("sub", ["../catalog", "a_manage/../../settings", "unknown"])
def test_sanitize_rejects_cross_module_and_traversal_subpages(sub):
    route = sanitize_ui_route({
        "group": "creative",
        "module": "meme",
        "view": "workbench",
        "sub": sub,
    })
    assert route["sub"] == ""


def test_sanitize_unknown_module_is_rejected():
    assert sanitize_ui_route({
        "group": "creative",
        "module": "not-a-module",
        "view": "workbench",
        "sub": "catalog",
    }) is None


def test_sanitize_overview_never_keeps_module_or_subpage():
    route = sanitize_ui_route({
        "group": "overview",
        "module": "meme",
        "view": "global",
        "sub": "settings",
        "subhash": "x",
        "subq": {"view": "catalog"},
    })
    assert route == {
        "group": "overview",
        "module": "",
        "view": "global",
        "sub": "",
        "subhash": "",
        "subq": {},
    }


def test_sanitize_rejects_control_characters_in_hash_and_query():
    route = sanitize_ui_route({
        "group": "creative",
        "module": "meme",
        "view": "settings",
        "sub": "settings",
        "subhash": "bad\nvalue",
        "subq": {},
    })
    assert route["subhash"] == ""


@pytest.fixture
def route_tmp():
    base = Path.cwd() / ".tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="ui-route-", dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_route_store_roundtrip_and_atomic_replacement(route_tmp: Path):
    store = RouteStore(route_tmp / "ui_route.json")
    route = {
        "group": "creative",
        "module": "meme",
        "view": "workbench",
        "sub": "semantic",
        "subhash": "",
        "subq": {},
    }
    assert store.put("astrbot", route) == route
    assert store.get("astrbot") == route
    assert store.get("other") is None
    saved = json.loads((route_tmp / "ui_route.json").read_text(encoding="utf-8"))
    assert saved["astrbot"] == route
    assert not list(route_tmp.glob("*.tmp"))


def test_route_store_ignores_corrupt_and_invalid_entries(route_tmp: Path):
    path = route_tmp / "ui_route.json"
    path.write_text('{"bad": {"module": "meme", "group": "creative", "view": "workbench", "sub": "../settings"}, "ok": {"module": "meme", "group": "creative", "view": "workbench", "sub": "catalog"}}', encoding="utf-8")
    store = RouteStore(path)
    assert store.get("bad")["sub"] == ""
    assert store.get("ok")["sub"] == "catalog"


def test_route_store_rejects_empty_username(route_tmp: Path):
    store = RouteStore(route_tmp / "ui_route.json")
    assert store.put("", {"group": "overview", "view": "overview"}) is None
    assert store.get("") is None
