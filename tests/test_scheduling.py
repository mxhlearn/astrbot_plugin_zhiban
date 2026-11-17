import asyncio
import importlib.util
from pathlib import Path

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

@pytest.mark.asyncio
async def test_media_queue_limit_and_heavy_budget_serialize_maintenance():
    scheduler = BudgetScheduler(media_queue_limit=1, maintenance_queue_limit=1, wait_seconds=5)
    media_entered = asyncio.Event()
    media_release = asyncio.Event()
    maintenance_entered = asyncio.Event()

    async def media_holder():
        async with scheduler.media():
            media_entered.set()
            await media_release.wait()

    async def media_waiter():
        async with scheduler.media():
            return True

    async def maintenance_waiter():
        async with scheduler.maintenance():
            maintenance_entered.set()

    owner = asyncio.create_task(media_holder())
    await media_entered.wait()
    extra_media = asyncio.create_task(media_waiter())
    maintenance = asyncio.create_task(maintenance_waiter())
    await asyncio.sleep(0.02)
    assert not maintenance_entered.is_set()
    with pytest.raises(RuntimeError):
        async with scheduler.media():
            pass
    media_release.set()
    await owner
    await extra_media
    await maintenance
    assert maintenance_entered.is_set()
    assert scheduler.status()["media_running"] == 0
    assert scheduler.status()["maintenance_running"] == 0
    assert scheduler.status()["heavy_running"] == 0


@pytest.mark.asyncio
async def test_close_cancels_resource_waiter():
    scheduler = BudgetScheduler(media_queue_limit=2, wait_seconds=10)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with scheduler.media():
            entered.set()
            await release.wait()

    owner = asyncio.create_task(holder())
    await entered.wait()
    waiter = asyncio.create_task(_media_wait(scheduler))
    await asyncio.sleep(0.02)
    await scheduler.close()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    release.set()
    await owner


@pytest.mark.asyncio
async def test_live_configure_applies_global_limits_and_preserves_active_owner():
    scheduler = BudgetScheduler(chat_concurrency=1, media_concurrency=1, maintenance_concurrency=1)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with scheduler.media():
            entered.set()
            await release.wait()

    owner = asyncio.create_task(holder())
    await entered.wait()
    scheduler.configure(
        queue_limit=7,
        session_queue_limit=3,
        wait_seconds=12,
        chat_concurrency=2,
        media_concurrency=2,
        maintenance_concurrency=2,
        media_queue_limit=5,
        maintenance_queue_limit=4,
    )
    assert scheduler.queue_limit == 7
    assert scheduler.session_limit == 3
    assert scheduler.wait_seconds == 12
    assert scheduler.chat_capacity == 2
    assert scheduler.media_capacity == 2
    assert scheduler.maintenance_capacity == 2
    assert scheduler.media_queue_limit == 5
    assert scheduler.maintenance_queue_limit == 4
    release.set()
    await owner
    async with scheduler.media():
        pass
    assert not scheduler._media.locked()
    assert scheduler.status()["media_running"] == 0


@pytest.mark.asyncio
async def test_lowering_idle_chat_capacity_removes_free_permits():
    scheduler = BudgetScheduler(chat_concurrency=2)
    assert scheduler._chat.active == 0
    assert scheduler._chat.available == 2

    scheduler.configure(chat_concurrency=1)

    assert scheduler.chat_capacity == 1
    assert scheduler._chat.capacity == 1
    assert scheduler._chat.active == 0
    assert scheduler._chat._value == 1


@pytest.mark.asyncio
async def test_lowering_active_chat_capacity_keeps_holders_without_leaking_permits():
    scheduler = BudgetScheduler(chat_concurrency=2)
    entered = [asyncio.Event() for _ in range(2)]
    release = asyncio.Event()

    async def holder(index):
        assert await scheduler.admit_pipeline(Event(f"scope-{index}"))
        entered[index].set()
        await release.wait()

    owners = [asyncio.create_task(holder(index)) for index in range(2)]
    await asyncio.gather(*(event.wait() for event in entered))
    assert scheduler._chat.active == 2

    scheduler.configure(chat_concurrency=1)
    assert scheduler.chat_capacity == 1
    assert scheduler._chat.active == 2
    assert scheduler._chat.available == 0

    release.set()
    await asyncio.gather(*owners)
    assert scheduler._chat.active == 0
    assert scheduler._chat.available == 1


