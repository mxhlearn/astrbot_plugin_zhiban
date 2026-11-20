import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qs

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "pages" / "dashboard"


def test_dashboard_supports_japanese_locale() -> None:
    index = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    source = (DASHBOARD / "i18n.js").read_text(encoding="utf-8")

    assert 'data-lang="ja"' in index
    assert '"zh", "en", "ru", "ja"' in source

    msg_block = source.split("const MSG = {", 1)[1].split("const MSG_JA", 1)[0]
    ja_block = source.split("const MSG_JA = {", 1)[1].split("  };", 1)[0]
    msg_keys = set(re.findall(r'"([A-Za-z0-9_.]+)":\s*\{', msg_block))
    ja_keys = set(re.findall(r'"([A-Za-z0-9_.]+)":\s*"', ja_block))
    assert ja_keys == msg_keys, "MSG_JA 必须覆盖全部 dashboard 文案"


def test_dashboard_loads_built_assets_instead_of_uncompressed_sources() -> None:
    index = (DASHBOARD / "index.html").read_text(encoding="utf-8")

    assert 'href="./assets/styles.min.css"' in index
    assert 'src="./assets/base.min.js"' in index
    assert 'src="./assets/graph.min.js"' in index
    for legacy in (
        "./appearance.js",
        "./styles.css",
        "./i18n.js",
        "./graph-shared.js",
        "./graph-ui.js",
    ):
        assert legacy not in index

    for name in ("styles.min.css", "base.min.js", "graph.min.js"):
        assert (DASHBOARD / "assets" / name).stat().st_size > 1_000


