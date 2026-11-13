import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("zhiban_scheduling", Path(__file__).parents[1] / "astrbot_plugin_zhiban/scheduling.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
BudgetScheduler = module.BudgetScheduler


class Event:
    def __init__(self, scope="test"):
        self.unified_msg_origin = scope
        self.stopped = False

    def stop_event(self):
        self.stopped = True


@pytest.mark.asyncio
async def test_per_session_queue_and_task_completion_release():
    scheduler = BudgetScheduler(queue_limit=2, session_queue_limit=1)
    gate = asyncio.Event()
    async def first():
        assert await scheduler.admit_pipeline(Event())
        assert await scheduler.admit_pipeline(Event())  # 同流水线可重复经过hook
        await gate.wait()
    owner = asyncio.create_task(first())
    await asyncio.sleep(.01)
    waiting = asyncio.create_task(scheduler.admit_pipeline(Event()))
    await asyncio.sleep(.01)
    rejected_event = Event()
    assert not await scheduler.admit_pipeline(rejected_event)
    assert rejected_event.stopped
    gate.set()
    await owner
    assert await waiting
    await asyncio.sleep(0)
    assert scheduler.status()["running"] == 0
    assert scheduler.status()["waiting"] == 0


@pytest.mark.asyncio
async def test_timeout_does_not_leak_or_leave_event_active():
    scheduler = BudgetScheduler()
    scheduler.wait_seconds = .01
    gate = asyncio.Event()
    async def first():
        await scheduler.admit_pipeline(Event())
        await gate.wait()
    owner = asyncio.create_task(first())
    await asyncio.sleep(.01)
    event = Event("second")
    assert not await scheduler.admit_pipeline(event)
    assert event.stopped
    assert scheduler.status()["waiting"] == 0
    gate.set()
    await owner
    await asyncio.sleep(0)
    assert not scheduler._chat.locked()


@pytest.mark.asyncio
async def test_media_nested_calls_no_deadlock_and_exception_releases():
    scheduler = BudgetScheduler()
    with pytest.raises(ValueError):
        async with scheduler.media():
            async with scheduler.media():
                raise ValueError("test")
    assert not scheduler._media.locked()


@pytest.mark.asyncio
async def test_close_rejects_and_clears_waiters():
    scheduler = BudgetScheduler()
    gate = asyncio.Event()
    async def first():
        await scheduler.admit_pipeline(Event())
        await gate.wait()
    owner = asyncio.create_task(first())
    await asyncio.sleep(.01)
    event = Event("second")
    waiter = asyncio.create_task(scheduler.admit_pipeline(event))
    await asyncio.sleep(.01)
    await scheduler.close()
    assert not await waiter
    assert event.stopped
    gate.set()
    await owner
    assert not await scheduler.admit_pipeline(Event("last"))
