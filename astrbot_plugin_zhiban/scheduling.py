"""有界准入；持有票据到原 AstrBot 流水线真正结束，而非到 Agent 返回。"""
from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import asynccontextmanager


class BudgetScheduler:
    """Small in-process budget for chat, media and maintenance work.

    Chat admission is counted per conversation and held until the pipeline task
    ends. Media and maintenance share one heavy-resource semaphore so two
    "each concurrency one" jobs cannot decode or index simultaneously. No
    worker threads, model processes or persistent queue are introduced here.
    """

    def __init__(
        self,
        queue_limit=20,
        session_queue_limit=4,
        wait_seconds=90,
        *,
        chat_concurrency=1,
        media_concurrency=1,
        maintenance_concurrency=1,
        media_queue_limit=8,
        maintenance_queue_limit=8,
        heavy_concurrency=1,
    ):
        self.queue_limit = max(1, min(100, int(queue_limit)))
        self.session_limit = max(1, min(10, int(session_queue_limit)))
        self.wait_seconds = max(1, min(600, float(wait_seconds)))
        self.chat_capacity = max(1, min(4, int(chat_concurrency)))
        self.media_capacity = max(1, min(2, int(media_concurrency)))
        self.maintenance_capacity = max(1, min(2, int(maintenance_concurrency)))
        self.media_queue_limit = max(1, min(32, int(media_queue_limit)))
        self.maintenance_queue_limit = max(1, min(32, int(maintenance_queue_limit)))
        self.heavy_capacity = max(1, min(2, int(heavy_concurrency)))
        self._chat = asyncio.Semaphore(self.chat_capacity)
        self._media = asyncio.Semaphore(self.media_capacity)
        self._maintenance = asyncio.Semaphore(self.maintenance_capacity)
        self._heavy = asyncio.Semaphore(self.heavy_capacity)
        self._media_owner = set()
        self._maintenance_owner = set()
        self._heavy_owner = None
        self._waiters = Counter()
        self._holders = set()
        self._waiting_tasks = set()
        self._resource_waiting = set()
        self._heavy_waiting = set()
        self._media_waiters = 0
        self._maintenance_waiters = 0
        self._closed = False
        self.rejected = 0
        self.resource_rejected = 0

    def configure(
        self,
        *,
        queue_limit=None,
        session_queue_limit=None,
        wait_seconds=None,
        chat_concurrency=None,
        media_concurrency=None,
        maintenance_concurrency=None,
        media_queue_limit=None,
        maintenance_queue_limit=None,
    ) -> None:
        """Apply new limits while preserving active holders and waiters."""
        if queue_limit is not None:
            self.queue_limit = max(1, min(100, int(queue_limit)))
        if session_queue_limit is not None:
            self.session_limit = max(1, min(10, int(session_queue_limit)))
        if wait_seconds is not None:
            self.wait_seconds = max(1, min(600, float(wait_seconds)))
        if media_queue_limit is not None:
            self.media_queue_limit = max(1, min(32, int(media_queue_limit)))
        if maintenance_queue_limit is not None:
            self.maintenance_queue_limit = max(1, min(32, int(maintenance_queue_limit)))
        self._resize_semaphore("chat", chat_concurrency)
        self._resize_semaphore("media", media_concurrency)
        self._resize_semaphore("maintenance", maintenance_concurrency)

    def _resize_semaphore(self, kind: str, requested) -> None:
        if requested is None:
            return
        cap_attr = "chat_capacity" if kind == "chat" else f"{kind}_capacity"
        sem_attr = "_chat" if kind == "chat" else f"_{kind}"
        old_capacity = int(getattr(self, cap_attr))
        new_capacity = max(1, min(4 if kind == "chat" else 2, int(requested)))
        if new_capacity == old_capacity:
            return
        active = old_capacity - getattr(getattr(self, sem_attr), "_value", old_capacity)
        # Raising permits only; lowering removes currently free permits and does
        # not revoke work already holding a ticket.
        target_free = max(0, new_capacity - active)
        current_free = getattr(getattr(self, sem_attr), "_value", old_capacity)
        delta = target_free - current_free
        for _ in range(max(0, delta)):
            getattr(self, sem_attr).release()
        for _ in range(max(0, -delta)):
            try:
                getattr(self, sem_attr).acquire_nowait()
            except AttributeError:
                pass
        setattr(self, cap_attr, new_capacity)

    def status(self):
        return {
            "running": len(self._holders),
            "waiting": sum(self._waiters.values()),
            "chat_capacity": self.chat_capacity,
            "media_running": self._media_capacity_running(),
            "media_waiting": self._media_waiters,
            "media_queue_limit": self.media_queue_limit,
            "maintenance_running": self._maintenance_capacity_running(),
            "maintenance_waiting": self._maintenance_waiters,
            "maintenance_queue_limit": self.maintenance_queue_limit,
            "heavy_running": self.heavy_capacity - getattr(self._heavy, "_value", self.heavy_capacity),
            "rejected": self.rejected,
            "resource_rejected": self.resource_rejected,
        }

    def _media_capacity_running(self) -> int:
        return self.media_capacity - getattr(self._media, "_value", self.media_capacity)

    def _maintenance_capacity_running(self) -> int:
        return self.maintenance_capacity - getattr(self._maintenance, "_value", self.maintenance_capacity)

    async def admit_pipeline(self, event):
        task = asyncio.current_task()
        if task in self._holders:
            return True
        scope = str(event.unified_msg_origin)
        if (self._closed or sum(self._waiters.values()) >= self.queue_limit
                or self._waiters[scope] >= self.session_limit):
            self.rejected += 1
            event.stop_event()
            return False
        self._waiters[scope] += 1
        self._waiting_tasks.add(task)
        try:
            await asyncio.wait_for(self._chat.acquire(), timeout=self.wait_seconds)
        except TimeoutError:
            event.stop_event()
            self.rejected += 1
            return False
        except asyncio.CancelledError:
            event.stop_event()
            if self._closed:
                return False
            raise
        finally:
            self._waiting_tasks.discard(task)
            self._waiters[scope] -= 1
            if not self._waiters[scope]:
                del self._waiters[scope]
        if self._closed:
            self._chat.release()
            event.stop_event()
            return False
        self._holders.add(task)
        task.add_done_callback(self._release)
        return True

    def _release(self, task):
        if task in self._holders:
            self._holders.remove(task)
            self._chat.release()

    async def _acquire_heavy(self) -> bool:
        task = asyncio.current_task()
        if self._heavy_owner is task:
            return False
        if self._closed:
            raise RuntimeError("知伴正在停止")
        self._heavy_waiting.add(task)
        try:
            await asyncio.wait_for(self._heavy.acquire(), timeout=self.wait_seconds)
        except TimeoutError as exc:
            self.resource_rejected += 1
            raise RuntimeError("重资源等待超时") from exc
        finally:
            self._heavy_waiting.discard(task)
        self._heavy_owner = task
        return True

    def _release_heavy(self, acquired: bool) -> None:
        if not acquired:
            return
        task = asyncio.current_task()
        if self._heavy_owner is task:
            self._heavy_owner = None
            self._heavy.release()

    async def _acquire_resource(self, kind: str, semaphore, owner_attr: str) -> None:
        task = asyncio.current_task()
        if task in getattr(self, owner_attr):
            return
        waiters_attr = f"_{kind}_waiters"
        limit = getattr(self, f"{kind}_queue_limit")
        if self._closed or getattr(self, waiters_attr) >= limit:
            self.resource_rejected += 1
            raise RuntimeError(f"{kind} 资源队列已满或正在停止")
        setattr(self, waiters_attr, getattr(self, waiters_attr) + 1)
        self._resource_waiting.add(task)
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=self.wait_seconds)
        except TimeoutError as exc:
            self.resource_rejected += 1
            raise RuntimeError(f"{kind} 资源等待超时") from exc
        finally:
            self._resource_waiting.discard(task)
            setattr(self, waiters_attr, getattr(self, waiters_attr) - 1)
        if self._closed:
            semaphore.release()
            raise RuntimeError("知伴正在停止")

    @asynccontextmanager
    async def media(self):
        """Media work with a bounded queue and shared heavy-resource budget."""
        task = asyncio.current_task()
        if task in self._media_owner:
            yield
            return
        await self._acquire_resource("media", self._media, "_media_owner")
        self._media_owner.add(task)
        heavy = False
        try:
            heavy = await self._acquire_heavy()
            yield
        finally:
            self._release_heavy(heavy)
            self._media_owner.discard(task)
            self._media.release()

    @asynccontextmanager
    async def maintenance(self):
        """Indexing/cleanup work that must not overlap other heavy jobs."""
        task = asyncio.current_task()
        if task in self._maintenance_owner:
            yield
            return
        await self._acquire_resource("maintenance", self._maintenance, "_maintenance_owner")
        self._maintenance_owner.add(task)
        heavy = False
        try:
            heavy = await self._acquire_heavy()
            yield
        finally:
            self._release_heavy(heavy)
            self._maintenance_owner.discard(task)
            self._maintenance.release()

    async def close(self):
        self._closed = True
        pending = tuple(self._waiting_tasks | self._resource_waiting | self._heavy_waiting)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