@pytest.mark.asyncio
async def test_queued_chat_waiters_survive_raise_and_lower_in_one_pool():
    scheduler = BudgetScheduler(chat_concurrency=1, queue_limit=10, wait_seconds=10)
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    release_waiters = asyncio.Event()
    entered = []

    async def holder(index):
        assert await scheduler.admit_pipeline(Event(f"scope-{index}"))
        entered.append(index)
        if index == 0:
            first_entered.set()
            await release_first.wait()
        else:
            await release_waiters.wait()

    owner = asyncio.create_task(holder(0))
    await first_entered.wait()
    waiters = [asyncio.create_task(holder(index)) for index in (1, 2, 3)]
    await asyncio.sleep(.02)
    assert scheduler._chat.waiting == 3

    scheduler.configure(chat_concurrency=4)
    await asyncio.sleep(.02)
    assert scheduler._chat.active == 4
    assert scheduler._chat.waiting == 0
    assert entered == [0, 1, 2, 3]

    scheduler.configure(chat_concurrency=2)
    assert scheduler._chat.active == 4
    assert scheduler._chat.capacity == 2
    release_first.set()
    await owner
    release_waiters.set()
    await asyncio.gather(*waiters)
    assert scheduler._chat.active == 0
    assert scheduler._chat.available == 2


@pytest.mark.asyncio
async def test_cancelled_and_timed_out_waiters_do_not_leave_phantom_permits():
    scheduler = BudgetScheduler(chat_concurrency=1, wait_seconds=.01)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        assert await scheduler.admit_pipeline(Event("owner"))
        entered.set()
        await release.wait()

    owner = asyncio.create_task(holder())
    await entered.wait()
    cancelled = asyncio.create_task(scheduler.admit_pipeline(Event("cancelled")))
    await asyncio.sleep(.01)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert not await scheduler.admit_pipeline(Event("timeout"))
    assert scheduler._chat.waiting == 0
    assert scheduler._chat.active == 1

    release.set()
    await owner
    assert scheduler._chat.active == 0
    assert scheduler._chat.available == 1


@pytest.mark.asyncio
async def test_configure_lower_then_raise_does_not_add_concurrency_to_active_pool():
    scheduler = BudgetScheduler(media_concurrency=2)
    entered = []
    release = asyncio.Event()

    owner_entered = asyncio.Event()

    async def holder(index):
        async with scheduler.media():
            entered.append(index)
            if index == 0:
                owner_entered.set()
                await release.wait()
            else:
                await asyncio.Event().wait()

    owners = [asyncio.create_task(holder(index)) for index in range(2)]
    await owner_entered.wait()
    for _ in range(20):
        if scheduler._media.active == 2:
            break
        await asyncio.sleep(0)
    assert scheduler._media.active == 2

    scheduler.configure(media_concurrency=1)
    assert scheduler._media.capacity == 1
    assert scheduler._media.active == 2
    scheduler.configure(media_concurrency=2)
    assert scheduler._media.capacity == 2
    assert scheduler._media.active == 2
    assert scheduler._media.available == 0

    release.set()
    await owners[0]
    for owner in owners[1:]:
        owner.cancel()
    await asyncio.gather(*owners[1:], return_exceptions=True)
    assert scheduler._media.active == 0
    assert scheduler._media.available == 2


@pytest.mark.asyncio
async def test_close_with_queued_chat_waiters_does_not_deadlock_or_double_release():
    scheduler = BudgetScheduler(chat_concurrency=1, queue_limit=10, wait_seconds=10)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        assert await scheduler.admit_pipeline(Event("owner"))
        entered.set()
        await release.wait()

    owner = asyncio.create_task(holder())
    await entered.wait()
    waiters = [asyncio.create_task(scheduler.admit_pipeline(Event(f"waiter-{index}"))) for index in range(3)]
    await asyncio.sleep(.02)
    assert scheduler._chat.waiting == 3

    scheduler.configure(chat_concurrency=2)
    await asyncio.sleep(.02)

    await asyncio.wait_for(scheduler.close(), timeout=1)
    assert all(waiter.done() for waiter in waiters)
    results = [waiter.result() for waiter in waiters]
    release.set()
    await owner
    assert all(results)
    assert scheduler._chat.active == 0
    assert scheduler._chat.available == 2


async def _media_wait(scheduler):
    async with scheduler.media():
        return True