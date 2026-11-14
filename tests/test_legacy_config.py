from __future__ import annotations

import importlib.util
import copy
import json
import sys
from pathlib import Path

import pytest


LEGACY_CONFIG_PATH = Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "legacy_config.py"
spec = importlib.util.spec_from_file_location("zhiban_legacy_config_under_test", LEGACY_CONFIG_PATH)
legacy_config = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = legacy_config
spec.loader.exec_module(legacy_config)

HEART_SCHEMA = {
    "heart": {
        "type": "object",
        "items": {
            "enabled": {"type": "bool", "default": True},
            "settings": {
                "type": "object",
                "items": {
                    "analyzer_model": {"type": "string", "default": ""},
                    "timing": {
                        "type": "object",
                        "items": {"cooldown": {"type": "int", "default": 10}},
                    },
                    "groups": {"type": "list", "default": []},
                },
            },
        },
    }
}
HEART_DEFAULTS = {"analyzer_model": "", "timing": {"cooldown": 10}, "groups": []}


class HostConfig(dict):
    def __init__(self, values, tmp_path, *, first_deploy=False, schema=None):
        super().__init__(copy.deepcopy(values))
        self.first_deploy = first_deploy
        self.schema = schema
        self.config_path = str(tmp_path / "astrbot_plugin_zhiban_config.json")
        self.save_calls = 0
        self.fail_save = False

    def save_config(self):
        self.save_calls += 1
        if self.fail_save:
            raise OSError("simulated config write failure")
        Path(self.config_path).write_text(json.dumps(self), encoding="utf-8")


def write_legacy(tmp_path, key, settings):
    path = tmp_path / legacy_config.LEGACY_CONFIGS[key]
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def migration_state(tmp_path):
    return json.loads(
        (tmp_path / legacy_config._MIGRATION_STATE_NAME).read_text(encoding="utf-8")
    )


def test_default_filled_first_deploy_imports_existing_legacy_settings(tmp_path):
    legacy = {"analyzer_model": "legacy-chat", "timing": {"cooldown": 25}}
    source = write_legacy(tmp_path, "heart", legacy)
    before = source.read_bytes()
    config = HostConfig(
        {"heart": {"enabled": False, "settings": HEART_DEFAULTS}},
        tmp_path, first_deploy=True, schema=HEART_SCHEMA,
    )

    assert legacy_config.import_legacy_settings(config, tmp_path) == ["heart"]

    assert config["heart"] == {"enabled": False, "settings": legacy}
    assert config.save_calls == 1
    assert json.loads(Path(config.config_path).read_text())["heart"]["settings"] == legacy
    assert source.read_bytes() == before
    assert migration_state(tmp_path)["modules"]["heart"]["outcome"] == "imported"


@pytest.mark.parametrize("edited_settings", [{}, HEART_DEFAULTS, {"analyzer_model": "edited"}])
def test_recorded_migration_preserves_later_edits_and_resets(tmp_path, edited_settings):
    write_legacy(tmp_path, "heart", {"analyzer_model": "legacy-chat"})
    config = HostConfig(
        {"heart": {"enabled": True, "settings": HEART_DEFAULTS}},
        tmp_path, first_deploy=True, schema=HEART_SCHEMA,
    )
    assert legacy_config.import_legacy_settings(config, tmp_path) == ["heart"]
    # Even a reused first-deploy object must not import twice after a user edit.
    config["heart"]["settings"] = copy.deepcopy(edited_settings)
    write_legacy(tmp_path, "heart", {"analyzer_model": "changed-upstream"})

    assert legacy_config.import_legacy_settings(config, tmp_path) == []
    assert config["heart"]["settings"] == edited_settings
    assert config.save_calls == 1


@pytest.mark.parametrize("settings", [HEART_DEFAULTS, {}, {"analyzer_model": "saved-chat"}])
def test_saved_host_values_are_authoritative_even_without_migration_record(tmp_path, settings):
    write_legacy(tmp_path, "heart", {"analyzer_model": "legacy-chat"})
    config = HostConfig(
        {"heart": {"enabled": True, "settings": settings}},
        tmp_path, schema=HEART_SCHEMA,
    )

    assert legacy_config.import_legacy_settings(config, tmp_path) == []
    assert config["heart"]["settings"] == settings
    assert config.save_calls == 0
    assert migration_state(tmp_path)["modules"]["heart"]["outcome"] == "preserved"


