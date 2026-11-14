import copy
import json
import os
import tempfile
from pathlib import Path

LEGACY_CONFIGS = {
    'heart': 'astrbot_plugin_angel_heart_config.json',
    'memory': 'astrbot_plugin_livingmemory_config.json',
    'eye': 'astrbot_plugin_angel_eye_config.json',
    'brush': 'astrbot_plugin_angel_brush_config.json',
    'tts': 'astrbot_plugin_breeze_tts_config.json',
    'meme': 'astrbot_plugin_meme_manager_config.json',
    'music': 'astrbot_plugin_listen_music_config.json',
    'proactive': 'astrbot_plugin_proactive_chat_config.json',
    'qzone': 'astrbot_plugin_qzone_config.json',
    'qqprofile': 'astrbot_plugin_qqprofile_config.json',
}

# The installed standalone copy uses qzone; older server snapshots used ultra.
# Never add AngelMemory as a memory source: its settings belong to another engine.
_LEGACY_CONFIG_ALIASES = {
    'qzone': ('astrbot_plugin_qzone_ultra_config.json',),
}

_ANGEL_MEMORY_KEYS = {
    'provider_id', 'retrieval', 'conversation_scope_map', 'group_domain_map',
    'group_knowledge_map', 'memory_behavior', 'enable_soul_system', 'note_assistant',
}
_LIVING_MEMORY_KEYS = {
    'bot_language', 'access_control', 'provider_settings', 'session_manager',
    'recall_engine', 'importance_decay', 'fusion_strategy', 'filtering_settings',
    'reflection_engine', 'agent_tools', 'graph_memory', 'migration_settings',
    'index_rebuild_settings', 'backup_settings', 'forgetting_agent',
    'memory_dedup', 'memory_consolidation',
}

_MIGRATION_STATE_NAME = 'astrbot_plugin_zhiban_legacy_migration.json'
_MIGRATION_VERSION = 1
_MIGRATION_OUTCOMES = {'imported', 'preserved', 'unavailable', 'invalid'}
_DEFAULT_VALUES = {
    'string': '', 'text': '', 'int': 0, 'float': 0.0, 'bool': False,
    'list': [], 'template_list': [], 'dict': {},
}


def _schema_defaults(schema):
    """Mirror the host's default expansion without constructing an AstrBotConfig."""
    result = {}
    for key, item in schema.items():
        if item.get('type') == 'object':
            result[key] = _schema_defaults(item.get('items', {}))
        else:
            result[key] = copy.deepcopy(
                item.get('default', _DEFAULT_VALUES.get(item.get('type')))
            )
    return result


def _is_untouched_first_deploy(config, key, settings):
    if getattr(config, 'first_deploy', False) is not True:
        return False
    schema = getattr(config, 'schema', None)
    if not isinstance(schema, dict):
        return False
    settings_schema = schema.get(key, {}).get('items', {}).get('settings')
    if not isinstance(settings_schema, dict) or settings_schema.get('type') != 'object':
        return False
    return settings == _schema_defaults(settings_schema.get('items', {}))


def _read_migration_state(path):
    try:
        state = json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return {'version': _MIGRATION_VERSION, 'modules': {}}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('旧配置迁移记录无法读取，已停止自动导入。') from exc
    if (
        not isinstance(state, dict)
        or state.get('version') != _MIGRATION_VERSION
        or not isinstance(state.get('modules'), dict)
        or any(
            not isinstance(record, dict)
            or not isinstance(record.get('source'), str)
            or not record['source']
            or not isinstance(record.get('outcome'), str)
            or record.get('outcome') not in _MIGRATION_OUTCOMES
            for record in state['modules'].values()
        )
    ):
        raise ValueError('旧配置迁移记录格式不受支持，已停止自动导入。')
    return state