def test_dashboard_build_outputs_are_current() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不在 PATH，跳过 dashboard 构建产物校验")
    result = subprocess.run(
        [node, "scripts/build_dashboard.mjs", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_dashboard_vendors_and_loads_lucide_subset() -> None:
    index = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    app = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    subset = (DASHBOARD / "vendor" / "lucide-subset.js").read_text(encoding="utf-8")

    assert '<script src="./vendor/lucide-subset.js"></script>' in index
    size = len(subset.encode("utf-8"))
    assert 1_000 < size < 50_000, f"lucide 子集应保持轻量，实际 {size} 字节"
    assert (DASHBOARD / "vendor" / "LUCIDE_LICENSE").is_file()
    assert "lucide.createIcons" in app
    assert 'data-lucide="' in index


def test_lucide_subset_covers_every_used_icon() -> None:
    subset = (DASHBOARD / "vendor" / "lucide-subset.js").read_text(encoding="utf-8")
    sources = [DASHBOARD / "index.html", *sorted((DASHBOARD / "modules").glob("*.js"))]
    used: set[str] = set()
    for source in sources:
        used |= set(
            re.findall(r'data-lucide="([a-z0-9-]+)"', source.read_text(encoding="utf-8"))
        )
    # 三目表达式动态生成的图标名不会被正则捕获，显式列出
    used |= {"trash-2", "check"}

    missing = sorted(name for name in used if f'"{name}":' not in subset)
    assert not missing, f"lucide 子集缺少图标，需要重新生成: {missing}"


def test_dashboard_has_no_handwritten_or_inline_svg_icons() -> None:
    source_files = [
        DASHBOARD / "index.html",
        DASHBOARD / "styles.css",
        DASHBOARD / "art-direction.css",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)

    assert "<svg" not in combined.lower()
    assert "data:image/svg+xml" not in combined.lower()


def test_dashboard_visible_ui_has_no_emoji() -> None:
    source_files = [
        DASHBOARD / "index.html",
        DASHBOARD / "i18n.js",
        DASHBOARD / "modules" / "prompt-page.js",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)

    emoji_ranges = (
        (0x1F000, 0x1FAFF),
        (0x2600, 0x27BF),
    )
    assert "\ufe0f" not in combined
    assert not any(
        start <= ord(character) <= end
        for character in combined
        for start, end in emoji_ranges
    )


def test_dynamic_dashboard_panels_rehydrate_lucide_icons() -> None:
    prompt_page = (DASHBOARD / "modules" / "prompt-page.js").read_text(encoding="utf-8")
    peek_panel = (DASHBOARD / "modules" / "peek-panel.js").read_text(encoding="utf-8")

    assert "lmHydrateIcons" in prompt_page
    assert "lmHydrateIcons" in peek_panel


def test_memory_transfer_controls_use_lucide_and_preview_before_import() -> None:
    index = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    memory_page = (DASHBOARD / "modules" / "memory-page.js").read_text(
        encoding="utf-8"
    )

    assert 'id="mem-export"' in index
    assert 'data-lucide="download"' in index
    assert 'id="mem-import"' in index
    assert 'data-lucide="upload"' in index
    assert 'accept=".json,.csv,application/json,text/csv"' in index
    assert '"memories/import"' in memory_page
    assert "dry_run: true" in memory_page
    assert "dry_run: false" in memory_page


def test_graph_dashboard_defaults_to_limited_overview_and_expanded_queries() -> None:
    graph_ui = (DASHBOARD / "graph-ui.js").read_text(encoding="utf-8")

    # 默认（ensureGraphScene / 空检索）走受限概览，不传 full_graph（#248）
    assert "fetchOverview(false)" in graph_ui
    # 「全量图谱」按钮可来回切换受限概览 ↔ 全量图（#248）
    assert 'fetchOverview(state.overviewMode !== "full")' in graph_ui
    assert 'params.set("full_graph", "true")' in graph_ui
    assert "limit_memories: 24" in graph_ui
    assert "limit_entries: 80" in graph_ui
    assert "limit_nodes: 80" in graph_ui
    assert "limit_edges: 120" in graph_ui


def test_large_graph_renderer_uses_lod_and_event_driven_frames() -> None:
    graph_2d = (DASHBOARD / "graph-2d.js").read_text(encoding="utf-8")
    graph_shared = (DASHBOARD / "graph-shared.js").read_text(encoding="utf-8")
    graph_renderer = (DASHBOARD / "graph-renderer.js").read_text(encoding="utf-8")
    graph_interaction = (DASHBOARD / "graph-interaction.js").read_text(
        encoding="utf-8"
    )

    assert "MASSIVE_EDGE_THRESHOLD: 12000" in graph_shared
    assert "Renderer.prototype.prepareGraph" in graph_renderer
    assert "this._communityBundles" in graph_renderer
    assert "this._structuralEdges" in graph_renderer
    assert "this._instantLayout = tier >= 2" in graph_2d
    assert "onRenderRequest" in graph_interaction
    assert "this._running = false" in graph_2d
    assert "Graph2D.prototype.getDiagnostics" in graph_2d


def test_graph_canvas_state_keeps_tooltip_inside_container() -> None:
    art = (DASHBOARD / "art-direction.css").read_text(encoding="utf-8")

    # art-direction 将画布提示移到左上角（top/left 16px），必须重置 styles.css
    # 的居中 translate，否则提示框会以「左上角 -50% 宽/高」定位被容器裁剪。
    assert ".graph-canvas-state" in art
    assert "transform: none" in art


def test_dashboard_hides_inactive_panels_from_keyboard_navigation() -> None:
    index = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    peek_panel = (DASHBOARD / "modules" / "peek-panel.js").read_text(
        encoding="utf-8"
    )

    assert 'id="modal-overlay"' not in index
    assert 'id="peek-panel" aria-hidden="true" inert' in index
    assert 'panel.removeAttribute("inert")' in peek_panel
    assert 'panel.setAttribute("aria-hidden", "false")' in peek_panel
    assert 'panel.setAttribute("inert", "")' in peek_panel
    assert 'panel.setAttribute("aria-hidden", "true")' in peek_panel

def test_dashboard_mobile_layout_keeps_graph_controls_usable() -> None:
    css = (DASHBOARD / "art-direction.css").read_text(encoding="utf-8")

    assert "@media (max-width: 768px)" in css
    assert "@media (max-width: 560px)" in css
    assert "#graph-session-filter" in css
    assert "flex: 1 1 110px" in css
    assert "grid-template-rows: auto minmax(240px, 1fr) auto auto" in css
    assert ".page-title" in css and "min-width: 0" in css

def test_dashboard_sources_have_no_legacy_appearance_cache_or_controls() -> None:
    sources = [
        DASHBOARD / "index.html",
        *sorted(DASHBOARD.glob("*.js")),
        *sorted(DASHBOARD.glob("*.css")),
        *sorted((DASHBOARD / "modules").glob("*.js")),
    ]
    markers = ("lmem_theme", "lmem_style", "theme-toggle", "appearance-dialog", "data-style")
    offenders = [
        f"{path.name}:{marker}"
        for path in sources
        for marker in markers
        if marker in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"遗留外观控制/缓存: {offenders}"

FIXTURE_JS = r"""
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const root = process.argv[2];
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const bundle = fs.readFileSync(path.join(root, 'assets', 'base.min.js'), 'utf8');
const scenario = JSON.parse(process.argv[3]);

const elements = [];
function textOf(el) { return el._text + el.children.map(textOf).join(''); }
function makeElement(tag, attrs = {}, text = '') {
  const el = {
    tagName: tag.toUpperCase(), attrs: { ...attrs }, children: [], _text: text,
    get textContent() { return textOf(this); },
    set textContent(value) { this._text = String(value); this.children = []; },
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null; },
    setAttribute(name, value) { this.attrs[name] = String(value); },
    removeAttribute(name) { delete this.attrs[name]; },
  };
  elements.push(el);
  return el;
}
const documentEl = makeElement('html', scenario.lang ? { lang: scenario.lang } : {});
const htmlLang = (html.match(/<html[^>]*\blang="([^"]+)"/) || [])[1];
if (htmlLang && !scenario.lang) documentEl.attrs.lang = htmlLang;
const rootEl = makeElement('#root');
const stack = [rootEl];
const tagPattern = new RegExp("<([a-zA-Z][a-zA-Z0-9-]*)([^>]*?)(\\/?)>|\\/([a-zA-Z][a-zA-Z0-9-]*)>|([^<]+)", "g");
for (const match of html.matchAll(tagPattern)) {
  const [, openTag, attrsText, selfClosing, closeTag, rawText] = match;
  if (openTag) {
    const attrs = {};
    for (const attr of attrsText.matchAll(/([a-zA-Z_:][\w:.-]*)(?:=["']([^"']*)["'])?/g)) {
      attrs[attr[1]] = attr[2] || '';
    }
    const el = makeElement(openTag, attrs);
    stack.at(-1).children.push(el);
    if (!selfClosing && !['input','meta','link','br','hr'].includes(openTag.toLowerCase())) stack.push(el);
  } else if (closeTag) {
    if (stack.length > 1 && stack.at(-1).tagName === closeTag.toUpperCase()) stack.pop();
  } else if (rawText.trim() && !['script','style'].includes(stack.at(-1).tagName.toLowerCase())) {
    stack.at(-1)._text += rawText.trim();
  }
}
function matches(el, selector) {
  if (!selector.startsWith('[') || !selector.endsWith(']')) return false;
  const body = selector.slice(1, -1);
  const eq = body.indexOf('=');
  const attr = eq === -1 ? body : body.slice(0, eq);
  if (!Object.prototype.hasOwnProperty.call(el.attrs, attr)) return false;
  if (eq === -1) return true;
  const expected = body.slice(eq + 1).replace(/^['"]|['"]$/g, '');
  return el.attrs[attr] === expected;
}
const listeners = {};
const document = {
  documentElement: documentEl,
  readyState: 'loading',
  querySelectorAll: selector => elements.filter(el => el !== rootEl && matches(el, selector)),
  addEventListener: (event, cb) => (listeners[event] ||= []).push(cb),
};
const storage = { ...scenario.storage };
class CustomEvent { constructor(type, detail) { this.type = type; this.detail = detail; } }
class URLSearchParams {
  constructor(query) {
    this.params = {};
    for (const [key, value] of new globalThis.URLSearchParams(query)) this.params[key] = value;
  }
  get(key) { return this.params[key] ?? null; }
}
const windowObj = {
  localStorage: { getItem: key => storage[key] ?? null, setItem: (key, value) => { storage[key] = String(value); } },
  navigator: { language: 'en-US' },
  location: { search: scenario.query || '' },
  addEventListener: (event, cb) => (listeners[event] ||= []).push(cb),
  dispatchEvent: event => (listeners[event.type] || []).forEach(cb => cb(event)),
};
if (scenario.locale) {
  windowObj.AstrBotPluginView = { getContext: () => ({ locale: scenario.locale }) };
}
if (scenario.lang) documentEl.attrs.lang = scenario.lang;
vm.runInNewContext(bundle, {
  window: windowObj, document, localStorage: windowObj.localStorage,
  navigator: windowObj.navigator, URLSearchParams, CustomEvent, console,
});
const keyText = key => document.querySelectorAll(`[data-i18n="${key}"]`)[0]?.textContent ?? null;
const placeholder = key => document.querySelectorAll(`[data-i18n-placeholder="${key}"]`)[0]?.attrs.placeholder ?? null;
if (scenario.fireDomReady) (listeners.DOMContentLoaded || []).forEach(cb => cb());
if (scenario.setLanguage) windowObj.setLanguage(scenario.setLanguage, { persist: true, source: 'user' });
process.stdout.write(JSON.stringify({
  lang: documentEl.attrs.lang || null,
  active: windowObj.getLanguage(),
  keys: {
    graph: keyText('nav.graph'), memory: keyText('nav.memory'), recall: keyText('nav.recall'),
    system: keyText('nav.system'), prompts: keyText('nav.prompts'), language: keyText('header.lang'),
    title: keyText('page.title'),
  },
  graphPlaceholder: placeholder('graph.queryPh'),
  storage,
}));"""


def _render_bundle(**scenario) -> dict[str, object]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不在 PATH，跳过 dashboard 首帧 bundle fixture")
    completed = subprocess.run(
        [node, "-e", FIXTURE_JS, "fixture", str(DASHBOARD), json.dumps(scenario)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(completed.stdout)


def test_dashboard_static_fallback_is_chinese_before_locale_detection() -> None:
    index = (DASHBOARD / "index.html").read_text(encoding="utf-8")

    assert '<html lang="zh-CN">' in index
    assert '<title data-i18n="page.title">记忆成长</title>' in index
    english_fallbacks = (
        "Knowledge Graph", "Recall Test", "Reset view", "Session ID",
        "Prompts", "Language", "System Overview", "Unsaved changes",
    )
    for fallback in english_fallbacks:
        assert fallback not in index, fallback
    assert 'src="./assets/base.min.js"' in index
    assert 'data-i18n-aria="nav.graph"' in index

    result = _render_bundle()
    # DOMContentLoaded has not fired: this is exactly the cold-cache first paint.
    assert result["lang"] == "zh-CN"
    assert result["keys"]["graph"] == "知识图谱"
    assert result["keys"]["memory"] == "记忆管理"
    assert result["keys"]["recall"] == "召回测试"
    assert result["keys"]["system"] == "系统概览"
    assert result["keys"]["prompts"] == "提示词管理"
    assert result["keys"]["language"] == "语言"
    assert result["keys"]["title"] == "记忆成长"
    assert result["active"] == "zh"

    assert result["graphPlaceholder"] == "输入人物、主题、事实或整句，查看召回到的图谱子图"
    assert "MutationObserver" not in (DASHBOARD / "i18n.js").read_text(encoding="utf-8")


def test_dashboard_head_bundle_defers_locale_until_dom_ready() -> None:
    # A host bridge with English locale must not flash English over Chinese.
    result = _render_bundle(locale="en-US")
    assert result["keys"]["graph"] == "知识图谱"

    result = _render_bundle(locale="en-US", fireDomReady=True)
    assert result["lang"] == "en"
    assert result["keys"]["graph"] == "Knowledge Graph"
    assert result["active"] == "en"

    # Switch back through the same public API used by the language menu.
    result = _render_bundle(locale="en-US", fireDomReady=True, setLanguage="zh")
    assert result["lang"] == "zh-CN"
    assert result["keys"]["graph"] == "知识图谱"
    assert result["active"] == "zh"
    assert result["storage"]["lmem_lang"] == "zh"


@pytest.mark.parametrize(
    ("locale", "expected_lang", "expected_nav"),
    [
        ("en-US", "en", "Knowledge Graph"),
        ("ru-RU", "ru", "Граф знаний"),
        ("ja-JP", "ja", "ナレッジグラフ"),
    ],
)
def test_dashboard_supported_locales_stay_consistent_after_detection(
    locale: str, expected_lang: str, expected_nav: str
) -> None:
    first = _render_bundle(locale=locale)
    assert first["keys"]["graph"] == "知识图谱"

    result = _render_bundle(locale=locale, fireDomReady=True)
    assert result["lang"] == expected_lang
    assert result["keys"]["graph"] == expected_nav
    assert result["active"] == expected_lang


def test_dashboard_legacy_english_cache_does_not_override_explicit_locale() -> None:
    # A stale cache from an older build must not force English when the URL
    # explicitly selects a supported locale.
    first = _render_bundle(storage={"lmem_lang": "en"}, query="?lang=ja")
    assert first["keys"]["graph"] == "知识图谱"

    result = _render_bundle(
        storage={"lmem_lang": "en"}, query="?lang=ja", fireDomReady=True
    )
    assert result["lang"] == "ja"
    assert result["keys"]["graph"] == "ナレッジグラフ"

    # Non-URL cached values remain a valid explicit user choice.
    result = _render_bundle(storage={"lmem_lang": "ru"}, fireDomReady=True)
    assert result["lang"] == "ru"
    assert result["keys"]["graph"] == "Граф знаний"

def test_dashboard_generated_bundle_contains_chinese_first_paint_logic() -> None:
    bundle = (DASHBOARD / "assets" / "base.min.js").read_text(encoding="utf-8")
    assert '"page.title":         { zh: "记忆成长", en: "记忆成长", ru: "记忆成长" }' in bundle
    assert "applyI18n();" in bundle
    assert 'source: "detect"' in bundle
    assert 'detected === "ja" ? "ja"' in bundle

    source = (DASHBOARD / "i18n.js").read_text(encoding="utf-8")
    assert "LivingMemory 控制台" not in source
    assert "LivingMemory Console" not in source
