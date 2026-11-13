import copy
import json
from pathlib import Path

LEGACY_CONFIGS = {
    'heart': 'astrbot_plugin_angel_heart_config.json',
    'memory': 'astrbot_plugin_angel_memory_config.json',
    'eye': 'astrbot_plugin_angel_eye_config.json',
    'brush': 'astrbot_plugin_angel_brush_config.json',
    'tts': 'astrbot_plugin_breeze_tts_config.json',
    'meme': 'astrbot_plugin_meme_manager_config.json',
    'music': 'astrbot_plugin_listen_music_config.json',
    'proactive': 'astrbot_plugin_proactive_chat_config.json',
    'qzone': 'astrbot_plugin_qzone_ultra_config.json',
    'filter': 'astrbot_plugin_link_filter_config.json',
}


def import_legacy_settings(config, config_dir):
    root = Path(config_dir)
    imported = []
    for key, filename in LEGACY_CONFIGS.items():
        section = config.get(key)
        if not isinstance(section, dict) or section.get('settings'):
            continue
        try:
            value = json.loads((root / filename).read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            if key == "proactive":
                for group in ("web_admin", "telemetry_config", "notification_settings"):
                    options = value.get(group)
                    if isinstance(options, dict) and "enabled" in options:
                        options["enabled"] = False
            section['settings'] = copy.deepcopy(value)
            imported.append(key)
    if imported:
        save = getattr(config, 'save_config', None)
        if callable(save):
            save()
    return imported
