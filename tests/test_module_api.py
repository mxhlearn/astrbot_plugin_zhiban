from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1]))
from astrbot_plugin_zhiban.module_api import (
    dashboard_session_authorized,
    module_api_target,
)


class ModuleApiRouteTests(unittest.TestCase):
    def test_routes_only_to_known_bundled_module_namespaces(self):
        self.assertEqual(module_api_target("meme", "packs"), "meme_manager/packs")
        self.assertEqual(module_api_target("memory", "page/config"), "astrbot_plugin_livingmemory/page/config")
        self.assertEqual(module_api_target("qzone", "page/status"), "astrbot_plugin_qzone_ultra/page/status")
        self.assertEqual(module_api_target("qqprofile", "profile/status"), "astrbot_plugin_qqprofile/profile/status")
        self.assertIsNone(module_api_target("unknown", "status"))
        self.assertIsNone(module_api_target("filter", "status"))

    def test_rejects_path_traversal_and_url_injection(self):
        for path in ("../config", "a/../../secret", "https://evil.test", r"..\admin", "status?token=x", "/", "/packs", "packs/"):
            with self.subTest(path=path):
                self.assertIsNone(module_api_target("meme", path))

    def test_dashboard_identity_comes_from_validated_request_context(self):
        class RequestContext:
            def __init__(self, username):
                self.username = username

        self.assertTrue(dashboard_session_authorized(RequestContext("astrbot"), "api_key:"))
        self.assertFalse(dashboard_session_authorized(RequestContext(""), "api_key:"))
        self.assertFalse(dashboard_session_authorized(RequestContext(None), "api_key:"))
        self.assertFalse(dashboard_session_authorized(RequestContext("api_key:abc123"), "api_key:"))
        self.assertFalse(dashboard_session_authorized(object(), "api_key:"))


if __name__ == "__main__":
    unittest.main()
