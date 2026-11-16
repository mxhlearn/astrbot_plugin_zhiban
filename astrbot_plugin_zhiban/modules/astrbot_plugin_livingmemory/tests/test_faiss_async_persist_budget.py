"""AsyncIndexPersister 与知伴 maintenance 预算的边界测试。"""

import asyncio
import threading
from contextlib import asynccontextmanager

import faiss
import numpy as np
import pytest
from astrbot_plugin_livingmemory.core import faiss_async_persist
from astrbot_plugin_livingmemory.core.faiss_async_persist import install_async_persist


class _BudgetSpy:
    def __init__(self):
        self.entries = 0
        self.exits = 0
        self.active = 0

    @asynccontextmanager
    async def maintenance(self):
        self.entries += 1
        self.active += 1
        try:
            yield
        finally:
            self.active -= 1
            self.exits += 1


class _Storage:
    def __init__(self, path):
        self.path = str(path)
        self.dimension = 8
        self.index = faiss.IndexIDMap(faiss.IndexFlatL2(8))

    async def save_index(self):
        faiss.write_index(self.index, self.path)

    async def insert_batch(self, vectors, ids):
        self.index.add_with_ids(vectors, np.asarray(ids, dtype=np.int64))
        await self.save_index()


def _storage(tmp_path, name="index.faiss"):
    storage = _Storage(tmp_path / name)
    storage.index.add_with_ids(
        np.random.rand(4, 8).astype(np.float32),
        np.arange(4, dtype=np.int64),
    )
    return storage


@pytest.mark.asyncio
async def test_debounce_wait_holds_no_ticket_and_write_holds_one(tmp_path, monkeypatch):
    budget = _BudgetSpy()
    storage = _storage(tmp_path)
    persister = install_async_persist(storage, debounce_seconds=600, budget=budget)
    observed = {}

    def write(index, path):
        observed["active_during_write"] = budget.active
        real_write(index, path)

    real_write = faiss_async_persist._write_index_atomic
    monkeypatch.setattr(faiss_async_persist, "_write_index_atomic", write)

    await storage.save_index()
    await asyncio.sleep(0.05)
    assert budget.entries == 0
    assert budget.active == 0

    await persister.flush_now()
    assert observed == {"active_during_write": 1}
    assert budget.entries == 1
    assert budget.exits == 1
    assert budget.active == 0
    await persister.aclose()


@pytest.mark.asyncio
async def test_cancelled_flush_releases_ticket_after_worker_finishes(tmp_path, monkeypatch):
    budget = _BudgetSpy()
    storage = _storage(tmp_path)
    persister = install_async_persist(storage, debounce_seconds=600, budget=budget)
    started = threading.Event()
    release = threading.Event()
    real_write = faiss_async_persist._write_index_atomic

    def blocking_write(index, path):
        started.set()
        assert release.wait(5)
        real_write(index, path)

    monkeypatch.setattr(faiss_async_persist, "_write_index_atomic", blocking_write)
    await storage.save_index()
    flush = asyncio.create_task(persister.flush_now())
    try:
        assert await asyncio.to_thread(started.wait, 2)
        assert budget.active == 1
        flush.cancel()
        await asyncio.sleep(0.01)
        assert not flush.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await flush
    assert budget.active == 0
    assert budget.entries == budget.exits == 1
    await persister.aclose()


@pytest.mark.asyncio
async def test_aclose_releases_ticket_for_pending_flush(tmp_path):
    budget = _BudgetSpy()
    storage = _storage(tmp_path)
    persister = install_async_persist(storage, debounce_seconds=600, budget=budget)

    await storage.save_index()
    assert budget.entries == 0
    await persister.aclose()

    assert budget.entries == budget.exits == 1
    assert budget.active == 0
    loaded = faiss.read_index(storage.path)
    assert loaded.ntotal == 4
@pytest.mark.asyncio
async def test_budget_holder_can_mutate_while_flush_waits(tmp_path, monkeypatch):
    """预算在索引读锁之前获取：持有者增删不会与落盘跨任务互等。"""
    from astrbot_plugin_zhiban.scheduling import BudgetScheduler

    budget = BudgetScheduler(maintenance_concurrency=1, heavy_concurrency=1)
    storage = _storage(tmp_path)
    persister = install_async_persist(storage, debounce_seconds=0, budget=budget)
    real_write = faiss_async_persist._write_index_atomic
    write_started = threading.Event()
    release_write = threading.Event()

    def blocking_write(index, path):
        write_started.set()
        assert release_write.wait(5)
        real_write(index, path)

    monkeypatch.setattr(faiss_async_persist, "_write_index_atomic", blocking_write)
    await storage.save_index()
    try:
        assert await asyncio.to_thread(write_started.wait, 2)
        mutation = asyncio.create_task(storage.insert_batch(
            np.zeros((1, storage.dimension), dtype=np.float32), [99]
        ))
        await asyncio.sleep(0.01)
        # 落盘已持预算和读锁，增删应等待，而不是反向抢预算死锁。
        assert not mutation.done()
        release_write.set()
        await asyncio.wait_for(mutation, timeout=2)
        await asyncio.wait_for(persister.flush_now(), timeout=2)
    finally:
        release_write.set()
        await persister.aclose()
        await budget.close()
    assert budget.status()["maintenance_running"] == 0


@pytest.mark.asyncio
async def test_budget_wait_cancellation_leaves_persister_usable(tmp_path):
    """等待预算时取消 flush 不泄漏索引锁，预算释放后仍可正常落盘。"""
    from contextlib import asynccontextmanager
    from astrbot_plugin_zhiban.scheduling import BudgetScheduler

    budget = BudgetScheduler(maintenance_concurrency=1, heavy_concurrency=1)
    holder_ready = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder():
        async with budget.maintenance():
            holder_ready.set()
            await release_holder.wait()

    holder_task = asyncio.create_task(holder())
    storage = _storage(tmp_path)
    persister = install_async_persist(storage, debounce_seconds=0, budget=budget)
    try:
        await holder_ready.wait()
        await storage.save_index()
        flush = asyncio.create_task(persister.flush_now())
        await asyncio.sleep(0.02)
        assert not flush.done()
        flush.cancel()
        with pytest.raises(asyncio.CancelledError):
            await flush
        release_holder.set()
        await holder_task
        await asyncio.wait_for(persister.flush_now(), timeout=2)
    finally:
        release_holder.set()
        await budget.close()
        await persister.aclose()
    assert budget.status()["maintenance_running"] == 0
@pytest.mark.asyncio
async def test_aclose_after_budget_close_does_not_raise(tmp_path):
    """宿主预算先关闭时，persister 清理不得重新取票或抛 RuntimeError。"""
    from astrbot_plugin_zhiban.scheduling import BudgetScheduler

    budget = BudgetScheduler(maintenance_concurrency=1, heavy_concurrency=1)
    storage = _storage(tmp_path)
    persister = install_async_persist(storage, debounce_seconds=600, budget=budget)
    await storage.save_index()
    await budget.close()

    await persister.aclose()
    assert persister._closed is True