def test_conflicting_explicit_values_on_first_deploy_are_preserved(tmp_path):
    write_legacy(tmp_path, "heart", {"analyzer_model": "legacy-chat"})
    settings = {**copy.deepcopy(HEART_DEFAULTS), "analyzer_model": "chosen-chat"}
    config = HostConfig(
        {"heart": {"enabled": True, "settings": settings}},
        tmp_path, first_deploy=True, schema=HEART_SCHEMA,
    )

    assert legacy_config.import_legacy_settings(config, tmp_path) == []
    assert config["heart"]["settings"] == settings
    # Recording the explicit choice prevents a subsequent reset from importing.
    config["heart"]["settings"] = copy.deepcopy(HEART_DEFAULTS)
    assert legacy_config.import_legacy_settings(config, tmp_path) == []
    assert config["heart"]["settings"] == HEART_DEFAULTS


def test_first_deploy_with_no_schema_does_not_guess_nonempty_defaults(tmp_path):
    write_legacy(tmp_path, "heart", {"analyzer_model": "legacy-chat"})
    config = HostConfig(
        {"heart": {"settings": HEART_DEFAULTS}}, tmp_path, first_deploy=True,
    )

    assert legacy_config.import_legacy_settings(config, tmp_path) == []
    assert config["heart"]["settings"] == HEART_DEFAULTS


def test_failed_parent_save_rolls_back_and_does_not_record_migration(tmp_path):
    write_legacy(tmp_path, "heart", {"analyzer_model": "legacy-chat"})
    config = HostConfig(
        {"heart": {"enabled": True, "settings": HEART_DEFAULTS}},
        tmp_path, first_deploy=True, schema=HEART_SCHEMA,
    )
    config.fail_save = True

    with pytest.raises(OSError, match="simulated"):
        legacy_config.import_legacy_settings(config, tmp_path)

    assert config["heart"]["settings"] == HEART_DEFAULTS
    assert not (tmp_path / legacy_config._MIGRATION_STATE_NAME).exists()
    config.fail_save = False
    assert legacy_config.import_legacy_settings(config, tmp_path) == ["heart"]


def test_corrupt_migration_record_does_not_allow_a_new_import(tmp_path):
    write_legacy(tmp_path, "heart", {"analyzer_model": "legacy-chat"})
    (tmp_path / legacy_config._MIGRATION_STATE_NAME).write_text("{broken", encoding="utf-8")
    config = HostConfig(
        {"heart": {"settings": HEART_DEFAULTS}},
        tmp_path, first_deploy=True, schema=HEART_SCHEMA,
    )

    with pytest.raises(ValueError, match="迁移记录"):
        legacy_config.import_legacy_settings(config, tmp_path)
    assert config["heart"]["settings"] == HEART_DEFAULTS
    assert config.save_calls == 0


def test_angel_memory_settings_are_replaced_by_livingmemory_settings(tmp_path):
    (tmp_path / "astrbot_plugin_livingmemory_config.json").write_text(
        json.dumps({"bot_language": "zh", "provider_settings": {"llm_provider_id": "local"}}),
        encoding="utf-8",
    )
    config = {"memory": {"enabled": True, "settings": {"provider_id": "angel"}}}

    imported = legacy_config.import_legacy_settings(config, tmp_path)

    assert imported == ["memory"]
    assert config["memory"]["enabled"] is True
    assert config["memory"]["settings"] == {
        "bot_language": "zh",
        "provider_settings": {"llm_provider_id": "local"},
    }


def test_existing_livingmemory_settings_are_not_overwritten(tmp_path):
    (tmp_path / "astrbot_plugin_livingmemory_config.json").write_text(
        json.dumps({"bot_language": "en"}), encoding="utf-8"
    )
    config = {"memory": {"enabled": True, "settings": {"bot_language": "ja"}}}

    imported = legacy_config.import_legacy_settings(config, tmp_path)

    assert imported == []
    assert config["memory"]["settings"]["bot_language"] == "ja"


def test_existing_host_angel_memory_config_still_converts(tmp_path):
    living = {"bot_language": "zh", "provider_settings": {"llm_provider_id": "local"}}
    write_legacy(tmp_path, "memory", living)
    config = HostConfig(
        {"memory": {"enabled": True, "settings": {"provider_id": "angel"}}}, tmp_path,
    )

    assert legacy_config.import_legacy_settings(config, tmp_path) == ["memory"]
    assert config["memory"]["settings"] == living
    assert config.save_calls == 1


