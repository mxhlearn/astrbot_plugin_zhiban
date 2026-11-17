from __future__ import annotations

import logging
import sys
import types
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
MODULES_ROOT = MODULE_ROOT.parent
for path in (str(MODULE_ROOT), str(MODULES_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _install_astrbot_stubs() -> None:
    if "astrbot" in sys.modules:
        return

    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.AstrBotConfig = dict
    api.logger = logging.getLogger("astrbot-anysearch-tests")
    api.FunctionTool = type(
        "FunctionTool",
        (),
        {"__init__": lambda self, **kwargs: self.__dict__.update(kwargs)},
    )

    event = types.ModuleType("astrbot.api.event")
    event.AstrMessageEvent = object
    event.filter = types.SimpleNamespace(command=lambda *a, **k: (lambda func: func))

    star = types.ModuleType("astrbot.api.star")
    class Star:
        def __init__(self, context, config=None):
            self.context = context

    star.Star = Star
    star.Context = object
    star.register = lambda *a, **k: (lambda cls: cls)

    core = types.ModuleType("astrbot.core")
    core_star = types.ModuleType("astrbot.core.star")
    core_filter = types.ModuleType("astrbot.core.star.filter")
    command = types.ModuleType("astrbot.core.star.filter.command")
    command.GreedyStr = str

    api.event = event
    api.star = star
    astrbot.api = api
    astrbot.core = core
    core.star = core_star
    core.star.filter = core_filter
    core_filter.command = command

    sys.modules.update(
        {
            "astrbot": astrbot,
            "astrbot.api": api,
            "astrbot.api.event": event,
            "astrbot.api.star": star,
            "astrbot.core": core,
            "astrbot.core.star": core_star,
            "astrbot.core.star.filter": core_filter,
            "astrbot.core.star.filter.command": command,
        }
    )


_install_astrbot_stubs()