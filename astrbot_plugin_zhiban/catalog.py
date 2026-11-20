"""知伴模块目录；顺序按常用工作流排列，不冒充用户统计。"""

MODULES = (
    {"key": "heart", "label": "聊天互动", "package": "astrbot_plugin_angel_heart", "group": "聊天系统"},
    {"key": "search", "label": "联网搜索", "package": "astrbot_plugin_anysearch", "group": "聊天系统"},
    {"key": "memory", "label": "记忆成长", "package": "astrbot_plugin_livingmemory", "group": "记忆成长"},
    {"key": "meme", "label": "表情互动", "package": "astrbot_plugin_meme_manager", "group": "表达创作"},
    {"key": "tts", "label": "语音回复", "package": "astrbot_plugin_breeze_tts", "group": "表达创作"},
    {"key": "proactive", "label": "主动问候", "package": "astrbot_plugin_proactive_chat", "group": "聊天系统"},
    {"key": "brush", "label": "图片创作", "package": "astrbot_plugin_angel_brush", "group": "表达创作"},
    {"key": "music", "label": "音乐点播", "package": "astrbot_plugin_listen_music", "group": "表达创作"},
    {"key": "eye", "label": "历史查询", "package": "astrbot_plugin_angel_eye", "group": "聊天系统"},
    {"key": "qzone", "label": "QQ 动态", "package": "astrbot_plugin_qzone_ultra", "group": "QQ 社交"},
    {"key": "qqprofile", "label": "QQ 资料", "package": "astrbot_plugin_qqprofile", "group": "QQ 社交"},
)

GROUPS = (
    {"key": "overview", "label": "总览", "order": 0},
    {"key": "chat", "label": "聊天系统", "order": 1},
    {"key": "memory", "label": "记忆成长", "order": 2},
    {"key": "creative", "label": "表达创作", "order": 3},
    {"key": "social", "label": "QQ 社交", "order": 4},
)


def ordered_modules(order=None):
    """允许管理员稳定调整菜单顺序；未知和重复项不改变已知模块。"""
    lookup = {spec["key"]: spec for spec in MODULES}
    result = []
    for key in order or ():
        if key in lookup and lookup[key] not in result:
            result.append(lookup[key])
    return result + [spec for spec in MODULES if spec not in result]
