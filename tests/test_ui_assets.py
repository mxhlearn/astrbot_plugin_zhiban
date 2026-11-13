"""Tests for the whitelist-backed module UI asset router."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


UI_ASSETS_PATH = Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "ui_assets.py"
spec = importlib.util.spec_from_file_location("zhiban_ui_assets_under_test", UI_ASSETS_PATH)
ui_assets = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ui_assets
spec.loader.exec_module(ui_assets)


class ModuleUiAssetTests(unittest.TestCase):
    def setUp(self):
        self.plugin_root = UI_ASSETS_PATH.parent

    def test_known_module_pages_and_nested_assets_resolve(self):
        for module in ui_assets.MODULE_UI_ROOTS:
            page = ui_assets.resolve_module_ui_asset(self.plugin_root, module, "index.html")
            self.assertTrue(page and page.is_file(), module)
        script = ui_assets.resolve_module_ui_asset(self.plugin_root, "heart", "assets/index-DP9jJ1z9.js")
        self.assertTrue(script and script.is_file())

    def test_unknown_modules_and_path_traversal_are_rejected(self):
        self.assertIsNone(ui_assets.resolve_module_ui_asset(self.plugin_root, "unknown", "index.html"))
        self.assertIsNone(ui_assets.resolve_module_ui_asset(self.plugin_root, "heart", "../../../../data/cmd_config.json"))
        self.assertIsNone(ui_assets.resolve_module_ui_asset(self.plugin_root, "heart", r"..\..\data\cmd_config.json"))

    def test_legacy_page_bridge_is_injected_before_app_scripts(self):
        source = '<html><head><script src="/api/plugin/page/bridge-sdk.js"></script><script src="./app.js"></script></head></html>'
        result = ui_assets.prepare_module_ui_html(source, "astrbot_plugin_angel_heart")
        self.assertNotIn("/api/plugin/page/bridge-sdk.js", result)
        self.assertLess(result.index('channel: CHANNEL'), result.index('src="./app.js"'))
        self.assertIn('"astrbot_plugin_angel_heart"', result)

    def test_nested_module_bridge_uses_post_message_contract_for_sandboxed_frames(self):
        script = ui_assets.legacy_bridge_script("astrbot_plugin_meme_manager")
        self.assertIn('const pluginName = "meme_manager"', script)
        self.assertIn('const CHANNEL = "astrbot-plugin-page"', script)
        self.assertIn('return `${pluginName}/${path}`', script)
        self.assertIn('event.source !== window.parent', script)
        self.assertIn('window.parent.postMessage(', script)
        self.assertIn('send("ready")', script)
        self.assertIn('makeRequest("api:get", { endpoint: makeEndpoint(endpoint), params })', script)
        self.assertIn('endpoint || "").replace(/^\\/+/, "") === "bridge/auth_token"', script)
        self.assertIn('makeRequest("api:post", { endpoint: makeEndpoint(endpoint), body })', script)
        self.assertIn('makeRequest("files:upload"', script)
        self.assertIn('makeRequest("files:download"', script)
        self.assertIn('makeRequest("sse:subscribe"', script)
        self.assertIn('makeRequest("sse:unsubscribe"', script)
        self.assertIn('message.kind === "sse_message"', script)
        self.assertIn('message.kind === "sse_state"', script)
        self.assertIn('return "*"', script)
        self.assertNotIn("window.parent.AstrBotPluginView", script)
        self.assertNotIn("fetch(", script)
        self.assertNotIn("credentials:", script)
        self.assertNotIn("{{", script)
        self.assertNotIn("}}", script)

    def test_other_module_api_names_remain_unchanged(self):
        script = ui_assets.legacy_bridge_script("astrbot_plugin_angel_heart")
        self.assertIn('const pluginName = "astrbot_plugin_angel_heart"', script)


if __name__ == "__main__":
    unittest.main()