def test_missing_livingmemory_source_clears_only_old_angel_settings_once(tmp_path):
    config = HostConfig(
        {"memory": {"enabled": False, "settings": {"provider_id": "angel"}}}, tmp_path,
    )

    assert legacy_config.import_legacy_settings(config, tmp_path) == []
    assert config["memory"] == {"enabled": False, "settings": {}}
    assert config.save_calls == 1
    write_legacy(tmp_path, "memory", {"bot_language": "en"})
    assert legacy_config.import_legacy_settings(config, tmp_path) == []
    assert config["memory"]["settings"] == {}


def test_proactive_import_keeps_business_settings_but_disables_auxiliary_services(tmp_path):
    source = {
        "friend_settings": {"enable": True},
        "group_settings": {"enable": False},
        "web_admin": {"enabled": True},
        "telemetry_config": {"enabled": True},
        "notification_settings": {"enabled": True},
    }
    path = write_legacy(tmp_path, "proactive", source)
    config = {"proactive": {"settings": {}}}

    assert legacy_config.import_legacy_settings(config, tmp_path) == ["proactive"]
    imported = config["proactive"]["settings"]
    assert imported["friend_settings"] == {"enable": True}
    assert imported["group_settings"] == {"enable": False}
    for group in ("web_admin", "telemetry_config", "notification_settings"):
        assert imported[group]["enabled"] is False
    assert json.loads(path.read_text()) == source


def test_installed_livingmemory_and_qzone_settings_import_without_disabling_modules(tmp_path):
    living = {
        "bot_language": "zh",
        "provider_settings": {"embedding_provider_id": "test-embedding", "llm_provider_id": "test-chat"},
        "access_control": {"allowed_ids": "test-user", "whitelist_enabled": True},
        "recall_engine": {"top_k": 7},
        "backup_settings": {"enabled": True},
    }
    qzone = {
        "cookies_str": "test-cookie-not-real",
        "llm": {"provider_id": "test-qzone-chat"},
        "manage_group": "test-group",
        "auto_start_daemon": True,
        "daemon_port": 4101,
        "life_publish": {"enabled": True},
        "news": {"enabled": False},
    }
    memory_path = write_legacy(tmp_path, "memory", living)
    qzone_path = tmp_path / "astrbot_plugin_qzone_config.json"
    qzone_path.write_text(json.dumps(qzone), encoding="utf-8")
    before = {path: path.read_bytes() for path in (memory_path, qzone_path)}
    config = HostConfig(
        {key: {"enabled": True, "settings": {}} for key in ("memory", "qzone")},
        tmp_path, first_deploy=True,
    )

    assert legacy_config.import_legacy_settings(config, tmp_path) == ["memory", "qzone"]
    assert config["memory"] == {"enabled": True, "settings": living}
    assert config["qzone"] == {"enabled": True, "settings": qzone}
    assert config.save_calls == 1
    for path, contents in before.items():
        assert path.read_bytes() == contents
    records = migration_state(tmp_path)["modules"]
    assert records["memory"]["source"] == "astrbot_plugin_livingmemory_config.json"
    assert records["qzone"]["source"] == "astrbot_plugin_qzone_config.json"
    assert "test-cookie-not-real" not in json.dumps(records)
    assert "test-embedding" not in json.dumps(records)


def test_qqprofile_settings_import_and_preserve_existing_host_values(tmp_path):
    legacy = {"sync_name": True}
    write_legacy(tmp_path, "qqprofile", legacy)
    schema = {
        "qqprofile": {
            "items": {
                "settings": {
                    "type": "object",
                    "items": {"sync_name": {"type": "bool", "default": False}},
                }
            }
        }
    }
    config = HostConfig(
        {"qqprofile": {"enabled": True, "settings": {"sync_name": False}}},
        tmp_path, first_deploy=True, schema=schema,
    )

    assert legacy_config.import_legacy_settings(config, tmp_path) == ["qqprofile"]
    assert config["qqprofile"] == {"enabled": True, "settings": legacy}
    assert migration_state(tmp_path)["modules"]["qqprofile"]["source"] == "astrbot_plugin_qqprofile_config.json"

    config["qqprofile"]["settings"]["sync_name"] = False
    assert legacy_config.import_legacy_settings(config, tmp_path) == []
    assert config["qqprofile"]["settings"]["sync_name"] is False


