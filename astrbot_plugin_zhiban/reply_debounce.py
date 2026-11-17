"""Bounded draft-window reply debounce adapted from reply_merge 1.4.2.

The coordinator is deliberately not a Star plugin and registers no hooks. The
root plugin calls 'hold' from on_waiting_llm_request and 'merge_request' from
on_llm_request. This keeps one owner for reply coordination and lets the host's
existing scheduler remain authoritative.

Adapted from Ye1xiaotian/astrbot_plugin_reply_merge at commit
4efd25c2dd11ee09daca18f48989d8643c63f2bb (MIT). Draft text is transient: it
is never logged, persisted, or exposed as a user-visible command.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import random
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

_MARKER_RE = re.compile(r"<<\s*(reply|wait)\s*(\d{1,3})?\s*>>", re.IGNORECASE)
_TRUNCATED = "…[已截断]"
_ORPHAN_OMITTED = "[另有补充消息因窗口容量上限未展开]"
_COMMAND_PREFIXES = ("/", "!", "#", ".")


def _as_float(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        number = float(default)
    if number != number:
        number = float(default)
    return max(low, min(high, number))


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "启用", "开启"}:
            return True
        if text in {"0", "false", "no", "off", "禁用", "关闭"}:
            return False
    return bool(default if value is None else value)


def _as_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        number = int(default)
    return max(low, min(high, number))


def _utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _truncate_utf8(text: str, limit: int) -> str:
    """Truncate without splitting a UTF-8 code point."""

    limit = max(0, int(limit))
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    if limit <= 0:
        return ""
    marker = _TRUNCATED.encode("utf-8")
    if len(marker) >= limit:
        raw = marker[:limit]
        while raw:
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                raw = raw[:-1]
        return ""
    budget = limit - len(marker)
    raw = raw[:budget]
    while raw:
        try:
            prefix = raw.decode("utf-8")
            break
        except UnicodeDecodeError:
            raw = raw[:-1]
    else:
        prefix = ""
    return prefix.rstrip() + _TRUNCATED


def _bounded_text(text: str, max_chars: int, max_bytes: int) -> str:
    value = str(text or "")
    if len(value) > max_chars:
        if max_chars > len(_TRUNCATED):
            value = value[: max_chars - len(_TRUNCATED)].rstrip() + _TRUNCATED
        else:
            value = value[: max(0, max_chars)]
    return _truncate_utf8(value, max_bytes)


@dataclass(frozen=True)
class ReplyDebounceConfig:
    """Validated runtime limits; values are clamped in normalized()."""

    enabled: bool = True
    thinking: bool = True
    min_wait: float = 3.0
    max_wait: float = 8.0
    max_passes: int = 4
    max_followups: int = 8
    max_chars: int = 16 * 1024
    max_bytes: int = 16 * 1024
    max_window: float = 30.0
    draft_timeout: float = 20.0
    draft_concurrency: int = 1
    settle: float = 0.8
    reply_pause: float = 1.5
    max_draft_chars: int = 1200
    max_images: int = 8
    forward_images: bool = True
    think_provider_id: str = ""
    think_style: str = ""
    think_voice: str = "human"
    think_context: bool = True
    think_context_chars: int = 4000
    active_limit: int = 128
    orphan_limit: int = 64
    orphan_ttl: float = 300.0
    orphan_grace: float = 5.0

    @classmethod
    def normalized(cls, values: dict[str, Any] | None = None) -> "ReplyDebounceConfig":
        source = dict(values or {})
        defaults = cls()
        min_wait = _as_float(source.get("min_wait"), defaults.min_wait, 0.01, 10.0)
        max_wait = _as_float(source.get("max_wait"), defaults.max_wait, min_wait, 20.0)
        max_window = _as_float(
            source.get("max_window"), defaults.max_window, 0.01, 60.0
        )
        max_window = max(max_window, min_wait)
        return cls(
            enabled=_as_bool(source.get("enabled"), defaults.enabled),
            thinking=_as_bool(source.get("thinking"), defaults.thinking),
            min_wait=min_wait,
            max_wait=max(max_wait, min_wait),
            max_passes=_as_int(source.get("max_passes"), defaults.max_passes, 1, 6),
            max_followups=_as_int(
                source.get("max_followups"), defaults.max_followups, 1, 16
            ),
            max_chars=_as_int(
                source.get("max_chars"), defaults.max_chars, 64, 32 * 1024
            ),
            max_bytes=_as_int(
                source.get("max_bytes"), defaults.max_bytes, 64, 32 * 1024
            ),
            max_window=max_window,
            draft_timeout=_as_float(
                source.get("draft_timeout"), defaults.draft_timeout, 0.01, 30.0
            ),
            draft_concurrency=_as_int(
                source.get("draft_concurrency"), defaults.draft_concurrency, 1, 2
            ),
            settle=_as_float(source.get("settle"), defaults.settle, 0.0, 2.0),
            reply_pause=_as_float(
                source.get("reply_pause"), defaults.reply_pause, 0.0, 5.0
            ),
            max_draft_chars=_as_int(
                source.get("max_draft_chars"),
                defaults.max_draft_chars,
                64,
                2000,
            ),
            max_images=_as_int(source.get("max_images"), defaults.max_images, 0, 12),
            forward_images=_as_bool(source.get("forward_images"), defaults.forward_images),
            think_provider_id=str(
                source.get("think_provider_id", defaults.think_provider_id) or ""
            ).strip()[:128],
            think_style=str(
                source.get("think_style", defaults.think_style) or ""
            ).strip()[:2000],
            think_voice=(
                "structured"
                if str(
                    source.get("think_voice", defaults.think_voice) or ""
                ).strip().lower()
                == "structured"
                else "human"
            ),
            think_context=_as_bool(source.get("think_context"), defaults.think_context),
            think_context_chars=_as_int(
                source.get("think_context_chars"),
                defaults.think_context_chars,
                512,
                12000,
            ),
            active_limit=_as_int(
                source.get("active_limit"), defaults.active_limit, 1, 256
            ),
            orphan_limit=_as_int(
                source.get("orphan_limit"), defaults.orphan_limit, 1, 128
            ),
            orphan_ttl=_as_float(
                source.get("orphan_ttl"), defaults.orphan_ttl, 0.01, 600.0
            ),
            orphan_grace=_as_float(
                source.get("orphan_grace"), defaults.orphan_grace, 0.0, 30.0
            ),
        )


@dataclass
class _Verdict:
    action: str
    wait: float
    thought: str = ""
    fallback: bool = False


@dataclass
class _Window:
    key: str
    first_message: str
    leader_order: tuple[int, int, int]
    created_at: float
    last_activity: float
    hard_cap: float
    deadline: float
    nonce: str
    leader_event: Any
    wakeup: asyncio.Event = field(default_factory=asyncio.Event)
    buffer: list[tuple[tuple[int, int, int], str]] = field(default_factory=list)
    followup_count: int = 0
    images: list[str] = field(default_factory=list)
    earlier: list[str] = field(default_factory=list)
    earlier_count: int = 0
    thoughts: list[_Verdict] = field(default_factory=list)
    waits: list[float] = field(default_factory=list)
    passes: int = 0
    bytes_used: int = 0
    omitted: int = 0
    force_close: bool = False
    rescued: bool = False
    parked_at: float = 0.0
    chars_used: int = 0
    context_block: str | None = None
    style_context: str | None = None


UsageRecorder = Callable[..., Any]


class _MeteredProvider:
    """Transparent provider wrapper that meters every draft response."""

    def __init__(
        self,
        provider: Any,
        *,
        event: Any,
        recorder: UsageRecorder | None,
        on_metered: Callable[[bool], None],
    ) -> None:
        self._provider = provider
        self._event = event
        self._recorder = recorder
        self._on_metered = on_metered

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)

    async def text_chat(self, *args: Any, **kwargs: Any) -> Any:
        response = await self._provider.text_chat(*args, **kwargs)
        if self._recorder is None:
            self._on_metered(False)
            return response
        status = "failed" if getattr(response, "role", "") == "err" else "completed"
        try:
            result = self._recorder(
                self._event,
                response,
                source="reply_debounce",
                status=status,
                is_final=False,
            )
            if inspect.isawaitable(result):
                await result
            self._on_metered(True)
        except Exception:
            # Accounting must never turn a usable draft into a reply failure.
            self._on_metered(False)
        return response


class ReplyDebounceCoordinator:
    """One bounded draft window per private user and conversation."""

    def __init__(
        self,
        context: Any,
        *,
        config: ReplyDebounceConfig | dict[str, Any] | None = None,
        usage_recorder: UsageRecorder | None = None,
        style_provider: Callable[[Any], Any] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._context = context
        self._usage_recorder = usage_recorder
        self._style_provider = style_provider
        self._rng = rng or random.Random()
        if isinstance(config, ReplyDebounceConfig):
            self._config = config.normalized(asdict(config))
        else:
            self._config = ReplyDebounceConfig.normalized(config)
        self._pending: dict[str, _Window] = {}
        self._orphaned: dict[str, list[_Window]] = {}
        self._draft_tasks: set[asyncio.Task[Any]] = set()
        self._draft_slots = asyncio.Semaphore(self._config.draft_concurrency)
        self._closed = False
        self._closed_event = asyncio.Event()
        self._order = 0
        self.draft_calls = 0
        self.draft_failures = 0
        self.draft_timeouts = 0
        self.fallback_passes = 0
        self.metered_drafts = 0
        self.meter_failures = 0
        self.capacity_bypasses = 0
        self.rescued_windows = 0
        self.truncated_messages = 0
        self.omitted_messages = 0

    @property
    def config(self) -> ReplyDebounceConfig:
        return self._config

    def configure(self, **changes: Any) -> ReplyDebounceConfig:
        values = asdict(self._config)
        unknown = set(changes) - set(values)
        if unknown:
            raise ValueError(f"unknown reply debounce settings: {sorted(unknown)}")
        values.update(changes)
        updated = ReplyDebounceConfig.normalized(values)
        if updated.draft_concurrency != self._config.draft_concurrency:
            # Existing tasks keep the old semaphore; new tasks use the new one.
            self._draft_slots = asyncio.Semaphore(updated.draft_concurrency)
        self._config = updated
        return self._config

    def eligible(self, event: Any) -> bool:
        """Only private chat is owned here; group chat remains AngelHeart-owned."""

        if self._closed or not self._config.enabled:
            return False
        try:
            if not event.is_private_chat():
                return False
        except Exception:
            return False
        text = self._event_text(event).strip()
        if text.startswith(_COMMAND_PREFIXES) or text.startswith("知伴"):
            return False
        try:
            if event.is_stopped():
                return False
        except Exception:
            pass
        return True

    async def hold(
        self,
        event: Any,
        admit: Callable[[Any], Any] | None = None,
    ) -> bool:
        """Open or join a window; return whether this event may continue."""

        if self._closed:
            self._stop_event(event)
            return False
        if not self.eligible(event):
            return await self._admit(event, admit)

        key = self._merge_key(event)
        existing = self._pending.get(key)
        if existing is not None:
            self._donate(
                existing,
                self._arrival_key(event),
                self._event_text(event),
                self._extract_images(event),
            )
            self._stop_event(event)
            return False

        if len(self._pending) >= self._config.active_limit:
            self.capacity_bypasses += 1
            return await self._admit(event, admit)

        now = time.monotonic()
        quiet = self._random_wait()
        window = _Window(
            key=key,
            first_message=_bounded_text(
                self._event_text(event),
                self._config.max_chars,
                self._config.max_bytes,
            ),
            leader_order=self._arrival_key(event),
            created_at=now,
            last_activity=now,
            hard_cap=now + self._config.max_window,
            deadline=min(now + self._config.max_window, now + quiet),
            nonce=uuid.uuid4().hex[:8],
            leader_event=event,
            images=self._extract_images(event),
        )
        window.bytes_used = _utf8_len(window.first_message)
        window.chars_used = len(window.first_message)
        window.wakeup.set()
        self._rescue_older(window, now)
        self._pending[key] = window
        try:
            completed = await self._run_window(window)
        except asyncio.CancelledError:
            if not self._closed:
                self._park(window)
            self._stop_event(event)
            raise
        except Exception:
            if not self._closed:
                self._park(window)
            self._stop_event(event)
            return False
        finally:
            if self._pending.get(key) is window:
                self._pending.pop(key, None)

        if not completed or self._closed:
            self._stop_event(event)
            return False

        self._park(window)
        self._set_extra(event, "_zhiban_reply_window", window)
        if not await self._admit(event, admit):
            self._stop_event(event)
            return False
        return True

    async def merge_request(self, event: Any, request: Any) -> bool:
        """Inject one finished window into the final prompt."""

        window = self._get_extra(event, "_zhiban_reply_window")
        if not isinstance(window, _Window):
            # Some third-party runners do not fire the waiting hook. Degrade
            # to a bounded in-request window instead of silently skipping
            # debounce; the local runner normally never reaches this branch.
            if not self.eligible(event):
                return True
            if not await self.hold(event):
                return False
            window = self._get_extra(event, "_zhiban_reply_window")
            if not isinstance(window, _Window):
                return True
        self._set_extra(event, "_zhiban_reply_window", None)
        self._claim_orphan(window)
        if window.rescued:
            self._stop_event(event)
            return False
        try:
            original = (
                str(getattr(request, "prompt", "") or "").strip()
                or window.first_message
            )
            blocks = self._render_window(window, event, original)
            if blocks:
                request.prompt = "\n\n".join(blocks)
            if window.images:
                current = list(getattr(request, "image_urls", None) or [])
                for image in window.images[: self._config.max_images]:
                    if image and image not in current:
                        current.append(image)
                request.image_urls = current
        except Exception:
            # The normal reply must survive malformed requests.
            pass
        return True

    async def close(self) -> None:
        self._closed = True
        self._closed_event.set()
        for window in tuple(self._pending.values()):
            window.wakeup.set()
        self._pending.clear()
        self._orphaned.clear()
        tasks = tuple(self._draft_tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)

    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        self._prune_orphans(now)
        return {
            "closed": self._closed,
            "active_windows": len(self._pending),
            "orphan_windows": sum(len(items) for items in self._orphaned.values()),
            "orphan_bytes": sum(
                window.bytes_used
                for items in self._orphaned.values()
                for window in items
            ),
            "draft_calls": self.draft_calls,
            "draft_failures": self.draft_failures,
            "draft_timeouts": self.draft_timeouts,
            "fallback_passes": self.fallback_passes,
            "metered_drafts": self.metered_drafts,
            "meter_failures": self.meter_failures,
            "capacity_bypasses": self.capacity_bypasses,
            "rescued_windows": self.rescued_windows,
            "truncated_messages": self.truncated_messages,
            "omitted_messages": self.omitted_messages,
            "limits": asdict(self._config),
        }

    async def _run_window(self, window: _Window) -> bool:
        while True:
            if self._closed:
                return False
            if window.force_close:
                return True
            now = time.monotonic()
            if now >= window.hard_cap:
                return True

            if window.wakeup.is_set():
                window.wakeup.clear()
                if self._config.thinking and window.passes < self._config.max_passes:
                    remaining = max(0.0, window.hard_cap - now)
                    await self._wait_or_closed(min(self._config.settle, remaining))
                    if self._closed:
                        return False
                    window.passes += 1
                    verdict = await self._draft_with_timeout(window)
                    if verdict is None:
                        verdict = self._fallback_verdict("")
                    window.thoughts.append(verdict)
                    if verdict.action == "reply":
                        quiet = max(
                            self._config.reply_pause,
                            window.last_activity
                            + self._config.min_wait
                            - time.monotonic(),
                        )
                    else:
                        quiet = max(
                            self._config.min_wait,
                            min(self._config.max_wait, verdict.wait),
                        )
                    window.waits.append(quiet)
                    window.deadline = min(
                        window.hard_cap, time.monotonic() + quiet
                    )
                    continue

                quiet = self._random_wait()
                window.waits.append(quiet)
                window.deadline = min(window.hard_cap, time.monotonic() + quiet)

            remaining = window.deadline - time.monotonic()
            if remaining <= 0:
                return True
            try:
                await asyncio.wait_for(window.wakeup.wait(), remaining)
            except TimeoutError:
                return True

    async def _draft_with_timeout(self, window: _Window) -> _Verdict | None:
        self.draft_calls += 1
        task = asyncio.create_task(self._draft_in_slot(window))
        self._draft_tasks.add(task)
        try:
            return await asyncio.wait_for(task, timeout=self._config.draft_timeout)
        except TimeoutError:
            self.draft_timeouts += 1
            return None
        except asyncio.CancelledError:
            if self._closed:
                return None
            raise
        except Exception:
            self.draft_failures += 1
            return None
        finally:
            self._draft_tasks.discard(task)

    async def _draft_in_slot(self, window: _Window) -> _Verdict | None:
        async with self._draft_slots:
            return await self._draft(window)

    async def _draft(self, window: _Window) -> _Verdict | None:
        provider = await self._using_provider(window)
        if provider is None:
            return None
        wrapped = _MeteredProvider(
            provider,
            event=window.leader_event,
            recorder=self._usage_recorder,
            on_metered=self._record_meter_result,
        )
        if self._config.think_context and window.context_block is None:
            window.context_block = await self._history_block(window.leader_event)
        if window.style_context is None:
            window.style_context = await self._style_context(window.leader_event)
        prompt = self._draft_prompt(window)
        style = window.style_context
        response = await wrapped.text_chat(
            prompt=prompt,
            system_prompt=self._draft_system_prompt(style),
            image_urls=self._draft_images(provider, window),
        )
        raw = str(getattr(response, "completion_text", "") or "").strip()
        return self._parse_verdict(raw)

    async def _using_provider(self, window: _Window) -> Any:
        provider_id = self._config.think_provider_id
        if provider_id:
            getter = getattr(self._context, "get_provider_by_id", None)
            if callable(getter):
                try:
                    provider = getter(provider_id)
                    if inspect.isawaitable(provider):
                        provider = await provider
                    if provider is not None:
                        return provider
                except Exception:
                    pass
        getter = getattr(self._context, "get_using_provider_async", None)
        if callable(getter):
            try:
                return await getter(umo=window.key.rsplit("|", 1)[0])
            except TypeError:
                return await getter()
        getter = getattr(self._context, "get_using_provider", None)
        if callable(getter):
            result = getter(window.key.rsplit("|", 1)[0])
            if inspect.isawaitable(result):
                result = await result
            return result
        return None

    def _draft_system_prompt(self, style: str) -> str:
        if self._config.think_voice == "structured":
            base = (
                "你是聊天机器人的回复前草稿模块。用极简的结构化笔记记录："
                "对方还缺什么信息、是否适合现在回复。最后一行只给 "
                "<<reply>> 或 <<wait 秒数>>，不要解释规则。"
            )
        else:
            base = (
                "你是聊天机器人的回复前草稿模块。用第一人称写一两句简短的心里话，"
                "不要写分析报告。最后一行只给 <<reply>> 或 <<wait 秒数>>，不要解释规则。"
            )
        if style:
            return f"[语气设定]\n{style}\n\n{base}"
        return base

    def _draft_images(self, provider: Any, window: _Window) -> list[str]:
        if not window.images or not self._config.forward_images:
            return []
        config = getattr(provider, "provider_config", {}) or {}
        modalities = config.get("modalities") if isinstance(config, dict) else None
        sees_images = modalities == [] or (
            isinstance(modalities, list) and "image" in modalities
        )
        return window.images[: self._config.max_images] if sees_images else []

    async def _style_context(self, event: Any) -> str:
        if self._config.think_style:
            return self._config.think_style
        if self._style_provider is None:
            return ""
        try:
            value = self._style_provider(event)
            if inspect.isawaitable(value):
                value = await value
            return str(value or "").strip()[:2000]
        except Exception:
            return ""

    def _draft_prompt(self, window: _Window) -> str:
        lines = [
            "用户正在连续发消息。只根据下面内容判断是否适合现在回复。",
            f"首条：{window.first_message}",
        ]
        if window.context_block:
            lines.append("最近对话：\n" + window.context_block)
        if window.earlier:
            lines.append("更早未回复：\n" + "\n".join(window.earlier))
        if window.buffer:
            lines.append(
                "随后补充：\n"
                + "\n".join(f"- {text}" for _, text in sorted(window.buffer))
            )
        previous = ""
        for verdict in reversed(window.thoughts):
            if verdict.thought:
                previous = verdict.thought
                break
        if previous:
            lines.append(f"你上一轮草稿：{previous}")
        lines.append(
            "如果用户明显说完，最后一行写 <<reply>>；否则写 <<wait N>>，"
            "N 是 1 到 999 的整数。"
        )
        return "\n\n".join(lines)

    async def _history_block(self, event: Any) -> str:
        """Read a small tail of history for the draft, never for persistence."""

        manager = getattr(self._context, "conversation_manager", None)
        if manager is None:
            return ""
        try:
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            if not umo:
                return ""
            conversation_id = await manager.get_curr_conversation_id(umo)
            if not conversation_id:
                return ""
            conversation = await manager.get_conversation(umo, conversation_id)
            raw = getattr(conversation, "history", "") if conversation is not None else ""
            history = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return ""
        if not isinstance(history, list):
            return ""
        labels = "群友" if not self._is_private(event) else "对方"
        lines: list[str] = []
        for item in history[-8:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = item.get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                pieces: list[str] = []
                for part in content:
                    if isinstance(part, str):
                        pieces.append(part)
                    elif isinstance(part, dict):
                        value = part.get("text")
                        if isinstance(value, str) and value.strip():
                            pieces.append(value)
                        elif part.get("type") == "image_url":
                            pieces.append("[图片]")
                text = "\n".join(pieces)
            else:
                text = ""
            text = text.split("[以下是", 1)[0]
            text = " / ".join(
                line.strip() for line in text.splitlines() if line.strip()
            )
            if not text:
                continue
            if len(text) > 800:
                text = text[:800].rstrip() + "…"
            lines.append(f"{labels if role == 'user' else '你'}：{text}")
        if not lines:
            return ""
        return _truncate_utf8(
            "\n".join(lines), self._config.think_context_chars
        )

    @staticmethod
    def _is_private(event: Any) -> bool:
        try:
            return bool(event.is_private_chat())
        except Exception:
            return True

    def _parse_verdict(self, raw: str) -> _Verdict:
        thought = _truncate_utf8(raw.strip(), self._config.max_draft_chars)
        matches = list(_MARKER_RE.finditer(raw))
        if not matches:
            return self._fallback_verdict(thought)
        marker = matches[-1]
        thought = _truncate_utf8(
            raw[: marker.start()].strip(), self._config.max_draft_chars
        )
        action = marker.group(1).lower()
        if action == "reply":
            return _Verdict("reply", 0.0, thought)
        try:
            wait = float(marker.group(2) or "")
        except (TypeError, ValueError):
            return self._fallback_verdict(thought)
        if not (0 < wait < 3600):
            return self._fallback_verdict(thought)
        return _Verdict("wait", wait, thought)

    def _fallback_verdict(self, thought: str) -> _Verdict:
        self.fallback_passes += 1
        return _Verdict("wait", self._random_wait(), thought, fallback=True)

    def _random_wait(self) -> float:
        return self._rng.uniform(self._config.min_wait, self._config.max_wait)

    def _donate(
        self,
        window: _Window,
        order: tuple[int, int, int],
        text: str,
        images: list[str],
    ) -> None:
        window.last_activity = time.monotonic()
        window.wakeup.set()
        if window.omitted:
            window.omitted += 1
            self.omitted_messages += 1
            window.force_close = True
            return
        if window.followup_count >= self._config.max_followups:
            window.omitted += 1
            self.omitted_messages += 1
            window.force_close = True
            return
        window.followup_count += 1
        available_chars = self._config.max_chars - window.chars_used
        available_bytes = self._config.max_bytes - window.bytes_used
        if available_chars <= 0 or available_bytes <= 0:
            window.omitted += 1
            self.omitted_messages += 1
            window.force_close = True
            return
        normalized = text.strip()
        bounded = _bounded_text(normalized, available_chars, available_bytes)
        if bounded != normalized:
            self.truncated_messages += 1
            window.force_close = True
        normalized = bounded
        if normalized:
            window.buffer.append((order, normalized))
            window.bytes_used += _utf8_len(normalized)
            window.chars_used += len(normalized)
        if window.followup_count >= self._config.max_followups:
            window.force_close = True
        if (
            window.chars_used >= self._config.max_chars
            or window.bytes_used >= self._config.max_bytes
        ):
            window.force_close = True
        remaining_images = max(0, self._config.max_images - len(window.images))
        if self._config.forward_images and remaining_images:
            for image in images:
                if image and image not in window.images and remaining_images:
                    window.images.append(image)
                    remaining_images -= 1

    def _render_window(
        self, window: _Window, event: Any, leader_text: str
    ) -> list[str]:
        ordered = sorted(window.buffer, key=lambda item: item[0])
        before = [text for order, text in ordered if order < window.leader_order]
        after = [text for order, text in ordered if order >= window.leader_order]
        speaker = " ".join(str(self._sender_name(event) or "").split())[:20].strip()
        who = f"这位用户（{speaker}）" if speaker else "这位用户"
        nonce = window.nonce
        earlier_block = ""
        if window.earlier:
            earlier_block = (
                f"[以下是{who}更早发来、但上一轮没能回复的内容"
                f"（校验码 {nonce}），也请一并回应]\n"
                + "\n".join(window.earlier)
            )
        before_block = ""
        if before:
            before_block = (
                f"[以下是{who}在最后一条消息之前先发出的内容"
                f"（校验码 {nonce}），请按时间顺序理解]\n"
                + "\n".join(f"- {text}" for text in before)
            )
        thought = ""
        for verdict in reversed(window.thoughts):
            if verdict.thought:
                thought = verdict.thought
                break
        thought_block = ""
        if thought:
            thought_block = (
                f"[以下是你在回复前对{who}这句话的内部草稿"
                f"（校验码 {nonce}），帮助理解语境；不要提及或复述]\n{thought}"
            )
        after_block = ""
        if after:
            shown = after
            if window.omitted:
                shown = [f"- ……（前面还有 {window.omitted} 条未展开）", *shown]
            after_block = (
                f"[以下是{who}在这条消息之后紧接着连发的后续内容"
                f"（校验码 {nonce}），请合并理解并只回复一次]\n"
                + "\n".join(f"- {text}" for text in shown)
            )
        elif window.omitted:
            after_block = (
                f"[{_ORPHAN_OMITTED}（校验码 {nonce}，共 {window.omitted} 条）]"
            )

        if before:
            leader_block = (
                f"[以下是{who}最后发来的一条消息（校验码 {nonce}）]\n{leader_text}"
            )
            blocks = [earlier_block, before_block, leader_block, thought_block, after_block]
        else:
            blocks = [leader_text, thought_block, earlier_block, after_block]
        return [block for block in blocks if block]

    def _rescue_older(self, window: _Window, now: float) -> None:
        items = self._orphaned.get(window.key, [])
        if not items:
            return
        remaining: list[_Window] = []
        for old in items:
            if old.rescued or now - old.parked_at > self._config.orphan_ttl:
                continue
            if now - old.parked_at < self._config.orphan_grace:
                remaining.append(old)
                continue
            moved: list[str] = []
            if old.first_message:
                moved.append(f"- {old.first_message}")
            moved.extend(f"- {text}" for _, text in sorted(old.buffer))
            moved.extend(old.earlier)
            if moved:
                for line in moved:
                    remaining_chars = self._config.max_chars - window.chars_used
                    remaining_bytes = self._config.max_bytes - window.bytes_used
                    if remaining_chars <= 0 or remaining_bytes <= 0:
                        window.omitted += 1
                        break
                    line = _bounded_text(line, remaining_chars, remaining_bytes)
                    window.earlier.append(line)
                    window.bytes_used += _utf8_len(line)
                    window.chars_used += len(line)
                    window.earlier_count += 1
            for image in old.images:
                if image not in window.images and len(window.images) < self._config.max_images:
                    window.images.append(image)
            old.rescued = True
            old.buffer.clear()
            old.earlier.clear()
            old.thoughts.clear()
            old.first_message = ""
            old.images.clear()
            self.rescued_windows += 1
        if remaining:
            self._orphaned[window.key] = remaining
        else:
            self._orphaned.pop(window.key, None)

    def _park(self, window: _Window) -> None:
        if self._closed or window.rescued:
            return
        if not (
            window.first_message
            or window.buffer
            or window.earlier
            or window.images
        ):
            return
        items = self._orphaned.setdefault(window.key, [])
        if any(item is window for item in items):
            return
        window.parked_at = time.monotonic()
        items.append(window)
        self._trim_orphans()

    def _claim_orphan(self, window: _Window) -> None:
        items = self._orphaned.get(window.key, [])
        remaining = [item for item in items if item is not window]
        if remaining:
            self._orphaned[window.key] = remaining
        else:
            self._orphaned.pop(window.key, None)

    def _trim_orphans(self) -> None:
        self._prune_orphans(time.monotonic())
        while self._orphan_count() > self._config.orphan_limit:
            oldest: tuple[str, _Window] | None = None
            for key, items in self._orphaned.items():
                for item in items:
                    if oldest is None or item.parked_at < oldest[1].parked_at:
                        oldest = (key, item)
            if oldest is None:
                return
            key, item = oldest
            self._orphaned[key] = [
                value for value in self._orphaned[key] if value is not item
            ]
            if not self._orphaned[key]:
                self._orphaned.pop(key, None)

    def _prune_orphans(self, now: float) -> None:
        for key in tuple(self._orphaned):
            kept = [
                item
                for item in self._orphaned[key]
                if now - item.parked_at <= self._config.orphan_ttl
            ]
            if kept:
                self._orphaned[key] = kept
            else:
                self._orphaned.pop(key, None)

    def _orphan_count(self) -> int:
        return sum(len(items) for items in self._orphaned.values())

    def _record_meter_result(self, recorded: bool) -> None:
        if recorded:
            self.metered_drafts += 1
        else:
            self.meter_failures += 1

    async def _admit(
        self, event: Any, admit: Callable[[Any], Any] | None
    ) -> bool:
        if admit is None:
            return True
        try:
            result = admit(event)
            if inspect.isawaitable(result):
                result = await result
        except asyncio.CancelledError:
            raise
        except Exception:
            self._stop_event(event)
            return False
        if not result:
            self._stop_event(event)
            return False
        return True

    async def _wait_or_closed(self, seconds: float) -> None:
        if seconds <= 0:
            return
        sleep_task = asyncio.create_task(asyncio.sleep(seconds))
        closed_task = asyncio.create_task(self._closed_event.wait())
        try:
            await asyncio.wait(
                (sleep_task, closed_task), return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for task in (sleep_task, closed_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(sleep_task, closed_task, return_exceptions=True)

    def _merge_key(self, event: Any) -> str:
        try:
            sender = str(event.get_sender_id() or "")
        except Exception:
            sender = ""
        return f"{event.unified_msg_origin}|{sender}"

    def _next_order(self) -> int:
        self._order += 1
        return self._order

    def _arrival_key(self, event: Any) -> tuple[int, int, int]:
        raw = getattr(getattr(event, "message_obj", None), "raw_message", None)
        platform_time = 0
        platform_seq = 0
        if raw is not None:
            for attr in ("time", "timestamp"):
                value = getattr(raw, attr, None)
                if isinstance(value, int):
                    platform_time = value
                    break
            value = getattr(raw, "message_seq", None)
            if isinstance(value, int):
                platform_seq = value
        if not platform_time:
            platform_time = int(
                getattr(getattr(event, "message_obj", None), "timestamp", 0) or 0
            )
        return platform_time, platform_seq, self._next_order()

    def _event_text(self, event: Any) -> str:
        getter = getattr(event, "get_message_str", None)
        if callable(getter):
            try:
                value = getter()
                if value:
                    return str(value)
            except Exception:
                pass
        value = getattr(event, "message_str", "")
        if value:
            return str(value)
        getter = getattr(event, "get_message_outline", None)
        if callable(getter):
            try:
                return str(getter() or "")
            except Exception:
                pass
        return ""

    def _messages(self, event: Any) -> list[Any]:
        getter = getattr(event, "get_messages", None)
        if callable(getter):
            try:
                return list(getter() or [])
            except Exception:
                pass
        chain = getattr(getattr(event, "message_obj", None), "message", None)
        return list(chain or [])

    def _extract_images(self, event: Any) -> list[str]:
        images: list[str] = []
        for component in self._messages(event):
            name = type(component).__name__.lower()
            if "image" not in name:
                continue
            source = str(
                getattr(component, "url", "") or getattr(component, "file", "") or ""
            ).strip()
            if source and source not in images:
                images.append(source)
            if len(images) >= self._config.max_images:
                break
        return images

    def _sender_name(self, event: Any) -> str:
        getter = getattr(event, "get_sender_name", None)
        if callable(getter):
            try:
                return str(getter() or "")
            except Exception:
                pass
        return ""

    def _get_extra(self, event: Any, key: str, default: Any = None) -> Any:
        getter = getattr(event, "get_extra", None)
        if callable(getter):
            try:
                return getter(key, default)
            except TypeError:
                return getter(key)
            except Exception:
                return default
        extras = getattr(event, "extras", {})
        if isinstance(extras, dict):
            return extras.get(key, default)
        return default

    def _set_extra(self, event: Any, key: str, value: Any) -> None:
        setter = getattr(event, "set_extra", None)
        if callable(setter):
            try:
                setter(key, value)
                return
            except Exception:
                pass
        extras = getattr(event, "extras", None)
        if isinstance(extras, dict):
            extras[key] = value

    def _stop_event(self, event: Any) -> None:
        stopper = getattr(event, "stop_event", None)
        if callable(stopper):
            try:
                stopper()
            except Exception:
                pass


__all__ = ["ReplyDebounceConfig", "ReplyDebounceCoordinator"]
