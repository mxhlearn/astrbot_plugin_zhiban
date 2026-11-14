from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path


BUILD_PATH = Path(__file__).parents[1] / "build_views.py"
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

    def test_five_primary_groups_keep_all_ten_modules_reachable(self):
        app_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "app.js").read_text(encoding="utf-8")
        index_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(len(build_views_module.MODULES), 10)
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
        self.assertIn("ui/global", app_source)
        self.assertIn("statusRequestInFlight", app_source)
        self.assertIn("runViewUpdate", app_source)
        self.assertIn('@view-transition { navigation: auto; }', index_source)
        self.assertIn("navigatePage(new URL(`modules/${item.page}/index.html`", app_source)
        bridge_source = (Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "views" / "知伴" / "module_bridge.js").read_text(encoding="utf-8")
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

    def test_readmes_document_models_and_integrated_upstreams(self):
        root = Path(__file__).parents[1]
        readmes = (
            (root / "README.md").read_text(encoding="utf-8"),
            (root / "astrbot_plugin_zhiban" / "README.md").read_text(encoding="utf-8"),
        )
        for source in readmes:
            self.assertIn("GPT-6 Astra", source)
            self.assertIn("DeepSeek V4.1 Flash", source)
            self.assertIn("OneBot v11", source)
            for repo in (
                "astrbot_plugin_angel_heart",
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
                        depth = 2 + len(relative.parent.parts)
                        bridge_src = "../" * depth + "module_bridge.js"
                        expected = build_views_module.prepare_module_ui_html(
                            source.read_text(encoding="utf-8"),
                            source_parts[0],
                            module_bridge_src=bridge_src,
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
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(len(manifest["generated_files"]), result["files"])
            self.assertTrue(manifest["adaptations"]["unchanged_non_html_assets"])
            self.assertEqual(manifest["adaptations"]["mode"], "authenticated SDK and module bridge injection")
            self.assertIn("reduced-motion", manifest["adaptations"]["motion"])
            for path in manifest["generated_files"]:
                if path.endswith("/index.html"):
                    page = (view_root / "modules" / path).read_text(encoding="utf-8")
                    self.assertIn("module_bridge.js", page)

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
            self.assertIn("module_bridge.js", page)
            self.assertIn('data-module-key="meme"', page)
            self.assertLess(page.index("/api/plugin/page/bridge-sdk.js"), page.index("module_bridge.js"))
            self.assertLess(page.index("module_bridge.js"), page.index('src="./app.js"'))
            self.assertIn("window.testPage = true;", (view_root / "modules" / "meme" / "app.js").read_text(encoding="utf-8"))

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
            self.assertIn('src="../../../module_bridge.js" data-module-key="meme"', page)

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
