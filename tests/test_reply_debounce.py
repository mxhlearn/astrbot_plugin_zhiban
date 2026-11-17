from __future__ import annotations

import asyncio
import json
import time
import unittest
from types import SimpleNamespace

from astrbot_plugin_zhiban.reply_debounce import (
    ReplyDebounceConfig,
    ReplyDebounceCoordinator,
)


class FakeEvent:
    def __init__(
        self,
        text: str,
        *,
        private: bool = True,
        umo: str = "private:1",
        sender: str = "u1",
        name: str = "用户",
        timestamp: int = 0,
        seq: int = 0,
    ) -> None:
        self.message_str = text
        self.unified_msg_origin = umo
        self.message_obj = SimpleNamespace(
            message=[SimpleNamespace(text=text)],
            message_id=f"m-{seq}",
            raw_message=SimpleNamespace(timestamp=timestamp, message_seq=seq),
            timestamp=timestamp,
        )
        self._private = private
        self._sender = sender
        self._name = name
        self._extras: dict = {}
        self.stopped = False

    def is_private_chat(self) -> bool:
        return self._private

    def get_sender_id(self) -> str:
        return self._sender

    def get_sender_name(self) -> str:
        return self._name

    def get_message_str(self) -> str:
        return self.message_str

    def get_messages(self):
        return self.message_obj.message

    def get_extra(self, key, default=None):
        return self._extras.get(key, default)

    def set_extra(self, key, value) -> None:
        self._extras[key] = value

    def stop_event(self) -> None:
        self.stopped = True

    def is_stopped(self) -> bool:
        return self.stopped


class FakeProvider:
    def __init__(self, completion_text: str = "<<reply>>", delay: float = 0.0):
        self.completion_text = completion_text
        self.delay = delay
        self.calls = 0
        self.requests = []
        self.provider_config = {"modalities": []}

    async def text_chat(self, **kwargs):
        self.calls += 1
        self.requests.append(dict(kwargs))
        if self.delay:
            await asyncio.sleep(self.delay)
        return SimpleNamespace(
            completion_text=self.completion_text,
            role="assistant",
            usage={"input_tokens": 3, "output_tokens": 2},
        )


class FakeContext:
    def __init__(self, provider: FakeProvider | None):
        self.provider = provider
        self.requested_umo = None
        self.provider_by_id = {}
        self.conversation_manager = None

    async def get_using_provider_async(self, umo=None):
        self.requested_umo = umo
        return self.provider

    def get_provider_by_id(self, provider_id):
        return self.provider_by_id.get(provider_id)


class FakeConversationManager:
    def __init__(self, history):
        self.history = history

    async def get_curr_conversation_id(self, umo):
        return "c1"

    async def get_conversation(self, umo, conversation_id):
        return SimpleNamespace(history=json.dumps(self.history, ensure_ascii=False))


class Recorder:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, event, response, **kwargs):
        self.calls.append((event, response, kwargs))


class Request:
    def __init__(self, prompt: str) -> None:
        self.prompt = prompt


async def wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.002)
    raise AssertionError("condition was not reached")


def make_coordinator(
    provider: FakeProvider | None = None,
    recorder=None,
    **config,
):
    values = {
        "thinking": False,
        "min_wait": 0.01,
        "max_wait": 0.03,
        "settle": 0.0,
        "max_window": 0.3,
        "reply_pause": 0.01,
    }
    values.update(config)
    return ReplyDebounceCoordinator(
        FakeContext(provider),
        config=values,
        usage_recorder=recorder,
    )


class ReplyDebounceCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_followup_reaches_admission_once(self):
        coordinator = make_coordinator()
        admitted = []

        async def admit(event):
            admitted.append(event)
            return True

        event = FakeEvent("你好")
        self.assertTrue(await coordinator.hold(event, admit))
        request = Request("你好")
        self.assertTrue(await coordinator.merge_request(event, request))
        self.assertEqual(request.prompt, "你好")
        self.assertEqual(admitted, [event])
        self.assertEqual(coordinator.status()["active_windows"], 0)
        await coordinator.close()

    async def test_one_followup_merges_once_and_stops_duplicate_event(self):
        coordinator = make_coordinator()
        admitted = []

        async def admit(event):
            admitted.append(event)
            return True

        first = FakeEvent("第一句", seq=1)
        second = FakeEvent("第二句", seq=2)
        leader = asyncio.create_task(coordinator.hold(first, admit))
        await wait_until(lambda: coordinator.status()["active_windows"] == 1)
        self.assertFalse(await coordinator.hold(second, admit))
        self.assertTrue(second.stopped)
        self.assertTrue(await leader)
        request = Request("第一句")
        self.assertTrue(await coordinator.merge_request(first, request))
        self.assertIn("第二句", request.prompt)
        self.assertIn("校验码", request.prompt)
        self.assertEqual(admitted, [first])
        await coordinator.close()

    async def test_conversations_and_senders_are_isolated(self):
        coordinator = make_coordinator()
        a = FakeEvent("A1", umo="private:a", sender="a", seq=1)
        a2 = FakeEvent("A2", umo="private:a", sender="a", seq=2)
        b = FakeEvent("B1", umo="private:b", sender="b", seq=1)
        b2 = FakeEvent("B2", umo="private:b", sender="b", seq=2)
        task_a = asyncio.create_task(coordinator.hold(a))
        task_b = asyncio.create_task(coordinator.hold(b))
        await wait_until(lambda: coordinator.status()["active_windows"] == 2)
        self.assertFalse(await coordinator.hold(a2))
        self.assertFalse(await coordinator.hold(b2))
        self.assertTrue(await task_a)
        self.assertTrue(await task_b)
        ra = Request("A1")
        rb = Request("B1")
        self.assertTrue(await coordinator.merge_request(a, ra))
        self.assertTrue(await coordinator.merge_request(b, rb))
        self.assertIn("A2", ra.prompt)
        self.assertNotIn("B2", ra.prompt)
        self.assertIn("B2", rb.prompt)
        self.assertNotIn("A2", rb.prompt)
        await coordinator.close()

    async def test_missing_marker_falls_back_wait_and_meters_draft(self):
        provider = FakeProvider("我还没完全想好，先别急着回。")
        recorder = Recorder()
        coordinator = make_coordinator(
            provider,
            recorder,
            thinking=True,
            max_passes=1,
        )
        event = FakeEvent("我想想")
        self.assertTrue(await coordinator.hold(event))
        status = coordinator.status()
        self.assertEqual(status["fallback_passes"], 1)
        self.assertEqual(status["metered_drafts"], 1)
        self.assertEqual(len(recorder.calls), 1)
        self.assertIs(recorder.calls[0][0], event)
        self.assertEqual(recorder.calls[0][2]["source"], "reply_debounce")
        request = Request("我想想")
        self.assertTrue(await coordinator.merge_request(event, request))
        self.assertIn("我还没完全想好", request.prompt)
        self.assertIn("校验码", request.prompt)
        await coordinator.close()

    async def test_only_last_legal_marker_controls_the_window(self):
        provider = FakeProvider("先等 <<wait 9>> 但后面改成 <<reply>>")
        coordinator = make_coordinator(provider, thinking=True, max_passes=1)
        event = FakeEvent("说完了")
        started = time.monotonic()
        self.assertTrue(await coordinator.hold(event))
        self.assertLess(time.monotonic() - started, 0.2)
        self.assertEqual(coordinator.draft_calls, 1)
        await coordinator.close()

    async def test_pass_limit_bounds_provider_calls(self):
        provider = FakeProvider("<<wait 9>>", delay=0.001)
        coordinator = make_coordinator(
            provider,
            thinking=True,
            max_passes=1,
            max_wait=0.04,
        )
        event = FakeEvent("第一句", seq=1)
        leader = asyncio.create_task(coordinator.hold(event))
        await wait_until(lambda: coordinator.draft_calls == 1)
        followup = FakeEvent("第二句", seq=2)
        self.assertFalse(await coordinator.hold(followup))
        self.assertTrue(await leader)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(coordinator.status()["draft_calls"], 1)
        await coordinator.close()

    async def test_followup_limit_forces_one_bounded_close(self):
        coordinator = make_coordinator(max_followups=1)
        event = FakeEvent("首条", seq=1)
        leader = asyncio.create_task(coordinator.hold(event))
        await wait_until(lambda: coordinator.status()["active_windows"] == 1)
        await asyncio.gather(
            coordinator.hold(FakeEvent("补充一", seq=2)),
            coordinator.hold(FakeEvent("补充二", seq=3)),
        )
        self.assertTrue(await leader)
        request = Request("首条")
        self.assertTrue(await coordinator.merge_request(event, request))
        self.assertIn("补充一", request.prompt)
        self.assertGreaterEqual(coordinator.status()["omitted_messages"], 1)
        await coordinator.close()

    async def test_byte_budget_truncates_and_closes(self):
        coordinator = make_coordinator(max_chars=64, max_bytes=64)
        event = FakeEvent("a" * 20, seq=1)
        leader = asyncio.create_task(coordinator.hold(event))
        await wait_until(lambda: coordinator.status()["active_windows"] == 1)
        self.assertFalse(await coordinator.hold(FakeEvent("b" * 80, seq=2)))
        self.assertTrue(await leader)
        request = Request("a" * 20)
        self.assertTrue(await coordinator.merge_request(event, request))
        self.assertEqual(coordinator.status()["truncated_messages"], 1)
        await coordinator.close()

    async def test_max_window_closes_without_unbounded_wait(self):
        coordinator = make_coordinator(
            min_wait=0.01,
            max_wait=0.5,
            max_window=0.05,
        )
        event = FakeEvent("继续等")
        started = time.monotonic()
        self.assertTrue(await coordinator.hold(event))
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.2)
        await coordinator.close()

    async def test_draft_timeout_falls_back(self):
        provider = FakeProvider("<<reply>>", delay=0.1)
        coordinator = make_coordinator(
            provider,
            thinking=True,
            draft_timeout=0.01,
            max_window=0.1,
        )
        event = FakeEvent("慢慢想")
        self.assertTrue(await coordinator.hold(event))
        status = coordinator.status()
        self.assertEqual(status["draft_timeouts"], 1)
        self.assertEqual(status["fallback_passes"], 1)
        await coordinator.close()

    async def test_cancel_parks_bounded_orphan_and_close_clears_it(self):
        coordinator = make_coordinator(min_wait=0.5, max_wait=0.5, max_window=1.0)
        event = FakeEvent("取消我", seq=1)
        leader = asyncio.create_task(coordinator.hold(event))
        await wait_until(lambda: coordinator.status()["active_windows"] == 1)
        leader.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await leader
        status = coordinator.status()
        self.assertEqual(status["active_windows"], 0)
        self.assertEqual(status["orphan_windows"], 1)
        await coordinator.close()
        closed = coordinator.status()
        self.assertEqual(closed["active_windows"], 0)
        self.assertEqual(closed["orphan_windows"], 0)

    async def test_close_wakes_active_window_without_leak(self):
        coordinator = make_coordinator(min_wait=0.5, max_wait=0.5, max_window=1.0)
        event = FakeEvent("关闭窗口")
        leader = asyncio.create_task(coordinator.hold(event))
        await wait_until(lambda: coordinator.status()["active_windows"] == 1)
        await coordinator.close()
        self.assertFalse(await asyncio.wait_for(leader, timeout=0.3))
        status = coordinator.status()
        self.assertEqual(status["active_windows"], 0)
        self.assertEqual(status["orphan_windows"], 0)

    async def test_scheduler_rejection_does_not_leak_pending(self):
        coordinator = make_coordinator()

        async def reject(event):
            return False

        event = FakeEvent("拒绝")
        self.assertFalse(await coordinator.hold(event, reject))
        self.assertTrue(event.stopped)
        status = coordinator.status()
        self.assertEqual(status["active_windows"], 0)
        self.assertEqual(status["orphan_windows"], 1)
        await coordinator.close()

    async def test_group_is_not_eligible_and_bypasses_coordinator(self):
        coordinator = make_coordinator(thinking=True)
        admitted = []

        async def admit(event):
            admitted.append(event)
            return True

        group = FakeEvent("群聊", private=False, umo="group:1")
        self.assertFalse(coordinator.eligible(group))
        self.assertTrue(await coordinator.hold(group, admit))
        self.assertEqual(admitted, [group])
        self.assertEqual(coordinator.draft_calls, 0)
        self.assertEqual(coordinator.status()["active_windows"], 0)
        await coordinator.close()

    async def test_orphan_is_rescued_by_next_window_once(self):
        coordinator = make_coordinator(
            orphan_grace=0.0,
            min_wait=0.2,
            max_wait=0.2,
            max_window=1.0,
        )
        old = FakeEvent("上一条未回复", seq=1)
        old_task = asyncio.create_task(coordinator.hold(old))
        await wait_until(lambda: coordinator.status()["active_windows"] == 1)
        old_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await old_task
        self.assertEqual(coordinator.status()["orphan_windows"], 1)

        new = FakeEvent("这一条", seq=2)
        new_task = asyncio.create_task(coordinator.hold(new))
        await wait_until(lambda: coordinator.status()["active_windows"] == 1)
        self.assertTrue(await new_task)
        request = Request("这一条")
        self.assertTrue(await coordinator.merge_request(new, request))
        self.assertIn("上一条未回复", request.prompt)
        self.assertEqual(coordinator.status()["rescued_windows"], 1)
        await coordinator.close()

    async def test_active_capacity_bypasses_without_opening_a_window(self):
        coordinator = make_coordinator(active_limit=1)
        first = FakeEvent("占用窗口", umo="private:a", sender="a")
        second = FakeEvent("旁路", umo="private:b", sender="b")
        admitted = []

        async def admit(event):
            admitted.append(event)
            return True

        leader = asyncio.create_task(coordinator.hold(first, admit))
        await wait_until(lambda: coordinator.status()["active_windows"] == 1)
        self.assertTrue(await coordinator.hold(second, admit))
        self.assertEqual(admitted, [second])
        self.assertEqual(coordinator.status()["capacity_bypasses"], 1)
        self.assertTrue(await leader)
        await coordinator.close()

    async def test_orphan_capacity_is_bounded(self):
        coordinator = make_coordinator(
            orphan_limit=1,
            min_wait=0.5,
            max_wait=0.5,
            max_window=1.0,
        )
        for index in range(2):
            event = FakeEvent(f"取消{index}", umo=f"private:{index}", sender="u")
            task = asyncio.create_task(coordinator.hold(event))
            await wait_until(lambda: coordinator.status()["active_windows"] == 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(coordinator.status()["orphan_windows"], 1)
        await coordinator.close()

    async def test_orphan_ttl_is_pruned(self):
        coordinator = make_coordinator(
            orphan_ttl=0.01,
            min_wait=0.5,
            max_wait=0.5,
            max_window=1.0,
        )
        event = FakeEvent("过期救援", umo="private:ttl", sender="u")
        task = asyncio.create_task(coordinator.hold(event))
        await wait_until(lambda: coordinator.status()["active_windows"] == 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.03)
        self.assertEqual(coordinator.status()["orphan_windows"], 0)
        await coordinator.close()

    def test_configuration_hard_caps(self):
        config = ReplyDebounceConfig.normalized(
            {
                "max_passes": 99,
                "max_followups": 99,
                "max_chars": 999999,
                "max_window": 999,
                "draft_concurrency": 99,
            }
        )
        self.assertEqual(config.max_passes, 6)
        self.assertEqual(config.max_followups, 16)
        self.assertEqual(config.max_chars, 32 * 1024)
        self.assertEqual(config.max_window, 60.0)
        self.assertEqual(config.draft_concurrency, 2)
        coordinator = ReplyDebounceCoordinator(FakeContext(None))
        self.assertEqual(coordinator.configure(max_passes=99).max_passes, 6)
        with self.assertRaises(ValueError):
            coordinator.configure(not_a_setting=True)


class ReplyDebounceProviderContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_merge_request_has_bounded_fallback_for_runners_without_wait_hook(self):
        coordinator = make_coordinator()
        first = FakeEvent('第一条', seq=1)
        request = Request('第一条')
        task = asyncio.create_task(coordinator.merge_request(first, request))
        await wait_until(lambda: coordinator.status()['active_windows'] == 1)
        self.assertFalse(await coordinator.hold(FakeEvent('补充', seq=2)))
        self.assertTrue(await task)
        self.assertIn('补充', request.prompt)
        await coordinator.close()

    async def test_configured_draft_provider_is_used_instead_of_session_provider(self):
        session_provider = FakeProvider("<<reply>>")
        draft_provider = FakeProvider("<<reply>>")
        context = FakeContext(session_provider)
        context.provider_by_id["cheap-draft"] = draft_provider
        coordinator = ReplyDebounceCoordinator(
            context,
            config={
                "thinking": True,
                "think_provider_id": "cheap-draft",
                "min_wait": 0.01,
                "max_wait": 0.03,
                "settle": 0.0,
                "max_window": 0.3,
                "reply_pause": 0.01,
            },
        )
        event = FakeEvent("你好", seq=1)
        self.assertTrue(await coordinator.hold(event))
        self.assertEqual(draft_provider.calls, 1)
        self.assertEqual(session_provider.calls, 0)
        await coordinator.close()

    async def test_style_and_bounded_history_are_passed_to_draft(self):
        provider = FakeProvider("<<reply>>")
        context = FakeContext(provider)
        context.conversation_manager = FakeConversationManager(
            [
                {"role": "user", "content": "历史问题"},
                {"role": "assistant", "content": "历史回答"},
            ]
        )
        style_calls = []

        async def style(event):
            style_calls.append(event)
            return "温柔、简短"

        coordinator = ReplyDebounceCoordinator(
            context,
            config={
                "thinking": True,
                "think_voice": "structured",
                "think_context": True,
                "think_context_chars": 512,
                "min_wait": 0.01,
                "max_wait": 0.03,
                "settle": 0.0,
                "max_window": 0.3,
                "reply_pause": 0.01,
            },
            style_provider=style,
        )
        event = FakeEvent("继续说", seq=1)
        self.assertTrue(await coordinator.hold(event))
        request = provider.requests[0]
        self.assertIn("结构化", request["system_prompt"])
        self.assertIn("温柔、简短", request["system_prompt"])
        self.assertIn("历史问题", request["prompt"])
        self.assertEqual(style_calls, [event])
        await coordinator.close()

    async def test_explicit_style_does_not_call_persona_style_provider(self):
        provider = FakeProvider("<<reply>>")
        context = FakeContext(provider)

        async def style(_event):
            raise AssertionError("style provider should not be called")

        coordinator = ReplyDebounceCoordinator(
            context,
            config={
                "thinking": True,
                "think_style": "冷静克制",
                "min_wait": 0.01,
                "max_wait": 0.03,
                "settle": 0.0,
                "max_window": 0.3,
                "reply_pause": 0.01,
            },
            style_provider=style,
        )
        self.assertTrue(await coordinator.hold(FakeEvent("说完了", seq=1)))
        self.assertIn("冷静克制", provider.requests[0]["system_prompt"])
        await coordinator.close()


if __name__ == "__main__":
    unittest.main()