def _write_migration_state(path, state):
    """Keep migration metadata outside the schema-pruned config, without secrets."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=path.parent,
            prefix=path.name + '.', suffix='.tmp', delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _restore_sections(config, sections):
    for key, original in sections.items():
        config[key].clear()
        config[key].update(copy.deepcopy(original))


def import_legacy_settings(config, config_dir):
    """Import once, preserving explicit settings and later user resets.

    AstrBot has already filled schema defaults before calling this function.
    Only a first-deploy object whose settings still equal those defaults can
    replace nonempty values. Existing host configs are authoritative, including
    deliberately empty settings. Plain dictionaries retain the empty-section
    import behavior for callers without host deployment metadata.
    """
    root = Path(config_dir)
    state_path = root / _MIGRATION_STATE_NAME
    state = _read_migration_state(state_path)
    records = state['modules']
    imported = []
    originals = {}
    state_changed = False
    existing_host_config = (
        bool(getattr(config, 'config_path', None))
        and getattr(config, 'first_deploy', False) is not True
    )
    for key, primary_filename in LEGACY_CONFIGS.items():
        section = config.get(key)
        if not isinstance(section, dict):
            continue
        candidates = (primary_filename, *_LEGACY_CONFIG_ALIASES.get(key, ()))
        record = records.get(key)
        # Renaming a legacy config must not override a recorded migration/edit.
        if record is not None and record.get('source') in candidates:
            continue
        filename = next(
            (name for name in candidates if (root / name).exists()), primary_filename,
        )
        settings = section.get('settings')
        old_angel_settings = (
            key == 'memory'
            and isinstance(settings, dict)
            and bool(_ANGEL_MEMORY_KEYS.intersection(settings))
            and not bool(_LIVING_MEMORY_KEYS.intersection(settings))
        )
        untouched_defaults = _is_untouched_first_deploy(config, key, settings)
        if not old_angel_settings and (
            existing_host_config or (settings and not untouched_defaults)
        ):
            records[key] = {'source': filename, 'outcome': 'preserved'}
            state_changed = True
            continue
        try:
            value = json.loads((root / filename).read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeError, json.JSONDecodeError):
            records[key] = {'source': filename, 'outcome': 'unavailable'}
            state_changed = True
            if old_angel_settings:
                originals[key] = copy.deepcopy(section)
                section['settings'] = {}
            continue
        angel_only_source = (
            key == 'memory'
            and isinstance(value, dict)
            and bool(_ANGEL_MEMORY_KEYS.intersection(value))
            and not bool(_LIVING_MEMORY_KEYS.intersection(value))
        )
        if isinstance(value, dict) and not angel_only_source:
            if key == "proactive":
                for group in ("web_admin", "telemetry_config", "notification_settings"):
                    options = value.get(group)
                    if isinstance(options, dict) and "enabled" in options:
                        options["enabled"] = False
            originals[key] = copy.deepcopy(section)
            section['settings'] = copy.deepcopy(value)
            imported.append(key)
            records[key] = {'source': filename, 'outcome': 'imported'}
        else:
            records[key] = {'source': filename, 'outcome': 'invalid'}
            if old_angel_settings:
                originals[key] = copy.deepcopy(section)
                section['settings'] = {}
        state_changed = True
    save = getattr(config, 'save_config', None)
    if originals:
        try:
            if callable(save):
                save()
        except Exception:
            _restore_sections(config, originals)
            raise
    # Never record an import before the parent configuration has been saved.
    if state_changed:
        try:
            _write_migration_state(state_path, state)
        except Exception as state_error:
            if originals:
                imported_sections = {key: copy.deepcopy(config[key]) for key in originals}
                _restore_sections(config, originals)
                if callable(save):
                    try:
                        save()
                    except Exception as rollback_error:
                        # Keep memory aligned with the last successful atomic
                        # parent save; do not claim a rollback that did not persist.
                        _restore_sections(config, imported_sections)
                        raise RuntimeError(
                            '旧配置迁移记录写入失败，配置回滚也失败；'
                            '已保留最后保存的导入配置，请检查存储后再启动。'
                        ) from rollback_error
            raise OSError('旧配置迁移记录写入失败，已恢复原配置。') from state_error
    return imported
