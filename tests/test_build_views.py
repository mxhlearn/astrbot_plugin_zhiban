from __future__ import annotations

import importlib.util
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
                        expected = build_views_module.prepare_module_ui_html(
                            source.read_text(encoding="utf-8"), source_parts[0]
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

    def test_materializes_selected_page_and_installs_authenticated_legacy_bridge(self):
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
            self.assertIn('const pluginName = "meme_manager"', page)
            self.assertIn('channel: CHANNEL', page)
            self.assertLess(page.index("send(\"ready\")"), page.index('src="./app.js"'))
            self.assertIn("window.testPage = true;", (view_root / "modules" / "meme" / "app.js").read_text(encoding="utf-8"))

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
