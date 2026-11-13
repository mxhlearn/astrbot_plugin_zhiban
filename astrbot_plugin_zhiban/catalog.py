"""菜单顺序为个人聊天机器人的预设使用频率，不冒充用户使用统计。"""

MODULES = (
    {"key": "heart", "label": "聊天互动", "package": "astrbot_plugin_angel_heart"},
    {"key": "memory", "label": "记忆与成长", "package": "astrbot_plugin_angel_memory"},
    {"key": "meme", "label": "表情互动", "package": "astrbot_plugin_meme_manager"},
    {"key": "tts", "label": "语音回复", "package": "astrbot_plugin_breeze_tts"},
    {"key": "proactive", "label": "主动问候", "package": "astrbot_plugin_proactive_chat"},
    {"key": "brush", "label": "图片创作", "package": "astrbot_plugin_angel_brush"},
    {"key": "music", "label": "音乐点播", "package": "astrbot_plugin_listen_music"},
    {"key": "eye", "label": "历史查询", "package": "astrbot_plugin_angel_eye"},
    {"key": "qzone", "label": "QQ空间", "package": "astrbot_plugin_qzone_ultra"},
    {"key": "filter", "label": "内容过滤", "package": "astrbot_plugin_link_filter"},
)


def ordered_modules(order=None):
    """允许管理员稳定调整菜单顺序；未知和重复项不改变已知模块。"""
    lookup = {s["key"]: s for s in MODULES}
    result = []
    for key in order or ():
        if key in lookup and lookup[key] not in result:
            result.append(lookup[key])
    return result + [s for s in MODULES if s not in result]