def test_qzone_current_filename_takes_priority_over_older_ultra_snapshot(tmp_path):
    write_legacy(tmp_path, "qzone", {"cookies_str": "current-test-cookie"})
    (tmp_path / "astrbot_plugin_qzone_ultra_config.json").write_text(
        json.dumps({"cookies_str": "stale-test-cookie"}), encoding="utf-8",
    )
    config = {"qzone": {"settings": {}}}

    assert legacy_config.import_legacy_settings(config, tmp_path) == ["qzone"]
    assert config["qzone"]["settings"]["cookies_str"] == "current-test-cookie"


def test_qzone_ultra_filename_remains_supported_when_current_file_is_absent(tmp_path):
    (tmp_path / "astrbot_plugin_qzone_ultra_config.json").write_text(
        json.dumps({"timeout": 45}), encoding="utf-8",
    )
    config = {"qzone": {"settings": {}}}

    assert legacy_config.import_legacy_settings(config, tmp_path) == ["qzone"]
    assert config["qzone"]["settings"] == {"timeout": 45}
    assert migration_state(tmp_path)["modules"]["qzone"]["source"] == "astrbot_plugin_qzone_ultra_config.json"


def test_qzone_invalid_current_file_does_not_silently_restore_stale_ultra_settings(tmp_path):
    (tmp_path / "astrbot_plugin_qzone_config.json").write_text("{broken", encoding="utf-8")
    (tmp_path / "astrbot_plugin_qzone_ultra_config.json").write_text(
        json.dumps({"cookies_str": "stale-test-cookie"}), encoding="utf-8",
    )
    config = {"qzone": {"settings": {}}}

    assert legacy_config.import_legacy_settings(config, tmp_path) == []
    assert config["qzone"]["settings"] == {}
    assert migration_state(tmp_path)["modules"]["qzone"]["outcome"] == "unavailable"


def test_recorded_ultra_migration_prevents_reimport_after_filename_change(tmp_path):
    (tmp_path / "astrbot_plugin_qzone_ultra_config.json").write_text(
        json.dumps({"timeout": 45}), encoding="utf-8",
    )
    config = {"qzone": {"settings": {}}}
    assert legacy_config.import_legacy_settings(config, tmp_path) == ["qzone"]
    config["qzone"]["settings"] = {}
    write_legacy(tmp_path, "qzone", {"timeout": 90})

    assert legacy_config.import_legacy_settings(config, tmp_path) == []
    assert config["qzone"]["settings"] == {}


def test_angelmemory_source_file_is_never_a_fallback_for_missing_livingmemory(tmp_path):
    old_path = tmp_path / "astrbot_plugin_angel_memory_config.json"
    old_path.write_text(json.dumps({"provider_id": "old-angel"}), encoding="utf-8")
    before = old_path.read_bytes()
    config = {"memory": {"enabled": True, "settings": {}}}

    assert legacy_config.import_legacy_settings(config, tmp_path) == []
    assert config["memory"] == {"enabled": True, "settings": {}}
    assert old_path.read_bytes() == before


@pytest.mark.parametrize("invalid_source", [{"provider_id": "old-angel"}, ["invalid-config"]])
def test_invalid_livingmemory_source_does_not_restore_old_angel_settings(tmp_path, invalid_source):
    write_legacy(tmp_path, "memory", invalid_source)
    config = {"memory": {"enabled": True, "settings": {"provider_id": "old-angel"}}}

    assert legacy_config.import_legacy_settings(config, tmp_path) == []
    assert config["memory"] == {"enabled": True, "settings": {}}
    assert migration_state(tmp_path)["modules"]["memory"]["outcome"] == "invalid"


def test_old_angel_migration_record_does_not_block_livingmemory_conversion(tmp_path):
    record = {"version": 1, "modules": {"memory": {
        "source": "astrbot_plugin_angel_memory_config.json", "outcome": "imported",
    }}}
    (tmp_path / legacy_config._MIGRATION_STATE_NAME).write_text(json.dumps(record), encoding="utf-8")
    living = {"provider_settings": {"llm_provider_id": "living-test-chat"}}
    write_legacy(tmp_path, "memory", living)
    config = {"memory": {"settings": {"provider_id": "old-angel"}}}

    assert legacy_config.import_legacy_settings(config, tmp_path) == ["memory"]
    assert config["memory"]["settings"] == living
    assert migration_state(tmp_path)["modules"]["memory"]["source"] == "astrbot_plugin_livingmemory_config.json"


