from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SERVICE_PATH = Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "settings_service.py"
spec = importlib.util.spec_from_file_location("zhiban_settings_service_under_test", SERVICE_PATH)
service = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = service
spec.loader.exec_module(service)


SCHEMA = {
    "type": "object",
    "items": {
        "enabled": {"type": "bool", "default": True},
        "settings": {
            "type": "object",
            "items": {
                "api_key": {"type": "string", "default": ""},
                "limits": {
                    "type": "object",
                    "items": {"concurrency": {"type": "int", "default": 2, "slider": {"min": 1, "max": 8}}},
                },
                "keep_domains": {"type": "list", "default": []},
            },
        },
    },
}


class SettingsServiceTests(unittest.TestCase):
    def test_read_masks_secrets_and_reports_configured_state(self):
        result = service.read_module_config(
            SCHEMA,
            {"enabled": True, "settings": {"api_key": "hidden-value", "limits": {"concurrency": 3}}},
        )
        self.assertEqual(result["settings"]["api_key"], "")
        self.assertEqual(result["configured_secrets"], ["api_key"])
        self.assertEqual(result["settings"]["limits"]["concurrency"], 3)
        self.assertTrue(result["revision"])

    def test_patch_is_partial_preserves_unknown_values_and_keeps_blank_secret(self):
        current = {"enabled": True, "settings": {
            "api_key": "hidden-value", "limits": {"concurrency": 2}, "legacy": "keep"}}
        result = service.apply_module_patch(
            SCHEMA,
            current,
            expected_revision=service.config_revision(current),
            changes={"api_key": "", "limits": {"concurrency": 4}},
        )
        self.assertEqual(result["settings"]["api_key"], "hidden-value")
        self.assertEqual(result["settings"]["limits"]["concurrency"], 4)
        self.assertEqual(result["settings"]["legacy"], "keep")

    def test_secret_clear_requires_explicit_path(self):
        current = {"enabled": True, "settings": {"api_key": "hidden-value"}}
        result = service.apply_module_patch(
            SCHEMA,
            current,
            expected_revision=service.config_revision(current),
            changes={},
            clear_secrets=["api_key"],
        )
        self.assertEqual(result["settings"]["api_key"], "")

    def test_revision_conflict_and_invalid_changes_fail_closed(self):
        current = {"enabled": True, "settings": {"limits": {"concurrency": 2}}}
        with self.assertRaises(service.SettingsConflictError):
            service.apply_module_patch(SCHEMA, current, expected_revision="stale", changes={"limits": {"concurrency": 3}})
        with self.assertRaises(service.SettingsValidationError):
            service.apply_module_patch(
                SCHEMA,
                current,
                expected_revision=service.config_revision(current),
                changes={"unknown": True},
            )
        with self.assertRaises(service.SettingsValidationError):
            service.apply_module_patch(
                SCHEMA,
                current,
                expected_revision=service.config_revision(current),
                changes={"limits": {"concurrency": 99}},
            )

    def test_module_enable_toggle_can_be_saved_without_settings_changes(self):
        current = {"enabled": True, "settings": {}}
        result = service.apply_module_patch(
            SCHEMA,
            current,
            expected_revision=service.config_revision(current),
            changes={},
            enabled=False,
        )
        self.assertFalse(result["enabled"])


if __name__ == "__main__":
    unittest.main()
