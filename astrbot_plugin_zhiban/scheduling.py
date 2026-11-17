"""有界准入；持有票据到原 AstrBot 流水线真正结束，而非到 Agent 返回。"""
from __future__ import annotations

import asyncio
from collections import Counter, deque
from contextlib import asynccontextmanager


class _Waiter:
    __slots__ = ("future", "granted")

    def __init__(self, future):
        self.future = future
        self.granted = False


class DynamicLimiter:
    """FIFO async limiter whose capacity can change without swapping pools."""

    def __init__(self, capacity):
        self.capacity = max(1, int(capacity))
        self._active = 0
        self._waiters = deque()
        self._closed = False

    @property
    def active(self):
        return self._active

    @property
    def available(self):
        return max(0, self.capacity - self._active)

    @property
    def waiting(self):
        return sum(1 for waiter in self._waiters if not waiter.future.done())

    @property
    def _value(self):
        """Compatibility view for callers that inspected Semaphore._value."""
        return self.available

    def locked(self):
        return self.available == 0

    async def acquire(self, timeout=None):
        task = asyncio.current_task()
        if self._closed:
            raise RuntimeError("limiter is closed")
        if self._active < self.capacity and not self._waiters:
            self._active += 1
            return

        loop = asyncio.get_running_loop()
        waiter = _Waiter(loop.create_future())
        self._waiters.append(waiter)
        self._wake()

        timed_out = False
        timer = None

        def _on_timeout():
            nonlocal timed_out
            if not waiter.future.done():
                timed_out = True
                waiter.future.cancel()

        if timeout is not None:
            timer = loop.call_later(float(timeout), _on_timeout)
        try:
            try:
                await waiter.future
            except asyncio.CancelledError:
                if not waiter.granted:
                    self._abandon(waiter)
                if timed_out:
                    raise TimeoutError from None
                raise
            except BaseException:
                self._abandon(waiter)
                raise
            # A granted waiter owns a permit even before its task resumes. The
            # owner/ holder is registered synchronously immediately after this
            # method returns, so a yield here cannot change the permit count.
            await asyncio.sleep(0)
        finally:
            if timer is not None:
                timer.cancel()

    def release(self):
        if self._active <= 0:
            raise RuntimeError("release without an active permit")
        self._active -= 1
        self._wake()

    def set_capacity(self, capacity):
        new_capacity = max(1, int(capacity))
        if new_capacity == self.capacity:
            return
        self.capacity = new_capacity
        self._wake()

    def close(self):
        self._closed = True
        for waiter in tuple(self._waiters):
            if not waiter.future.done():
                waiter.future.cancel()

    def _wake(self):
        if self._closed:
            return
        while self._waiters and self._active < self.capacity:
            waiter = self._waiters.popleft()
            if waiter.future.done():
                continue
            waiter.granted = True
            self._active += 1
            waiter.future.set_result(True)

    def _abandon(self, waiter):
        try:
            self._waiters.remove(waiter)
        except ValueError:
            pass
        if waiter.granted:
            waiter.granted = False
            self._active -= 1
            self._wake()


class BudgetScheduler:
    """Small in-process budget for chat, media and maintenance work.

    Chat admission is counted per conversation and held until the pipeline task
    ends. Media and maintenance share one heavy-resource limiter so two
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
        self._chat = DynamicLimiter(self.chat_capacity)
        self._media = DynamicLimiter(self.media_capacity)
        self._maintenance = DynamicLimiter(self.maintenance_capacity)
        self._heavy = DynamicLimiter(self.heavy_capacity)
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
        self._set_capacity("chat", chat_concurrency)
        self._set_capacity("media", media_concurrency)
        self._set_capacity("maintenance", maintenance_concurrency)

    def _set_capacity(self, kind: str, requested) -> None:
        if requested is None:
            return
        maximum = 4 if kind == "chat" else 2
        capacity = max(1, min(maximum, int(requested)))
        setattr(self, f"{kind}_capacity", capacity)
        getattr(self, f"_{kind}").set_capacity(capacity)

    def status(self):
        return {
            "running": len(self._holders),
            "waiting": sum(self._waiters.values()),
            "chat_capacity": self.chat_capacity,
            "media_running": self._media.active,
            "media_waiting": self._media_waiters,
            "media_queue_limit": self.media_queue_limit,
            "maintenance_running": self._maintenance.active,
            "maintenance_waiting": self._maintenance_waiters,
            "maintenance_queue_limit": self.maintenance_queue_limit,
            "heavy_running": self._heavy.active,
            "rejected": self.rejected,
            "resource_rejected": self.resource_rejected,
        }

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
            await self._chat.acquire(timeout=self.wait_seconds)
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
            await self._heavy.acquire(timeout=self.wait_seconds)
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

    async def _acquire_resource(self, kind: str, limiter: DynamicLimiter, owner_attr: str) -> None:
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
            await limiter.acquire(timeout=self.wait_seconds)
        except TimeoutError as exc:
            self.resource_rejected += 1
            raise RuntimeError(f"{kind} 资源等待超时") from exc
        finally:
            self._resource_waiting.discard(task)
            setattr(self, waiters_attr, getattr(self, waiters_attr) - 1)
        if self._closed:
            limiter.release()
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
        for limiter in (self._chat, self._media, self._maintenance, self._heavy):
            limiter.close()
        pending = tuple(self._waiting_tasks | self._resource_waiting | self._heavy_waiting)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)