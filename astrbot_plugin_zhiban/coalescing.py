"""Pre-admission coalescing for consecutive ordinary chat text.

This layer only joins plain text events from the same conversation and sender.
It does not sleep while holding the chat budget lock, and it never stores media
bytes. Commands, mentions, replies and events already debounced by AngelHeart
are intentionally left untouched.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Batch:
    key: str
    texts: list[str] = field(default_factory=list)
    message_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)
    last_at: float = field(default_factory=time.monotonic)
    signal: asyncio.Event = field(default_factory=asyncio.Event)
    chars: int = 0


class MessageCoalescer:
    """Bounded, in-memory consecutive-message merger."""

    def __init__(
        self,
        *,
        quiet_seconds: float = 1.5,
        max_seconds: float = 5.0,
        max_messages: int = 8,
        max_chars: int = 2000,
    ):
        self.quiet_seconds = max(0.05, min(10.0, float(quiet_seconds)))
        self.max_seconds = max(self.quiet_seconds, min(30.0, float(max_seconds)))
        self.max_messages = max(2, min(32, int(max_messages)))
        self.max_chars = max(100, min(20000, int(max_chars)))
        self._batches: dict[str, _Batch] = {}
        self._lock = asyncio.Lock()
        self._closed = False
        self.coalesced_messages = 0
        self.flushed_batches = 0
        self.dropped_events = 0

    async def join(self, key: str, text: str, message_id: str = "") -> tuple[bool, str, list[str]]:
        """Join a message.

        Returns ``(leader, merged_text, message_ids)``. Only the leader waits for
        the quiet window and is allowed to continue to admission. Followers get
        ``(False, "", [])`` and must stop their event.
        """
        text = str(text or "").strip()
        if not text or self._closed:
            return True, text, [message_id] if message_id else []
        now = time.monotonic()
        leader = False
        async with self._lock:
            batch = self._batches.get(key)
            if batch is None:
                batch = _Batch(key=key, created_at=now, last_at=now)
                self._batches[key] = batch
                leader = True
            batch.texts.append(text)
            if message_id:
                batch.message_ids.append(str(message_id))
            batch.chars += len(text)
            batch.last_at = now
            if not leader:
                batch.signal.set()
                return False, "", []

        try:
            while True:
                async with self._lock:
                    current = self._batches.get(key)
                    if current is not batch or self._closed:
                        break
                    now = time.monotonic()
                    quiet_deadline = batch.last_at + self.quiet_seconds
                    hard_deadline = batch.created_at + self.max_seconds
                    remaining = min(quiet_deadline, hard_deadline) - now
                    if (
                        remaining <= 0
                        or len(batch.texts) >= self.max_messages
                        or batch.chars >= self.max_chars
                    ):
                        break
                try:
                    await asyncio.wait_for(batch.signal.wait(), timeout=remaining)
                    batch.signal.clear()
                except TimeoutError:
                    break
            async with self._lock:
                if self._batches.get(key) is batch:
                    self._batches.pop(key, None)
                merged = "\n".join(part for part in batch.texts if part)
                ids = list(batch.message_ids)
                self.flushed_batches += 1
                self.coalesced_messages += max(0, len(batch.texts) - 1)
                return True, merged, ids
        except asyncio.CancelledError:
            async with self._lock:
                if self._batches.get(key) is batch:
                    self._batches.pop(key, None)
                self.dropped_events += len(batch.texts)
            raise

    async def close(self):
        async with self._lock:
            self._closed = True
            for batch in self._batches.values():
                batch.signal.set()
            self._batches.clear()

    def status(self) -> dict[str, Any]:
        return {
            "active_batches": len(self._batches),
            "queued_messages": sum(len(batch.texts) for batch in self._batches.values()),
            "queued_chars": sum(batch.chars for batch in self._batches.values()),
            "coalesced_messages": self.coalesced_messages,
            "flushed_batches": self.flushed_batches,
            "dropped_events": self.dropped_events,
            "quiet_ms": int(self.quiet_seconds * 1000),
            "max_ms": int(self.max_seconds * 1000),
            "max_messages": self.max_messages,
            "max_chars": self.max_chars,
        }
