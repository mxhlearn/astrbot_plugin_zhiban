import asyncio
import unittest
from types import SimpleNamespace

from astrbot.core.message.components import Plain
from astrbot_plugin_zhiban.main import ZhibanPlugin
from astrbot_plugin_zhiban.coalescing import MessageCoalescer


class FakeEvent:
    def __init__(self, text, *, private=True, extra=None, chain=None):
        self.message_str = text
        self.message_obj = SimpleNamespace(
            message=chain if chain is not None else [Plain(text)],
            message_id="m1",
        )
        self.unified_msg_origin = "private:1" if private else "group:1"
        self._private = private
        self._extra = dict(extra or {})
        self.stopped = False

    def is_private_chat(self):
        return self._private

    def get_sender_id(self):
        return "u1"

    def get_extra(self, key, default=None):
        return self._extra.get(key, default)

    def set_extra(self, key, value):
        self._extra[key] = value

    def stop_event(self):
        self.stopped = True


class MainCoalescingTests(unittest.TestCase):
    def setUp(self):
        self.plugin = object.__new__(ZhibanPlugin)
        self.plugin.config = {"heart": {"settings": {"reply_rhythm": {"coalesce_enabled": True}}}}

    def test_private_plain_text_is_eligible(self):
        self.assertTrue(self.plugin._coalesce_eligible(FakeEvent("你好")))

    def test_command_and_media_are_not_eligible(self):
        self.assertFalse(self.plugin._coalesce_eligible(FakeEvent("/status")))
        self.assertFalse(self.plugin._coalesce_eligible(FakeEvent("看图", chain=[object()])))

    def test_group_already_debounced_is_not_eligible(self):
        event = FakeEvent("普通文本", private=False, extra={"angelheart_debounce_kind": "secretary"})
        self.assertFalse(self.plugin._coalesce_eligible(event))

    def test_apply_merged_text_preserves_event_identity(self):
        event = FakeEvent("第一句")
        self.plugin._apply_coalesced_text(event, "第一句\n第二句", ["m1", "m2"])
        self.assertEqual(event.message_str, "第一句\n第二句")
        self.assertEqual(event.message_obj.message[0].text, "第一句\n第二句")
        self.assertEqual(event.message_obj.message_id, "m1")
        self.assertEqual(event.get_extra("_zhiban_coalesced_count"), 2)

    def test_reply_rhythm_is_owned_by_heart_and_old_global_is_fallback(self):
        self.plugin.config = {
            "heart": {"settings": {"reply_rhythm": {
                "coalesce_enabled": False,
                "coalesce_quiet_ms": 900,
                "coalesce_max_ms": 3000,
                "coalesce_max_messages": 5,
                "coalesce_max_chars": 1200,
            }}},
            "management": {
                "coalesce_enabled": True,
                "coalesce_quiet_ms": 1500,
                "coalesce_max_ms": 5000,
                "coalesce_max_messages": 8,
                "coalesce_max_chars": 2000,
            },
        }
        self.assertFalse(self.plugin._coalesce_eligible(FakeEvent("你好")))
        self.assertEqual(self.plugin._reply_rhythm_config(), {
            "coalesce_enabled": False,
            "coalesce_quiet_ms": 900,
            "coalesce_max_ms": 3000,
            "coalesce_max_messages": 5,
            "coalesce_max_chars": 1200,
        })
        self.plugin.config = {"management": {"coalesce_enabled": False, "coalesce_quiet_ms": 700}}
        self.assertEqual(self.plugin._reply_rhythm_config()["coalesce_quiet_ms"], 700)
        self.assertFalse(self.plugin._reply_rhythm_config()["coalesce_enabled"])



class FakeScheduler:
    def __init__(self):
        self.admitted = []

    async def admit_pipeline(self, event):
        self.admitted.append(event.message_str)
        return True


class MainCoalescingIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_plain_events_reach_admission_once_with_merged_text(self):
        plugin = object.__new__(ZhibanPlugin)
        plugin.config = {"heart": {"settings": {"reply_rhythm": {"coalesce_enabled": True}}}}
        plugin.coalescer = MessageCoalescer(quiet_seconds=0.05, max_seconds=0.3)
        plugin.scheduler = FakeScheduler()
        first = FakeEvent("第一句")
        second = FakeEvent("第二句")
        await asyncio.gather(plugin.admit(first), plugin.admit(second))
        self.assertEqual(plugin.scheduler.admitted, ["第一句\n第二句"])
        self.assertTrue(second.stopped)


if __name__ == "__main__":
    unittest.main()
