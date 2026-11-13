"""有界准入；持有票据到原 AstrBot 流水线真正结束，而非到 Agent 返回。"""
from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import asynccontextmanager


class BudgetScheduler:
    def __init__(self, queue_limit=20, session_queue_limit=4, wait_seconds=90):
        self.queue_limit = max(1, min(100, int(queue_limit)))
        self.session_limit = max(1, min(10, int(session_queue_limit)))
        self.wait_seconds = max(1, min(600, float(wait_seconds)))
        self._chat = asyncio.Lock()
        self._media = asyncio.Lock()
        self._media_owner = None
        self._waiters = Counter()
        self._holders = set()
        self._waiting_tasks = set()
        self._closed = False
        self.rejected = 0

    def status(self):
        return {"running": len(self._holders), "waiting": sum(self._waiters.values()),
                "media_running": self._media.locked(), "rejected": self.rejected}

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

    @asynccontextmanager
    async def media(self):
        """任务内可重入，防工具又调用语音时递归申请同一把锁。"""
        task = asyncio.current_task()
        if self._media_owner is task:
            yield
            return
        async with self._media:
            if self._closed:
                raise RuntimeError("知伴正在停止")
            self._media_owner = task
            try:
                yield
            finally:
                self._media_owner = None

    async def close(self):
        self._closed = True
        for task in tuple(self._waiting_tasks):
            task.cancel()
        if self._waiting_tasks:
            await asyncio.gather(*tuple(self._waiting_tasks), return_exceptions=True)
