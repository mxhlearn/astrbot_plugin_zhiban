import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "pages" / "app"


def read(relative: str) -> str:
    return (APP / relative).read_text("utf-8")


def test_embedded_navigation_contract_uses_parent_router():
    ui = read("shared/ui.js")
    assert "window.ZhibanModule" in ui
    assert "zhibanModule.isEmbedded === true" in ui
    assert "function navigateModuleTarget" in ui
    assert "zhibanModule.navigate(target)" in ui
    assert "document.baseURI" in ui
    assert "function getRouteQuery" in ui
    assert "function getRouteHash" in ui
    assert "aria-current" in ui
    assert 'link.dataset.moduleTarget = `${page}/index.html`;' in ui
    assert "if (embedded || nextUrl.origin !== location.origin) continue;" in ui
    assert 'if (embedded) return "";' in ui


def test_page_scripts_do_not_leave_controlled_route():
    forbidden = re.compile(
        r"(?:window\.)?location\.(?:assign|replace|reload)\s*\(|"
        r"(?:window\.)?location\.href\s*="
    )
    for relative in (
        "a_manage/script.js",
        "catalog/script.js",
        "semantic/script.js",
        "settings/script.js",
    ):
        source = read(relative)
        assert not forbidden.search(source), relative


def test_index_redirect_only_uses_location_replace_outside_embed():
    page = read("index.html")
    assert page.count("window.location.replace") == 1
    assert "window.ZhibanModule" in page
    assert "window.ZhibanModule.navigate(target)" in page
    assert page.index("if (embedded)") < page.index("window.location.replace")


def test_settings_hash_sync_is_srcdoc_safe():
    config = read("settings/config.js")
    assert config.count("history.replaceState(") == 1
    assert "function syncSettingsHash(value)" in config
    assert "if (window.MemeUI?.isEmbedded) {" in config
    assert "window.MemeUI.updateRoute?." in config
    assert "window.MemeUI?.getRouteHash?.()" in config
    assert 'document.documentElement.dataset.zhibanSubpageHash = hash;' in config


def test_empty_library_uses_non_blocking_state_actions():
    manage = read("a_manage/script.js")
    assert "第一次使用？" not in manage
    assert "maybeShowFirstUseCatalogGuide" not in manage
    assert "firstUseCatalogGuideShown" not in manage
    assert 'id="empty-hint-import"' in manage
    assert '<button id="empty-hint-open-catalog" type="button" data-module-target="catalog/index.html?view=catalog">前往资源广场</button>' in manage
    assert 'getElementById("empty-hint-open-catalog")' in manage
    assert "void openCatalogPage();" in manage
    bridge = (ROOT.parents[1] / "views" / "知伴" / "module_bridge.js").read_text("utf-8")
    assert "button[data-module-target]" in bridge
    assert "event.stopImmediatePropagation();" in bridge


def test_deep_link_query_and_hash_are_route_first():
    manage = read("a_manage/script.js")
    assert "window.MemeUI.getRouteQuery()" in manage
    assert "initialRouteQuery.managed_pack_id" in manage
    assert "initialRouteQuery.review_collection" in manage
    ui = read("shared/ui.js")
    query_fn = ui[ui.index("function getRouteQuery()") : ui.index("function getRouteHash()")]
    assert "route.query" in query_fn
    assert "location.search" in query_fn
    assert 'key === "asset_token"' in query_fn


def test_settings_navigation_confirms_before_dropping_drafts():
    script = read("settings/script.js")
    assert "离开设置页面" in script
    assert "window.addEventListener(" in script
    assert "navigateTarget(moduleTarget || rawHref)" in script
    assert "allowPageLeave = true;" in script


def test_module_targets_stay_inside_known_subpages():
    allowed = {
        "a_manage/index.html",
        "catalog/index.html",
        "semantic/index.html",
        "settings/index.html",
        "index.html",
    }
    for relative in (
        "shared/ui.js",
        "a_manage/script.js",
        "catalog/script.js",
        "semantic/script.js",
        "settings/script.js",
    ):
        source = read(relative)
        for target in re.findall(
            r"(?:navigateTarget|navigateModuleTarget|buildModuleTarget|navigate)\(\s*\"([^\"]+)\"",
            source,
        ):
            assert target in allowed, (relative, target)
        assert "javascript:" not in source
        assert "asset_token" not in re.findall(
            r"navigate(?:Target|ModuleTarget)?\(\s*\"([^\"]+)\"", source
        )


def test_shared_route_contract_uses_parent_context_and_whitelist():
    ui = read("shared/ui.js")
    assert "zhibanModule.onContext(" in ui
    assert "function onRouteChange(" in ui
    assert "function updateRouteMetadata(" in ui
    assert "function syncModuleRoute(" in ui
    assert "function normalizeModuleTarget(" in ui
    assert "if (!raw || raw.startsWith("#")) return "";" in ui
    assert "const parts = [];" in ui
    assert "function ensureBreadcrumb(" in ui
    assert "if (embedded) return;" in ui
    assert "The parent shell owns the breadcrumb" in ui
    assert "window.MemeUI.updateRoute" not in ui


def test_page_titles_and_deep_links_use_expression_creation_crumbs():
    settings_page = read("settings/index.html")
    assert "settings-page-breadcrumb" not in settings_page
    assert "设置中心" in settings_page
    assert "表情互动" in read("a_manage/index.html")
    assert 'window.MemeUI.go("settings/index.html#backup")' in read(
        "a_manage/script.js"
    )
    catalog = read("catalog/script.js")
    assert 'new Set(["catalog", "updates"])' in catalog
    assert "onRouteChange" in catalog
    config = read("settings/config.js")
    assert "onRouteChange" in config
    assert 'window.MemeUI.updateRoute?.' in config


def test_semantic_page_has_no_absolute_bridge_sdk_dependency():
    page = read("semantic/index.html")
    assert "/api/plugin/page/bridge-sdk.js" not in page


def test_shared_ui_route_functions_are_unique():
    ui = read("shared/ui.js")
    for name in (
        "navigateModuleTarget",
        "syncModuleRoute",
        "onRouteChange",
        "ensureBreadcrumb",
    ):
        assert ui.count(f"function {name}(") == 1, name
