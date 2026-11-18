from __future__ import annotations

import json
import hashlib
import importlib.util
import re
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


BUILD_PATH = Path(__file__).parents[1] / "build_views.py"
PLUGIN_ROOT = Path(__file__).parents[1] / "astrbot_plugin_zhiban"
BRIDGE_HASH = hashlib.sha256((PLUGIN_ROOT / "views" / "知伴" / "module_bridge.js").read_bytes()).hexdigest()[:12]
BRIDGE_FILENAME = f"module_bridge.{BRIDGE_HASH}.js"
spec = importlib.util.spec_from_file_location("zhiban_build_views_under_test", BUILD_PATH)
build_views_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = build_views_module
spec.loader.exec_module(build_views_module)


class BuildViewsTests(unittest.TestCase):
    def test_materializes_brand_and_each_module_logo(self):
        plugin_root = Path(__file__).parents[1] / "astrbot_plugin_zhiban"
        with tempfile.TemporaryDirectory() as temp:
            view_root = Path(temp) / "views" / "知伴"
            result = build_views_module.build_views(plugin_root, view_root=view_root)

            self.assertEqual(result["logos"], len(build_views_module.MODULES))
            self.assertEqual((view_root / "logo.png").read_bytes(), (plugin_root / "logo.png").read_bytes())
            for module in build_views_module.MODULES:
                source = plugin_root / "modules" / module["package"] / "logo.png"
                if not source.is_file():
                    source = plugin_root / build_views_module.LOGO_FALLBACKS[module["key"]]
                target = view_root / "logos" / f"{module['key']}{source.suffix.lower()}"
                self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_app_page_routes_match_generated_module_views(self):
        plugin_root = Path(__file__).parents[1] / "astrbot_plugin_zhiban"
        app_source = (plugin_root / "views" / "知伴" / "app.js").read_text(encoding="utf-8")
        for module in build_views_module.MODULE_UI_ROOTS:
            with self.subTest(module=module):
                self.assertRegex(
                    app_source,
                    rf'\{{ key: "{re.escape(module)}"[^\n]*page: "{re.escape(module)}"',
                )
                self.assertTrue(
                    (plugin_root / "views" / "知伴" / "modules" / module / "index.html").is_file()
                )

        for module in ("proactive", "eye", "qqprofile"):
            with self.subTest(message_pipeline_module=module):
                entry = next(line for line in app_source.splitlines() if f'key: "{module}"' in line)
                self.assertIn("help:", entry)
                self.assertNotIn("page:", entry)

    def test_five_primary_groups_keep_all_modules_reachable(self):
        app_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "app.js").read_text(encoding="utf-8")
        index_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(len(build_views_module.MODULES), 12)
        self.assertNotIn("filter", {item["key"] for item in build_views_module.MODULES})
        expected_groups = {
            "overview": "总览",
            "chat": "聊天系统",
            "memory": "记忆成长",
            "creative": "表达创作",
            "social": "QQ 社交",
        }
        for key, label in expected_groups.items():
            self.assertRegex(app_source, rf'\{{ key: "{key}", label: "{label}"')
        for module, group, group_key in (
            ("heart", "聊天系统", "chat"),
            ("search", "聊天系统", "chat"),
            ("parser", "聊天系统", "chat"),
            ("proactive", "聊天系统", "chat"),
            ("eye", "聊天系统", "chat"),
            ("memory", "记忆成长", "memory"),
            ("meme", "表达创作", "creative"),
            ("tts", "表达创作", "creative"),
            ("brush", "表达创作", "creative"),
            ("music", "表达创作", "creative"),
            ("qzone", "QQ 社交", "social"),
            ("qqprofile", "QQ 社交", "social"),
        ):
            entry = next(line for line in app_source.splitlines() if f'key: "{module}"' in line)
            self.assertIn(f'group: "{group}"', entry)
            self.assertIn(f'groupKey: "{group_key}"', entry)
        self.assertIn("renderGlobalOverview", app_source)
        self.assertIn("renderGlobalSettings", app_source)
        for key in ("chat_concurrency", "media_concurrency", "maintenance_concurrency", "media_queue_limit", "maintenance_queue_limit"):
            self.assertIn(f'["{key}"', app_source)
        self.assertIn("moduleStates.set(module.key", app_source)
        self.assertIn("await refreshStatus({ background: true });", app_source)
        self.assertIn('"今日成功回复"', app_source)
        self.assertIn("successful_responses", app_source)
        self.assertIn("Token 未统计", app_source)
        self.assertIn("if (item && item.label) items.push(item.label);", app_source)
        self.assertIn("function navigateModuleSubpage", app_source)
        self.assertIn("activeSubpageQuery = nextQuery;\n  persistRouteState();", app_source)
        self.assertIn("detail.accepted = accepted", app_source)
        self.assertIn("ui/global", app_source)
        self.assertIn("statusRequestInFlight", app_source)
        self.assertIn("runViewUpdate", app_source)
        self.assertIn('@view-transition { navigation: auto; }', index_source)
        self.assertIn('十二个模块，一个知伴', index_source)
        self.assertIn("createModuleFrameElement(", app_source)
        self.assertNotIn("navigatePage(new URL(`modules/${item.page}/index.html`", app_source)
        self.assertIn("frame.setAttribute(\"sandbox\", \"allow-scripts allow-forms allow-downloads\")", app_source)
        self.assertIn("frame.srcdoc = rewriteModuleDocument(source, pageUrl.href, item.key, route)", app_source)
        self.assertIn("fetchEpoch !== modulePageCache.epoch", app_source)
        self.assertNotIn("modulePageCache.epoch !== epoch", app_source)
        self.assertIn("modulePageCache.purgeExpired()", app_source)
        self.assertIn("visibilitychange", app_source)
        self.assertIn("navigator.connection?.saveData", app_source)
        self.assertIn("modulePrefetchController", app_source)
        self.assertIn("modulePrefetchTimer", app_source)
        self.assertIn("startModuleCacheMaintenance", app_source)
        self.assertIn("moduleCacheMaintenanceTimer", app_source)
        self.assertIn("syncTheme(context)", app_source)
        self.assertIn("modulePageCache.clear()", app_source)
        self.assertNotIn("const sdkUrl = new URL(\"/api/plugin/page/bridge-sdk.js\", location.origin)", app_source)
        self.assertIn("const declaredBridge = source.match", app_source)
        self.assertIn('const bridgeUrl = new URL("./module_bridge.js", document.baseURI)', app_source)
        self.assertIn('const declaredName = declaredUrl.pathname.split("/").pop()', app_source)
        self.assertIn('bridgeUrl.pathname = bridgeUrl.pathname.replace', app_source)
        self.assertIn('bridgeUrl.search = declaredUrl.search', app_source)
        self.assertIn("zhiban-panel-bootstrap", app_source)
        self.assertIn('documentElement.dataset.zhibanHostFrame=\"true\"', app_source)
        self.assertIn('data-module-key="${moduleKey}"', app_source)
        self.assertIn("pageUrl.searchParams.set(\"embedded\", \"frame\")", app_source)
        self.assertIn("pageUrl.searchParams.set(\"zhiban_panel\", \"1\")", app_source)
        self.assertIn("const assetToken = new URL(location.href).searchParams.get(\"asset_token\")", app_source)
        self.assertIn("if (assetToken) pageUrl.searchParams.set(\"asset_token\", assetToken)", app_source)
        self.assertIn("fetch(pageUrl.href", app_source)
        self.assertIn("zhiban:app-ready", app_source)
        self.assertIn("zhiban:app-error", app_source)
        self.assertIn("zhiban:bridge-ready", app_source)
        self.assertIn("activeModuleBridgeTimer", app_source)
        self.assertIn("activeModuleAppTimer", app_source)
        bridge_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "module_bridge.js").read_text(encoding="utf-8")
        host_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "host_bridge.js").read_text(encoding="utf-8")
        self.assertIn("MODULE_ROUTE_WHITELIST", host_source)
        self.assertIn("模块子页面不在允许范围", host_source)
        self.assertIn("RESERVED_ROUTE_QUERY_KEYS", host_source)
        self.assertIn("decodeModuleRoutePath", host_source)
        self.assertIn("modulePageRoot", bridge_source)
        self.assertIn("moduleRelativePath", bridge_source)
        self.assertIn("RESERVED_ROUTE_QUERY_KEYS", bridge_source)
        self.assertIn("zhiban-shell-style", bridge_source)
        self.assertIn("配置当前模块", bridge_source)
        self.assertIn("qzone", bridge_source)
        self.assertIn("sameNavigationTarget", bridge_source)
        self.assertIn("prefetchTarget", bridge_source)
        self.assertIn("@view-transition { navigation: auto; }", bridge_source)
        self.assertIn("STATUS_CACHE_TTL_MS", bridge_source)
        self.assertIn('id="primaryNav"', index_source)
        self.assertNotIn('data-page="system"', index_source)
        self.assertNotIn('key: "filter"', app_source)
        self.assertFalse((Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "logos" / "filter.svg").exists())

    def test_management_schema_generation_is_idempotent(self):
        root = Path(__file__).parents[1]
        schema_path = root / "astrbot_plugin_zhiban" / "_conf_schema.json"
        before = schema_path.read_bytes()
        subprocess.run([sys.executable, str(root / "build_schema.py")], check=True, stdout=subprocess.DEVNULL)
        self.assertEqual(schema_path.read_bytes(), before)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(
            list(schema["management"]["items"]),
            [
                "chat_concurrency",
                "media_concurrency",
                "maintenance_concurrency",
                "media_queue_limit",
                "maintenance_queue_limit",
                "queue_limit",
                "session_queue_limit",
                "wait_seconds",
                "menu_order",
            ],
        )

    def test_readmes_document_ai_policy_and_integrated_upstreams(self):
        root = Path(__file__).parents[1]
        readmes = (
            (root / "README.md").read_text(encoding="utf-8"),
            (root / "astrbot_plugin_zhiban" / "README.md").read_text(encoding="utf-8"),
        )
        for source in readmes:
            self.assertIn("GPT-6 Astra", source)
            self.assertIn("跨模块架构梳理、复杂调用链与生命周期/资源预算审阅", source)
            self.assertIn("DeepSeek V4.1 Flash", source)
            self.assertIn("回复防抖、Anysearch 联网搜索、缓存与调度等代码实现", source)
            self.assertIn("AstrBot 运行时使用部署者自行配置的 Provider，与上述开发工具相互独立", source)
            self.assertIn("3,438 项测试通过（根测试 215 + 图片模块 12 + 表情模块 1,542 + 记忆模块 1,187 + 联网搜索模块 28 + QQ 动态模块 454）", source)
            self.assertIn("OneBot v11", source)
            for repo in (
                "astrbot_plugin_angel_heart",
                "astrbot_plugin_anysearch",
                "astrbot_plugin_livingmemory",
                "astrbot_plugin_meme_manager",
                "AstrBot-breezetts",
                "astrbot_plugin_proactive_chat",
                "astrbot_plugin_angel_brush",
                "astrbot_plugin_listen_music",
                "astrbot_plugin_angel_eye",
                "astrbot_plugin_qzone_ultra",
                "astrbot_plugin_qqprofile",
            ):
                self.assertIn(repo, source)

    def test_chat_interaction_source_uses_zhiban_brand_and_green_theme(self):
        root = Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "modules" / "astrbot_plugin_angel_heart"
        source_root = root / "webui" / "src"
        panel = (source_root / "ChatConfigPanel.vue").read_text(encoding="utf-8")
        fields = (source_root / "fields.ts").read_text(encoding="utf-8")
        theme = (source_root / "theme.ts").read_text(encoding="utf-8")
        app = (source_root / "App.vue").read_text(encoding="utf-8")
        main = (source_root / "main.ts").read_text(encoding="utf-8")
        webui_index = (root / "webui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="brand">聊天互动</div>', panel)
        self.assertIn('<title>聊天互动</title>', webui_index)
        self.assertIn('<h2>对话运行状态</h2>', panel)
        self.assertNotIn('天使之心', panel)
        self.assertNotIn('AngelHeart', fields)
        self.assertNotIn('天使之心', fields)
        self.assertIn('知伴|小知', fields)
        self.assertIn("#2f6b4f", theme)
        self.assertIn("#f5f8f4", theme)
        self.assertIn("#f5f8f4", app)
        self.assertIn("document.documentElement.dataset.zhibanModule = 'heart'", main)
        self.assertIn("app.provide(themeKey, createThemeApi())", main)
        self.assertIn('新建对话策略', panel)
        self.assertIn('重命名对话策略', panel)
        self.assertIn('还没有对话策略', panel)
        self.assertNotIn('新建配置模板', panel)
        self.assertNotIn('模板名称', panel)
        self.assertNotIn('theme-toggle', panel)
        self.assertNotIn("toggleTheme", panel)
        build_root = root / "pages" / "chat-config"
        built_index = (build_root / "index.html").read_text(encoding="utf-8")
        self.assertIn("<title>聊天互动</title>", built_index)
        built_js_name = re.search(r'src="\./assets/(index-[^"]+\.js)"', built_index)
        built_css_name = re.search(r'href="\./assets/(style-[^"]+\.css)"', built_index)
        self.assertIsNotNone(built_js_name)
        self.assertIsNotNone(built_css_name)
        built_js = build_root / "assets" / built_js_name.group(1)
        built_css = build_root / "assets" / built_css_name.group(1)
        bundled = built_index + built_js.read_text(encoding="utf-8") + built_css.read_text(encoding="utf-8")
        self.assertNotIn("天使之心", bundled)
        self.assertNotIn("AngelHeart", bundled)
        self.assertIn("#2f6b4f", bundled)
        self.assertIn("聊天互动", bundled)
        self.assertIn("新建对话策略", bundled)
        self.assertNotIn("theme-toggle", bundled)

    def test_shell_and_qzone_do_not_use_page_local_navigation_or_short_bridge_timeouts(self):
        root = Path(__file__).parents[1] / "astrbot_plugin_zhiban"
        app = (root / "views" / "知伴" / "app.js").read_text(encoding="utf-8")
        bridge = (root / "views" / "知伴" / "module_bridge.js").read_text(encoding="utf-8")
        self.assertIn("document.addEventListener('click'", bridge)
        qzone = (
            root
            / "modules"
            / "astrbot_plugin_qzone_ultra"
            / "pages"
            / "qzone"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertNotIn("location.replace", app)
        self.assertNotIn("navigatePage", app)
        self.assertNotIn("BRIDGE_READY_TIMEOUT_MS", qzone)
        self.assertIn("await bridge.ready()", qzone)
        self.assertIn("installRuntimeErrorForwarding", bridge)
        self.assertIn("unhandledrejection", bridge)
        self.assertIn("benignRuntimeWarning", bridge)
        self.assertIn("ResizeObserver loop", bridge)

    def test_picture_creation_source_uses_zhiban_brand_and_host_theme(self):
        root = Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "modules" / "astrbot_plugin_angel_brush"
        source_root = root / "webui" / "src"
        panel = (source_root / "BrushPanel.vue").read_text(encoding="utf-8")
        theme = (source_root / "theme.ts").read_text(encoding="utf-8")
        app = (source_root / "App.vue").read_text(encoding="utf-8")
        main = (source_root / "main.ts").read_text(encoding="utf-8")
        webui_index = (root / "webui" / "index.html").read_text(encoding="utf-8")

        self.assertIn('class="brand">图片创作</div>', panel)
        self.assertIn('<title>图片创作</title>', webui_index)
        self.assertIn('<h2>图片创作</h2>', panel)
        self.assertIn('tab="生成图片"', panel)
        self.assertIn('tab="编辑图片"', panel)
        self.assertIn('生成图片 / 编辑图片', panel)
        self.assertNotIn('工具测试', panel)
        self.assertNotIn('angel_image_generate', panel)
        self.assertNotIn('angel_image_edit', panel)
        self.assertNotIn('Angel', panel)
        self.assertNotIn('天使', panel)

        self.assertIn("#2f6b4f", theme)
        self.assertIn("#f5f8f4", theme)
        self.assertIn("#f5f8f4", app)
        self.assertIn("document.documentElement.dataset.zhibanModule = 'brush'", main)
        self.assertIn("document.documentElement.dataset.theme = 'light'", main)
        self.assertIn("app.provide(themeKey, createThemeApi())", main)
        self.assertIn("bridge?.getContext?.()", app)
        self.assertIn("bridge?.onContext?.(syncHostTheme)", app)
        self.assertIn("theme.syncFromHost(context)", app)
        self.assertIn("context?.isDark", theme)
        self.assertNotIn('theme-toggle', panel)
        self.assertNotIn('toggleTheme', panel)
        self.assertNotIn('angel-brush-theme', theme)
        self.assertNotIn('localStorage', theme)
        self.assertNotIn('toggle:', theme)

    def test_picture_creation_bundle_matches_visible_brand_and_host_theme(self):
        root = Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "modules" / "astrbot_plugin_angel_brush"
        build_root = root / "pages" / "brush-config"
        built_index = (build_root / "index.html").read_text(encoding="utf-8")
        self.assertIn("<title>图片创作</title>", built_index)
        built_js_name = re.search(r'src="\./assets/(index-[^"]+\.js)"', built_index)
        built_css_name = re.search(r'href="\./assets/(style-[^"]+\.css)"', built_index)
        self.assertIsNotNone(built_js_name)
        self.assertIsNotNone(built_css_name)
        built_js = build_root / "assets" / built_js_name.group(1)
        built_css = build_root / "assets" / built_css_name.group(1)
        bundled = built_index + built_js.read_text(encoding="utf-8") + built_css.read_text(encoding="utf-8")

        self.assertNotIn('工具测试', bundled)
        self.assertNotIn('angel-brush-theme', bundled)
        self.assertNotIn('theme-toggle', bundled)
        self.assertIn('图片创作', bundled)
        self.assertIn('生成图片', bundled)
        self.assertIn('编辑图片', bundled)
        self.assertIn('#2f6b4f', bundled)
        self.assertIn('#f5f8f4', bundled)

    def test_qq_profile_source_keeps_status_signature_and_license(self):
        root = Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "modules" / "astrbot_plugin_qqprofile"
        source = (root / "main.py").read_text(encoding="utf-8")
        license_text = (root / "LICENSE").read_text(encoding="utf-8")
        self.assertIn('@filter.command("设置状态")', source)
        self.assertIn('@filter.command("设置签名")', source)
        self.assertIn("set_online_status", source)
        self.assertIn("set_self_longnick", source)
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", license_text)

    def test_bundled_pages_match_sources_except_required_bridge_shim(self):
        plugin_root = Path(__file__).parents[1] / "astrbot_plugin_zhiban"
        with tempfile.TemporaryDirectory() as temp:
            view_root = Path(temp) / "views" / "知伴"
            build_views_module.build_views(plugin_root, view_root=view_root)

            expected_paths = set()
            for module, source_parts in build_views_module.MODULE_UI_ROOTS.items():
                source_root = plugin_root / "modules" / Path(*source_parts)
                self.assertTrue(source_root.is_dir(), f"Missing upstream UI: {module}")
                for source in source_root.rglob("*"):
                    if not source.is_file():
                        continue
                    relative = source.relative_to(source_root)
                    expected_paths.add((Path(module) / relative).as_posix())
                    generated = view_root / "modules" / module / relative
                    self.assertTrue(generated.is_file(), f"Missing copied asset: {module}/{relative}")
                    if source.name.lower() == "index.html":
                        expected_source = source
                        depth = 2 + len(relative.parent.parts)
                        bridge_src = "../" * depth + BRIDGE_FILENAME
                        if module == "meme" and relative.as_posix() == "index.html":
                            expected_source = source_root / "a_manage" / "index.html"
                            bridge_src = "../../../" + BRIDGE_FILENAME
                        expected = build_views_module.prepare_module_ui_html(
                            expected_source.read_text(encoding="utf-8"),
                            source_parts[0],
                            module_bridge_src=bridge_src,
                        )
                        if module == "meme" and relative.as_posix() == "index.html":
                            expected = re.sub(
                                r"<head\b[^>]*>",
                                lambda match: match.group(0) + '<base href="./a_manage/">',
                                expected,
                                count=1,
                                flags=re.IGNORECASE,
                            )
                        self.assertEqual(generated.read_text(encoding="utf-8"), expected)
                    else:
                        self.assertEqual(generated.read_bytes(), source.read_bytes())

            generated_paths = {
                path.relative_to(view_root / "modules").as_posix()
                for path in (view_root / "modules").rglob("*")
                if path.is_file()
            }
            self.assertEqual(generated_paths, expected_paths)

    def test_generated_manifest_records_controlled_adaptations(self):
        plugin_root = Path(__file__).parents[1] / "astrbot_plugin_zhiban"
        with tempfile.TemporaryDirectory() as temp:
            view_root = Path(temp) / "views" / "知伴"
            result = build_views_module.build_views(plugin_root, view_root=view_root)
            manifest = __import__("json").loads((view_root / ".zhiban_generated_assets.json").read_text(encoding="utf-8"))
            adaptations = manifest["adaptations"]
            adapted_assets = adaptations["adapted_assets"]
            adapted_paths = {item["path"]: item for item in adapted_assets}

            self.assertEqual(manifest["schema_version"], 3)
            self.assertEqual(manifest["generated_files"], sorted(manifest["generated_files"]))
            self.assertEqual(len(manifest["generated_files"]), len(set(manifest["generated_files"])))
            self.assertEqual(len(manifest["generated_files"]), result["files"])
            self.assertTrue(adaptations["unchanged_non_html_assets"])
            self.assertEqual(
                adaptations["non_html_policy"],
                "only registered adaptations may differ; all other non-HTML resources "
                "are copied byte-for-byte",
            )
            self.assertEqual(adaptations["mode"], "authenticated SDK and module bridge injection")
            self.assertEqual(
                adaptations["theme"],
                "first-paint head CSS plus module_bridge.js controlled light-green overrides",
            )
            self.assertIn("reduced-motion", adaptations["motion"])

            expected_html = {
                path for path in manifest["generated_files"] if path.endswith("/index.html")
            }
            self.assertEqual(
                {path for path in adapted_paths if path.endswith("/index.html")},
                expected_html,
            )
            self.assertLessEqual(set(adapted_paths), set(manifest["generated_files"]))
            adapted_non_html = [item for item in adapted_assets if not item["path"].endswith("/index.html")]
            self.assertTrue(adapted_non_html)
            self.assertTrue(
                all(item["path"].startswith(("heart/", "qzone/")) for item in adapted_non_html)
            )
            qzone_asset = adapted_paths.get("qzone/app.js")
            self.assertIsNotNone(qzone_asset)
            self.assertIn("5s bridge-ready timeout", qzone_asset["reason"])
            self.assertEqual(len(qzone_asset["sha256"]), 64)

            for path, item in adapted_paths.items():
                with self.subTest(path=path):
                    self.assertEqual(
                        set(item),
                        {"path", "sha256", "reason", "source"},
                    )
                    self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
                    self.assertTrue(item["reason"])
                    self.assertTrue(item["source"])
                    generated = view_root / "modules" / path
                    self.assertEqual(
                        item["sha256"],
                        hashlib.sha256(generated.read_bytes()).hexdigest(),
                    )
                    if path.endswith("/index.html"):
                        self.assertIn(BRIDGE_FILENAME, generated.read_text(encoding="utf-8"))
                    else:
                        source = plugin_root / "modules" / item["source"]
                        self.assertEqual(item["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())

            for path in manifest["generated_files"]:
                if path in adapted_paths:
                    continue
                module, relative = path.split("/", 1)
                source_root = plugin_root / "modules" / Path(
                    *build_views_module.MODULE_UI_ROOTS[module]
                )
                if path.endswith("/index.html"):
                    self.assertIn(BRIDGE_FILENAME, (view_root / "modules" / path).read_text(encoding="utf-8"))
                else:
                    self.assertEqual(
                        (view_root / "modules" / path).read_bytes(),
                        (source_root / relative).read_bytes(),
                    )

    def test_adapted_non_html_assets_cannot_be_copied_without_manifest_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "modules" / "astrbot_plugin_angel_heart" / "pages" / "chat-config"
            source.mkdir(parents=True)
            (source / "index.html").write_text("<html><head></head></html>", encoding="utf-8")
            (source / "assets").mkdir()
            (source / "assets" / "unregistered.js").write_text("rebuilt", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing from the manifest"):
                build_views_module.build_views(
                    root,
                    view_root=root / "views" / "知伴",
                    mapping={
                        "heart": (
                            "astrbot_plugin_angel_heart",
                            "pages",
                            "chat-config",
                        )
                    },
                )

    def test_materializes_selected_page_with_sdk_adapter_before_app_scripts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "modules" / "astrbot_plugin_meme_manager" / "pages" / "app"
            source.mkdir(parents=True)
            (source / "index.html").write_text(
                '<html><head><script src="/api/plugin/page/bridge-sdk.js"></script>'
                '<script src="./app.js"></script></head></html>',
                encoding="utf-8",
            )
            (source / "app.js").write_text("window.testPage = true;", encoding="utf-8")
            view_root = root / "views" / "知伴"

            result = build_views_module.build_views(
                root,
                view_root=view_root,
                mapping={"meme": ("astrbot_plugin_meme_manager", "pages", "app")},
            )

            page = (view_root / "modules" / "meme" / "index.html").read_text(encoding="utf-8")
            self.assertEqual(result["files"], 2)
            self.assertEqual(page.count("/api/plugin/page/bridge-sdk.js"), 1)
            self.assertIn(BRIDGE_FILENAME, page)
            self.assertIn('data-module-key="meme"', page)
            self.assertLess(page.index("/api/plugin/page/bridge-sdk.js"), page.index(BRIDGE_FILENAME))
            self.assertLess(page.index(BRIDGE_FILENAME), page.index('src="./app.js"'))
            self.assertIn("window.testPage = true;", (view_root / "modules" / "meme" / "app.js").read_text(encoding="utf-8"))

    def test_navigation_ownership_is_single_and_fails_closed(self):
        module_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "module_bridge.js").read_text(encoding="utf-8")
        host_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "host_bridge.js").read_text(encoding="utf-8")
        ui_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "modules" / "astrbot_plugin_meme_manager" / "pages" / "app" / "shared" / "ui.js").read_text(encoding="utf-8")
        self.assertNotIn("stopImmediatePropagation()", module_source)
        app_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "app.js").read_text(encoding="utf-8")
        self.assertIn("navigateModuleSubpage may replace activeModuleFrame synchronously", app_source)
        self.assertIn('if (sequence !== moduleFrameSequence || item.key !== activeKey || activeView !== "workbench") return;', app_source)
        self.assertIn('if (!accepted) event.preventDefault();', app_source)
        self.assertNotIn("      event.preventDefault();\n      detail.accepted = accepted;", app_source)
        self.assertIn("document.addEventListener('click'", module_source)
        self.assertIn("data-zhiban-nav-bound", module_source)
        self.assertIn("message.token === state.appReadyToken", host_source)
        self.assertIn("!state.appReady && message.token === frame.dataset.appReadyToken", host_source)
        self.assertIn("zhibanModule.navigate(target);", ui_source)
        self.assertNotIn("if (!navigateModuleTarget(target)) {", ui_source)

    def test_failure_message_from_installed_emoji_navigation_is_regression_covered(self):
        host_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "host_bridge.js").read_text(encoding="utf-8")
        module_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "module_bridge.js").read_text(encoding="utf-8")
        self.assertIn("data-module-target values are module-relative", module_source)
        self.assertIn("const explicitModulePath = rawTarget.startsWith('#') || options.moduleRelative === true;", module_source)
        self.assertIn("const bases = explicitModulePath ? [moduleRoot] : [moduleRoot, pageRoot];", module_source)
        self.assertIn("const marker = `/modules/${moduleKey}/`;", host_source)
        self.assertIn('if (absolute) throw new Error("模块子页面不在允许范围");', host_source)
        self.assertIn('if (!allowed || !allowed.has(rawPath)) {', host_source)
        for route in ("a_manage/index.html", "catalog/index.html", "semantic/index.html", "settings/index.html"):
            self.assertIn(f'"{route}"', host_source)

    def test_installed_navigation_wire_format_is_module_relative_and_host_validated(self):
        host_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "host_bridge.js").read_text(encoding="utf-8")
        module_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "module_bridge.js").read_text(encoding="utf-8")
        self.assertIn("const wireRoute = { path: route.path, hash: route.hash, query: route.query };", module_source)
        self.assertIn("send('navigate', { module: moduleKey, token, ...wireRoute });", module_source)
        self.assertNotIn('if (!absolute && (/\\?/.test(rawTarget) || /#/.test(rawTarget))) {', host_source)
        self.assertIn('if (absolute && !/\\/modules\\/[^/?#]+\\//.test(decodeURIComponent(rawPathText))) {', host_source)
        self.assertIn('if (absolute) throw new Error("模块子页面不在允许范围");', host_source)
        self.assertIn('if (!allowed || !allowed.has(rawPath)) {', host_source)
    def test_nested_pages_resolve_bridge_from_signed_view_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "modules" / "astrbot_plugin_meme_manager" / "pages" / "app" / "a_manage"
            source.mkdir(parents=True)
            (source / "index.html").write_text("<html><head></head></html>", encoding="utf-8")
            view_root = root / "views" / "知伴"

            build_views_module.build_views(
                root,
                view_root=view_root,
                mapping={"meme": ("astrbot_plugin_meme_manager", "pages", "app")},
            )

            page = (view_root / "modules" / "meme" / "a_manage" / "index.html").read_text(encoding="utf-8")
            bridge_hash = BRIDGE_HASH
            self.assertIn(f'src="../../../{BRIDGE_FILENAME}?v={bridge_hash}" data-module-key="meme"', page)
            app_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "app.js").read_text(encoding="utf-8")
            self.assertIn("const declaredBridge = source.match", app_source)
            self.assertIn('const bridgeUrl = new URL("./module_bridge.js", document.baseURI)', app_source)
            self.assertIn('const declaredName = declaredUrl.pathname.split("/").pop()', app_source)
            self.assertIn('bridgeUrl.pathname = bridgeUrl.pathname.replace', app_source)
            self.assertIn('bridgeUrl.search = declaredUrl.search', app_source)
            self.assertTrue((view_root / f'module_bridge.{bridge_hash}.js').is_file())

    def test_previous_manifest_controls_stale_file_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "modules" / "pkg" / "pages" / "page"
            source.mkdir(parents=True)
            (source / "index.html").write_text("<html><head></head></html>", encoding="utf-8")
            view_root = root / "views" / "知伴"
            output = view_root / "modules" / "demo"
            output.mkdir(parents=True)
            stale = output / "removed.js"
            stale.write_text("stale", encoding="utf-8")
            view_root.mkdir(parents=True, exist_ok=True)
            (view_root / ".zhiban_generated_assets.json").write_text(
                '["demo/removed.js"]', encoding="utf-8"
            )

            build_views_module.build_views(
                root,
                view_root=view_root,
                mapping={"demo": ("pkg", "pages", "page")},
            )

            self.assertFalse(stale.exists())
            self.assertTrue((output / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()
