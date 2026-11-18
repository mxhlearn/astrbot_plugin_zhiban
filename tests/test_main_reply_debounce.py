from __future__ import annotations

import unittest
from types import SimpleNamespace

from astrbot_plugin_zhiban.main import ZhibanPlugin


class FakeEvent:
    def __init__(self, _text="", *, umo=None):
        self.extra = {}
        self.stopped = False
        self.unified_msg_origin = umo or "private:1"

    def set_extra(self, key, value):
        self.extra[key] = value

    def get_extra(self, key, default=None):
        return self.extra.get(key, default)

    def stop_event(self):
        self.stopped = True


class FakeScheduler:
    def __init__(self, admitted=True):
        self.result = admitted
        self.events = []

    async def admit_pipeline(self, event):
        self.events.append(event)
        return self.result


class FakeCoordinator:
    def __init__(self, continued=True):
        self.continued = continued
        self.held = []
        self.merged = []

    async def hold(self, event, admit):
        self.held.append(event)
        return await admit(event)

    async def merge_request(self, event, request):
        self.merged.append((event, request))
        return self.continued


class MainReplyDebounceTests(unittest.IsolatedAsyncioTestCase):
    def test_config_is_owned_by_heart_and_includes_draft_boundaries(self):
        plugin = object.__new__(ZhibanPlugin)
        plugin.config = {
            "heart": {
                "settings": {
                    "reply_debounce": {
                        "enabled": False,
                        "enable_thinking": False,
                        "think_provider_id": "cheap",
                        "think_style": "克制",
                        "think_context": False,
                        "think_context_chars": 900,
                        "min_wait": 2,
                        "max_wait": 5,
                        "max_window": 20,
                        "max_passes": 3,
                        "max_followups": 4,
                        "max_chars": 1000,
                        "max_bytes": 2000,
                        "forward_images": False,
                        "draft_concurrency": 2,
                    }
                }
            },
            "management": {"reply_debounce": {"enabled": True}},
        }
        config = plugin._reply_debounce_config()
        self.assertFalse(config["enabled"])
        self.assertFalse(config["thinking"])
        self.assertEqual(config["think_provider_id"], "cheap")
        self.assertEqual(config["think_context_chars"], 900)
        self.assertEqual(config["max_bytes"], 2000)
        self.assertFalse(config["forward_images"])
        self.assertEqual(config["draft_concurrency"], 2)

    async def test_admit_uses_coordinator_then_marks_usage_admission(self):
        plugin = object.__new__(ZhibanPlugin)
        plugin.reply_debounce = FakeCoordinator()
        plugin.scheduler = FakeScheduler(True)
        plugin.logger = SimpleNamespace(info=lambda *a, **k: None)
        event = FakeEvent()
        await plugin.admit(event)
        self.assertEqual(plugin.reply_debounce.held, [event])
        self.assertEqual(plugin.scheduler.events, [event])
        self.assertTrue(event.extra["_zhiban_usage_admitted"])

    async def test_merge_stops_event_when_window_was_rescued(self):
        plugin = object.__new__(ZhibanPlugin)
        plugin.reply_debounce = FakeCoordinator(continued=False)
        event = FakeEvent()
        request = SimpleNamespace()
        await plugin.merge_reply_request(event, request)
        self.assertTrue(event.stopped)
        self.assertEqual(plugin.reply_debounce.merged, [(event, request)])

    async def test_style_combines_current_base_persona_and_approved_supplement(self):
        class BasePersona:
            prompt = "基础语气"

        class Conversation:
            persona_id = "conv-persona"

        class ConversationManager:
            def get_current_conversation(self, umo):
                self.umo = umo
                return Conversation()

        class PersonaManager:
            async def resolve_selected_persona(self, *, umo, conversation_persona_id, platform_name):
                self.args = (umo, conversation_persona_id, platform_name)
                return (conversation_persona_id, BasePersona(), None, False)

        class Supplement:
            async def approved_text(self, scope):
                self.scope = scope
                return "补充语气"

        plugin = object.__new__(ZhibanPlugin)
        plugin.persona = Supplement()
        plugin.context = SimpleNamespace(
            persona_manager=PersonaManager(),
            conversation_manager=ConversationManager(),
        )
        event = FakeEvent("测试", umo="aiocqhttp:friend:u1")
        event.get_sender_id = lambda: "u1"
        event.is_private_chat = lambda: True
        event.get_platform_name = lambda: "aiocqhttp"
        text = await plugin._reply_debounce_style(event)
        self.assertIn("基础语气", text)
        self.assertIn("补充语气", text)
        self.assertEqual(
            plugin.context.persona_manager.args,
            ("aiocqhttp:friend:u1", "conv-persona", "aiocqhttp"),
        )

    async def test_style_falls_back_when_host_persona_resolution_fails(self):
        class Supplement:
            async def approved_text(self, scope):
                return "补充语气"

        class PersonaManager:
            async def resolve_selected_persona(self, **kwargs):
                raise RuntimeError("persona unavailable")

        plugin = object.__new__(ZhibanPlugin)
        plugin.persona = Supplement()
        plugin.context = SimpleNamespace(
            persona_manager=PersonaManager(),
            conversation_manager=None,
        )
        event = FakeEvent("测试", umo="aiocqhttp:friend:u1")
        event.get_sender_id = lambda: "u1"
        event.is_private_chat = lambda: True
        event.get_platform_name = lambda: "aiocqhttp"
        text = await plugin._reply_debounce_style(event)
        self.assertEqual(text, "补充语气")


if __name__ == "__main__":
    unittest.main()
    async def test_anysearch_readiness_uses_module_checker(self):
        class Search:
            def module_readiness(self):
                return {"state": "not_ready", "label": "未配置", "detail": "未配置 Anysearch API Key"}

        plugin = object.__new__(ZhibanPlugin)
        plugin.host = SimpleNamespace(instances={"search": Search()})
        plugin._readiness_cache = {}
        result = await plugin._module_readiness(
            {"key": "search", "enabled": True, "state": "running"}
        )
        self.assertEqual(result["state"], "not_ready")
        self.assertIn("API Key", result["detail"])