@pytest.mark.parametrize("failure_point", ["fsync", "replace"])
def test_sidecar_write_failure_rolls_back_parent_and_preserves_old_record(tmp_path, monkeypatch, failure_point):
    write_legacy(tmp_path, "heart", {"analyzer_model": "legacy-chat"})
    state_path = tmp_path / legacy_config._MIGRATION_STATE_NAME
    old_state = {"version": 1, "modules": {"filter": {
        "source": "astrbot_plugin_link_filter_config.json", "outcome": "preserved",
    }}}
    state_path.write_text(json.dumps(old_state), encoding="utf-8")
    old_bytes = state_path.read_bytes()
    config = HostConfig(
        {"heart": {"enabled": True, "settings": HEART_DEFAULTS}},
        tmp_path, first_deploy=True, schema=HEART_SCHEMA,
    )
    config.save_config()

    def fail(*args, **kwargs):
        raise OSError("simulated sidecar failure")

    monkeypatch.setattr(legacy_config.os, failure_point, fail)
    with pytest.raises(OSError, match="已恢复原配置"):
        legacy_config.import_legacy_settings(config, tmp_path)

    assert config["heart"]["settings"] == HEART_DEFAULTS
    assert json.loads(Path(config.config_path).read_text())["heart"]["settings"] == HEART_DEFAULTS
    assert state_path.read_bytes() == old_bytes
    assert list(tmp_path.glob(legacy_config._MIGRATION_STATE_NAME + ".*.tmp")) == []
    assert config.save_calls == 3  # baseline, import, compensating rollback


def test_sidecar_failure_restores_plain_dict_without_persistence_hook(tmp_path, monkeypatch):
    write_legacy(tmp_path, "qzone", {"timeout": 45})
    config = {"qzone": {"enabled": True, "settings": {}}}

    def fail(*args, **kwargs):
        raise OSError("simulated sidecar failure")

    monkeypatch.setattr(legacy_config.os, "replace", fail)
    with pytest.raises(OSError, match="已恢复原配置"):
        legacy_config.import_legacy_settings(config, tmp_path)

    assert config == {"qzone": {"enabled": True, "settings": {}}}
    assert not (tmp_path / legacy_config._MIGRATION_STATE_NAME).exists()


def test_failed_compensating_save_reports_failure_and_retains_last_saved_values(tmp_path, monkeypatch):
    living = {"provider_settings": {"llm_provider_id": "living-test-chat"}}
    write_legacy(tmp_path, "memory", living)
    config = HostConfig({"memory": {"enabled": True, "settings": {}}}, tmp_path, first_deploy=True)
    original_save = config.save_config

    def fail_rollback():
        if config.save_calls:
            raise OSError("simulated rollback failure")
        original_save()

    def fail_sidecar(*args, **kwargs):
        raise OSError("simulated sidecar failure")

    monkeypatch.setattr(config, "save_config", fail_rollback)
    monkeypatch.setattr(legacy_config.os, "replace", fail_sidecar)
    with pytest.raises(RuntimeError, match="配置回滚也失败"):
        legacy_config.import_legacy_settings(config, tmp_path)

    assert config["memory"]["settings"] == living
    assert json.loads(Path(config.config_path).read_text())["memory"]["settings"] == living
    assert not (tmp_path / legacy_config._MIGRATION_STATE_NAME).exists()


@pytest.mark.parametrize("record", [{}, {"source": "x", "outcome": []}, {"source": "x", "outcome": "unknown"}])
def test_malformed_sidecar_module_records_fail_closed(tmp_path, record):
    state = {"version": 1, "modules": {"memory": record}}
    (tmp_path / legacy_config._MIGRATION_STATE_NAME).write_text(json.dumps(state), encoding="utf-8")
    write_legacy(tmp_path, "memory", {"bot_language": "en"})
    config = {"memory": {"settings": {}}}

    with pytest.raises(ValueError, match="迁移记录格式"):
        legacy_config.import_legacy_settings(config, tmp_path)
    assert config == {"memory": {"settings": {}}}
