"""Persistent, privacy-preserving usage accounting for 知伴.

The service intentionally stays dependency-free and stores only accounting
metadata.  It never receives or persists prompts, model output, cookies, or
keys.  All timestamps are stored in UTC; natural-day aggregation uses the
deployment timezone supplied by the caller.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEMA_VERSION = "1"
DEFAULT_SCOPE = "zhiban"
DEFAULT_RETENTION_DAYS = 180
DEFAULT_MAX_RECORDS = 200_000
_MISSING = object()
_CALL_ID_PREFIX = "anonymous-call:"
_USAGE_CALL_ID_ATTR = "_zhiban_usage_call_id"
_MAX_RESPONSE_CALL_ID_CACHE = 512


def _new_usage_call_id() -> str:
    """Return a fresh opaque identity for one real provider call."""

    return _CALL_ID_PREFIX + uuid.uuid4().hex


def _valid_usage_call_id(value: Any) -> str | None:
    """Validate an explicitly propagated call id without normalizing payloads."""

    if isinstance(value, bool) or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.startswith(_CALL_ID_PREFIX):
        suffix = text[len(_CALL_ID_PREFIX) :]
        if len(suffix) != 32:
            return None
        try:
            uuid.UUID(hex=suffix)
        except (ValueError, AttributeError, TypeError):
            return None
    return text


@dataclass(frozen=True)
class _UsageValues:
    present: bool
    input_other: int = 0
    input_cached: int = 0
    output: int = 0

    @property
    def total(self) -> int:
        return self.input_other + self.input_cached + self.output


def _field(source: Any, name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, _MISSING)
    return getattr(source, name, _MISSING)


def _token_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        try:
            number = int(float(value))
        except (TypeError, ValueError, OverflowError):
            return 0
    return max(0, number)


def _first_present(source: Any, *names: str) -> Any:
    for name in names:
        value = _field(source, name)
        if value is not _MISSING and value is not None:
            return value
    return _MISSING


def _extract_usage(usage: Any) -> _UsageValues:
    """Read AstrBot ``TokenUsage`` plus common provider-dict aliases.

    ``TokenUsage(0, 0, 0)`` is a real, measured zero.  ``None`` or an object
    without any recognizable usage field is missing data and must not be
    presented as a measured zero.
    """

    if usage is None:
        return _UsageValues(False)

    direct_names = ("input_other", "input_cached", "output")
    direct = {name: _field(usage, name) for name in direct_names}
    # AstrBot's TokenUsage always supplies the two input buckets.  Requiring
    # one of them avoids treating a generic ``{"output": ...}`` dict as an
    # AstrBot object and accidentally dropping its ``input`` alias.
    if direct["input_other"] is not _MISSING or direct["input_cached"] is not _MISSING:
        output_value = direct["output"]
        if output_value is _MISSING:
            output_value = _first_present(usage, "output_tokens", "completion_tokens")
        return _UsageValues(
            True,
            _token_int(direct["input_other"]),
            _token_int(direct["input_cached"]),
            _token_int(output_value),
        )

    # Compatibility with provider-shaped dictionaries.  Input totals are
    # inclusive of cached tokens, so cached tokens are subtracted from the
    # non-cached bucket instead of being added twice.  ``total_tokens`` is
    # deliberately ignored and recomputed from the three disjoint buckets.
    input_total = _first_present(usage, "input_tokens", "prompt_tokens", "input")
    cached = _first_present(
        usage,
        "cached_input_tokens",
        "cache_read_input_tokens",
        "input_cached_tokens",
    )
    if cached is _MISSING:
        for details_name in ("input_tokens_details", "prompt_tokens_details"):
            details = _field(usage, details_name)
            if details is not _MISSING and details is not None:
                cached = _first_present(details, "cached_tokens", "cached_input_tokens")
                if cached is not _MISSING:
                    break
    output = _first_present(usage, "output_tokens", "completion_tokens", "output")
    if input_total is _MISSING and cached is _MISSING and output is _MISSING:
        return _UsageValues(False)

    cached_count = 0 if cached is _MISSING else _token_int(cached)
    if input_total is _MISSING:
        input_other = 0
    else:
        input_total_count = _token_int(input_total)
        cached_count = min(cached_count, input_total_count)
        input_other = input_total_count - cached_count
    return _UsageValues(
        True,
        input_other,
        cached_count,
        0 if output is _MISSING else _token_int(output),
    )


def _response_usage(response: Any, usage_missing: bool | None = None) -> _UsageValues:
    """Extract normalized usage from a response without retaining its payload.

    AstrBot's OpenAI adapters may synthesize ``TokenUsage(0, 0, 0)`` when the
    provider omitted usage.  If the attached ``raw_completion`` explicitly has
    no recognizable usage, treat that synthesized zero as missing.  Measured
    zeros without an explicit raw usage payload remain real zeroes.
    """

    if usage_missing is True:
        return _UsageValues(False)

    direct = _extract_usage(_field(response, "usage"))
    raw_completion = _field(response, "raw_completion")
    raw_usage = _MISSING
    if raw_completion is not _MISSING and raw_completion is not None:
        raw_usage = _field(raw_completion, "usage")
    from_raw = (
        _extract_usage(raw_usage)
        if raw_usage is not _MISSING
        else _UsageValues(False)
    )

    if usage_missing is False:
        return from_raw if from_raw.present else direct

    # The raw provider payload, when available, is authoritative.  This both
    # preserves measured zeroes and avoids an adapter's synthesized zero
    # masking non-zero provider values.
    if raw_usage is not _MISSING:
        return from_raw
    return direct


def _sqlite_utc_text(value: datetime) -> str:
    """Render an aware datetime as the naive UTC text AstrBot stores."""

    return _as_utc(value).replace(tzinfo=None).isoformat(sep=" ", timespec="microseconds")


def _as_utc(value: datetime | str | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="microseconds")


def _resolve_timezone(name: str | None) -> tuple[tzinfo, str]:
    """Return a usable timezone and a stable label for API responses."""

    candidate = (name or "").strip()
    if candidate:
        try:
            return ZoneInfo(candidate), candidate
        except (ZoneInfoNotFoundError, ValueError):
            # Configuration errors should degrade to a local zone rather than
            # taking down the dashboard or the chat plugin.
            pass
    local = datetime.now().astimezone().tzinfo or timezone.utc
    label = getattr(local, "key", None) or getattr(local, "zone", None)
    if not label:
        offset = local.utcoffset(datetime.now())
        if offset == timedelta(0):
            label = "UTC"
        else:
            total_minutes = int(offset.total_seconds() // 60) if offset else 0
            sign = "+" if total_minutes >= 0 else "-"
            hours, minutes = divmod(abs(total_minutes), 60)
            label = f"UTC{sign}{hours:02d}:{minutes:02d}"
    return local, label


def _normalise_status(status: Any) -> str:
    text = str(status or "").strip().lower()
    if text in {"completed", "complete", "success", "succeeded", "ok"}:
        return "completed"
    if text in {"failed", "failure", "error", "errored", "err", "cancelled", "canceled"}:
        return "failed"
    return "unknown"


def _clean_label(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _status_rank(status: str) -> int:
    return {"completed": 3, "failed": 2, "unknown": 1}.get(status, 1)


def _response_status(response: Any, status: str | None) -> str:
    role_status = _normalise_status(_field(response, "role"))
    if role_status == "failed":
        return "failed"
    if status is None:
        return "completed"
    return _normalise_status(status)


def _dedupe_key(request_id: str) -> str:
    # Request ids are normally short provider ids.  Bound pathological values
    # without ever storing arbitrary response bodies.
    if len(request_id) <= 1024:
        return request_id
    return "sha256:" + hashlib.sha256(request_id.encode("utf-8")).hexdigest()


class UsageService:
    """SQLite-backed accounting for 知伴-related model responses.

    Each operation opens its own short-lived connection.  Writes use
    ``BEGIN IMMEDIATE`` and a unique ``(scope, dedupe_key)`` constraint so
    concurrent hooks can safely report the same final response more than once.
    """

    def __init__(self, db_path: str | Path, timezone_name: str | None = None):
        self.db_path = Path(db_path).expanduser()
        self._tz, self.timezone = _resolve_timezone(timezone_name)
        self._init_lock = threading.Lock()
        self._started_lock = threading.Lock()
        self._started_at: str | None = None
        self._schema_ready = False
        # Explicit call ids are the primary propagation mechanism.  This small
        # cache is only a compatibility bridge for hooks that run before the
        # caller upgrade.  It is keyed by ``id(response)`` only as an in-process
        # lookup hint.  The paired weak reference is always dereferenced and
        # identity-checked before use, so an address cannot reuse a stale id.
        self._response_call_ids: dict[int, tuple[Any, str]] = {}
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.db_path),
            timeout=8.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 8000")
        return connection

    def _initialize(self) -> None:
        with self._init_lock:
            if self._schema_ready:
                return
            connection = self._connect()
            try:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = NORMAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS usage_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS usage_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        scope TEXT NOT NULL,
                        dedupe_key TEXT NOT NULL,
                        request_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        model TEXT,
                        status TEXT NOT NULL,
                        has_usage INTEGER NOT NULL CHECK (has_usage IN (0, 1)),
                        input_other INTEGER NOT NULL DEFAULT 0,
                        input_cached INTEGER NOT NULL DEFAULT 0,
                        output INTEGER NOT NULL DEFAULT 0,
                        total_tokens INTEGER NOT NULL DEFAULT 0,
                        occurred_at TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE (scope, dedupe_key)
                    );

                    CREATE INDEX IF NOT EXISTS idx_usage_occurred
                        ON usage_records (scope, occurred_at);
                    CREATE INDEX IF NOT EXISTS idx_usage_source
                        ON usage_records (scope, source, occurred_at);
                    """
                )
                connection.execute(
                    "INSERT OR IGNORE INTO usage_meta (key, value) VALUES (?, ?)",
                    ("schema_version", SCHEMA_VERSION),
                )
                self._schema_ready = True
            finally:
                connection.close()

    @staticmethod
    def _can_weakref(value: Any) -> bool:
        try:
            weakref.ref(value)
        except TypeError:
            return False
        return True

    @staticmethod
    def _response_call_id_attribute(response: Any) -> str | None:
        value = getattr(response, _USAGE_CALL_ID_ATTR, None)
        return _valid_usage_call_id(value)

    def _lookup_response_call_id(self, response: Any) -> str | None:
        entry = self._response_call_ids.get(id(response))
        if entry is None:
            return None
        reference, call_id = entry
        if reference() is response:
            return call_id
        # Recovered object address: retire the stale entry immediately.
        self._response_call_ids.pop(id(response), None)
        return None

    def _prune_response_call_ids(self) -> None:
        """Bound the compatibility cache by dropping collected responses."""

        if len(self._response_call_ids) < _MAX_RESPONSE_CALL_ID_CACHE:
            return
        for address, (reference, _) in list(self._response_call_ids.items()):
            if reference() is None:
                self._response_call_ids.pop(address, None)

    def _associate_response_call_id(self, response: Any, call_id: str) -> None:
        if self._can_weakref(response):
            self._prune_response_call_ids()
            self._response_call_ids[id(response)] = (weakref.ref(response), call_id)

    def new_call_id(self) -> str:
        """Create the identity for one real provider call.

        The caller should pass the returned value to ``record_*`` through the
        call's own context (or event extra data) so every hook for that call
        shares one id.  Retries should call this again for a new attempt.
        """

        return _new_usage_call_id()

    def begin_provider_call(self, response: Any, call_id: str | None = None) -> str:
        """Bind a call id to a response before any usage hook observes it.

        This is a compatibility bridge for callers that cannot yet pass the
        call id explicitly.  It keeps only a weak reference to the response and
        never inspects or persists the response payload.
        """

        resolved = _valid_usage_call_id(call_id) or self.new_call_id()
        try:
            setattr(response, _USAGE_CALL_ID_ATTR, resolved)
        except Exception:
            pass
        self._associate_response_call_id(response, resolved)
        return resolved

    def finish_provider_call(
        self,
        response: Any,
        *,
        call_id: str | None = None,
        clear_binding: bool = True,
    ) -> str | None:
        """Finish a call and return the id that hooks should reuse.

        Explicit ``call_id`` always wins.  Otherwise a response-level binding
        made by ``begin_provider_call`` is used.  The binding is removed by
        default after recording so the id cannot leak into a later retry that
        happens to reuse the same object address.
        """

        resolved = _valid_usage_call_id(call_id)
        if resolved is None:
            resolved = self._response_call_id_attribute(response)
        if resolved is None:
            resolved = self._lookup_response_call_id(response)
        if resolved is not None and clear_binding:
            self._response_call_ids.pop(id(response), None)
            try:
                if getattr(response, _USAGE_CALL_ID_ATTR, None) == resolved:
                    delattr(response, _USAGE_CALL_ID_ATTR)
            except Exception:
                pass
        return resolved

    def _resolve_accounting_id(
        self,
        response: Any,
        *,
        request_id: str | None,
        call_id: str | None,
    ) -> str:
        """Choose a durable dedupe id without ever using an object address."""

        if request_id is not None and str(request_id).strip():
            return str(request_id).strip()

        explicit = _valid_usage_call_id(call_id)
        if explicit is not None:
            return explicit

        response_id = _field(response, "id")
        if (
            response_id is not _MISSING
            and response_id is not None
            and str(response_id).strip()
        ):
            return str(response_id).strip()

        propagated = self._response_call_id_attribute(response)
        if propagated is None:
            propagated = self._lookup_response_call_id(response)
        if propagated is not None:
            return propagated

        # Last-resort compatibility for unmodified callers.  A fresh UUID is
        # generated per record call; repeated hooks for the same response can
        # still dedupe through the bounded in-process binding recorded here.
        generated = self.new_call_id()
        self._associate_response_call_id(response, generated)
        return generated

    @staticmethod
    def _started_payload(started_at: str, now_utc: datetime, tz: tzinfo, label: str) -> dict[str, Any]:
        try:
            started = _as_utc(started_at)
            started_local = started.astimezone(tz)
            started_day = started_local.date().isoformat()
            days = max(1, (now_utc.astimezone(tz).date() - started_local.date()).days + 1)
        except (TypeError, ValueError):
            started_day = None
            days = 1
        return {
            "started_at": started_at,
            "started_day": started_day,
            "days": days,
            "timezone": label,
        }

    def ensure_started(self, now: datetime | str | None = None) -> dict[str, Any]:
        """Persist the first-use timestamp and return the companion-day basis."""

        now_utc = _as_utc(now)
        started_at = self._started_at
        if started_at is None:
            with self._started_lock:
                started_at = self._started_at
                if started_at is None:
                    connection = self._connect()
                    try:
                        connection.execute("BEGIN IMMEDIATE")
                        connection.execute(
                            "INSERT OR IGNORE INTO usage_meta (key, value) VALUES ('started_at', ?)",
                            (_iso_utc(now_utc),),
                        )
                        row = connection.execute(
                            "SELECT value FROM usage_meta WHERE key = 'started_at'"
                        ).fetchone()
                        connection.commit()
                    except Exception:
                        connection.rollback()
                        raise
                    finally:
                        connection.close()
                    started_at = str(row["value"]) if row else _iso_utc(now_utc)
                    self._started_at = started_at
        return self._started_payload(started_at, now_utc, self._tz, self.timezone)

    def record_response(
        self,
        response: Any,
        *,
        source: str,
        model: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
        call_id: str | None = None,
        occurred_at: datetime | str | None = None,
        scope: str = DEFAULT_SCOPE,
        usage_missing: bool | None = None,
        is_final: bool | None = None,
    ) -> bool:
        """Record one final model response, idempotently by call identity.

        ``True`` means a new row was inserted or an existing provisional row
        was upgraded with better status/usage.  ``False`` means no accounting
        changed.  Each real provider call must supply a fresh ``call_id``;
        retries receive a new id and are counted separately, while repeated
        hooks reporting one call reuse the same id and collapse to one row.

        AstrBot may yield a terminal stream chunk with ``is_chunk=True``.  Such
        chunks are ignored unless the caller explicitly marks ``is_final``.
        When ``usage_missing`` is ``True``, AstrBot's synthesized all-zero
        ``TokenUsage`` is treated as unavailable rather than measured zero.
        """

        is_chunk = _field(response, "is_chunk") is True
        if is_chunk and is_final is not True:
            return False

        self.ensure_started()
        resolved_usage = _response_usage(response, usage_missing)
        request_text = self._resolve_accounting_id(
            response,
            request_id=request_id,
            call_id=call_id,
        )
        occurred_utc = _as_utc(occurred_at)
        record_scope = _clean_label(scope, DEFAULT_SCOPE)
        record_source = _clean_label(source, "unknown")
        record_model = None if model is None else (str(model).strip() or None)
        record_status = _response_status(response, status)
        token_values = (
            resolved_usage.input_other,
            resolved_usage.input_cached,
            resolved_usage.output,
            resolved_usage.total if resolved_usage.present else 0,
        )
        dedupe_key = _dedupe_key(request_text)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT id, status, has_usage, input_other, input_cached,
                       output, total_tokens
                FROM usage_records
                WHERE scope = ? AND dedupe_key = ?
                """,
                (record_scope, dedupe_key),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO usage_records (
                        scope, dedupe_key, request_id, source, model, status,
                        has_usage, input_other, input_cached, output,
                        total_tokens, occurred_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_scope,
                        dedupe_key,
                        request_text,
                        record_source,
                        record_model,
                        record_status,
                        int(resolved_usage.present),
                        token_values[0],
                        token_values[1],
                        token_values[2],
                        token_values[3],
                        _iso_utc(occurred_utc),
                        _iso_utc(datetime.now(timezone.utc)),
                    ),
                )
                changed = cursor.rowcount > 0
            else:
                old_status = str(existing["status"])
                old_has_usage = bool(existing["has_usage"])
                better_status = _status_rank(record_status) > _status_rank(old_status)
                better_usage = resolved_usage.present and (
                    not old_has_usage or resolved_usage.total > int(existing["total_tokens"])
                )
                changed = better_status or better_usage
                if changed:
                    connection.execute(
                        """
                        UPDATE usage_records
                        SET status = ?, has_usage = ?, input_other = ?,
                            input_cached = ?, output = ?, total_tokens = ?,
                            model = COALESCE(model, ?), source = CASE
                                WHEN source = 'unknown' THEN ? ELSE source END
                        WHERE id = ?
                        """,
                        (
                            record_status if better_status else old_status,
                            int(resolved_usage.present or (old_has_usage and not better_status)),
                            token_values[0] if better_usage else (existing["input_other"] if old_has_usage else 0),
                            token_values[1] if better_usage else (existing["input_cached"] if old_has_usage else 0),
                            token_values[2] if better_usage else (existing["output"] if old_has_usage else 0),
                            token_values[3] if better_usage else (existing["total_tokens"] if old_has_usage else 0),
                            record_model,
                            record_source,
                            existing["id"],
                        ),
                    )
            connection.commit()
            return changed
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_event(
        self,
        event: Any,
        response: Any,
        *,
        source: str = "unknown",
        model: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
        call_id: str | None = None,
        occurred_at: datetime | str | None = None,
        scope: str = DEFAULT_SCOPE,
        usage_missing: bool | None = None,
        is_final: bool | None = None,
    ) -> bool:
        """Record an event response, reading only the usage-source marker.

        The event's ``extra._zhiban_usage_source`` and
        ``extra._zhiban_usage_call_id`` are preferred when present.  No event
        text, message chain, or sender metadata is inspected.
        """

        extra = getattr(event, "extra", None)
        if isinstance(extra, Mapping):
            marker = extra.get("_zhiban_usage_source")
            if marker:
                source = str(marker)
            if call_id is None:
                call_id = _valid_usage_call_id(extra.get(_USAGE_CALL_ID_ATTR))
        return self.record_response(
            response,
            source=source,
            model=model,
            status=status,
            request_id=request_id,
            call_id=call_id,
            occurred_at=occurred_at,
            scope=scope,
            usage_missing=usage_missing,
            is_final=is_final,
        )

    @staticmethod
    def _period_coverage(requests: int, usage_requests: int, missing_usage: int) -> str:
        if requests == 0:
            return "no_data"
        if usage_requests == 0:
            return "missing"
        if missing_usage:
            return "partial"
        return "complete"

    @classmethod
    def _summary_values(cls, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            requests = usage_requests = missing_usage = 0
            successful_responses = failed_responses = unknown_responses = 0
            input_other = input_cached = output = total = 0
        else:
            requests = int(row["requests"] or 0)
            usage_requests = int(row["usage_requests"] or 0)
            missing_usage = int(row["missing_usage"] or 0)
            successful_responses = int(row["successful_responses"] or 0)
            failed_responses = int(row["failed_responses"] or 0)
            unknown_responses = int(row["unknown_responses"] or 0)
            input_other = int(row["input_other"] or 0)
            input_cached = int(row["input_cached"] or 0)
            output = int(row["output"] or 0)
            total = int(row["tokens"] or 0)
        has_usage = usage_requests > 0
        return {
            "requests": requests,
            "usage_requests": usage_requests,
            "missing_usage": missing_usage,
            "successful_responses": successful_responses,
            "failed_responses": failed_responses,
            "unknown_responses": unknown_responses,
            # ``None`` means "not measured", while zero with usage_requests > 0
            # means a provider-reported real zero.
            "tokens": total if has_usage else None,
            "input_other": input_other if has_usage else None,
            "input_cached": input_cached if has_usage else None,
            "output": output if has_usage else None,
            "token_coverage": cls._period_coverage(requests, usage_requests, missing_usage),
            "tokens_available": has_usage,
        }

    @staticmethod
    def _bounds(now_utc: datetime, tz: tzinfo) -> tuple[datetime, datetime, datetime]:
        today = now_utc.astimezone(tz).date()
        today_start = datetime.combine(today, time.min, tzinfo=tz)
        tomorrow_start = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)
        last7_start = datetime.combine(today - timedelta(days=6), time.min, tzinfo=tz)
        return (
            today_start.astimezone(timezone.utc),
            last7_start.astimezone(timezone.utc),
            tomorrow_start.astimezone(timezone.utc),
        )

    @staticmethod
    def _query_summary(
        connection: sqlite3.Connection,
        scope: str,
        start: datetime | None,
        end: datetime | None,
    ) -> sqlite3.Row:
        clauses = ["scope = ?"]
        params: list[Any] = [scope]
        if start is not None:
            clauses.append("occurred_at >= ?")
            params.append(_iso_utc(start))
        if end is not None:
            clauses.append("occurred_at < ?")
            params.append(_iso_utc(end))
        where = " AND ".join(clauses)
        return connection.execute(
            f"""
            SELECT
                COUNT(*) AS requests,
                SUM(CASE WHEN has_usage = 1 THEN 1 ELSE 0 END) AS usage_requests,
                SUM(CASE WHEN has_usage = 0 THEN 1 ELSE 0 END) AS missing_usage,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS successful_responses,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_responses,
                SUM(CASE WHEN status NOT IN ('completed', 'failed') THEN 1 ELSE 0 END) AS unknown_responses,
                COALESCE(SUM(CASE WHEN has_usage = 1 THEN total_tokens ELSE 0 END), 0) AS tokens,
                COALESCE(SUM(CASE WHEN has_usage = 1 THEN input_other ELSE 0 END), 0) AS input_other,
                COALESCE(SUM(CASE WHEN has_usage = 1 THEN input_cached ELSE 0 END), 0) AS input_cached,
                COALESCE(SUM(CASE WHEN has_usage = 1 THEN output ELSE 0 END), 0) AS output
            FROM usage_records
            WHERE {where}
            """,
            params,
        ).fetchone()

    def summary(self, now: datetime | str | None = None) -> dict[str, Any]:
        """Return read-only zhiban totals for today, seven days, and all time.

        ``tokens`` and its buckets are ``None`` when no recorded request has
        provider usage; a numeric zero therefore always means a measured zero.
        ``token_coverage`` reports ``no_data``/``missing``/``partial``/
        ``complete`` for the dashboard's data-quality badge.
        """

        now_utc = _as_utc(now)
        started = self.ensure_started(now=now_utc)
        today_start, last7_start, tomorrow_start = self._bounds(now_utc, self._tz)
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            today = self._summary_values(
                self._query_summary(connection, DEFAULT_SCOPE, today_start, tomorrow_start)
            )
            last7 = self._summary_values(
                self._query_summary(connection, DEFAULT_SCOPE, last7_start, tomorrow_start)
            )
            all_time = self._summary_values(
                self._query_summary(connection, DEFAULT_SCOPE, None, None)
            )
            source_rows = connection.execute(
                """
                SELECT
                    source,
                    COUNT(*) AS requests,
                    SUM(CASE WHEN has_usage = 1 THEN 1 ELSE 0 END) AS usage_requests,
                    SUM(CASE WHEN has_usage = 0 THEN 1 ELSE 0 END) AS missing_usage,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS successful_responses,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_responses,
                    SUM(CASE WHEN status NOT IN ('completed', 'failed') THEN 1 ELSE 0 END) AS unknown_responses,
                    COALESCE(SUM(CASE WHEN has_usage = 1 THEN total_tokens ELSE 0 END), 0) AS tokens,
                    COALESCE(SUM(CASE WHEN has_usage = 1 THEN input_other ELSE 0 END), 0) AS input_other,
                    COALESCE(SUM(CASE WHEN has_usage = 1 THEN input_cached ELSE 0 END), 0) AS input_cached,
                    COALESCE(SUM(CASE WHEN has_usage = 1 THEN output ELSE 0 END), 0) AS output
                FROM usage_records
                WHERE scope = ?
                GROUP BY source
                ORDER BY requests DESC, source ASC
                """,
                (DEFAULT_SCOPE,),
            ).fetchall()
            connection.commit()
        finally:
            connection.close()

        sources = []
        for row in source_rows:
            values = self._summary_values(row)
            values["source"] = str(row["source"])
            sources.append(values)
        return {
            "scope": DEFAULT_SCOPE,
            "timezone": started["timezone"],
            "started_at": started["started_at"],
            "started_day": started["started_day"],
            "days": started["days"],
            "today": today,
            "last7": last7,
            "all": all_time,
            "sources": sources,
            "retention_days": DEFAULT_RETENTION_DAYS,
        }

    def cleanup(
        self,
        now: datetime | str | None = None,
        *,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> dict[str, int]:
        """Apply bounded retention without touching the first-use timestamp."""

        if retention_days < 1:
            raise ValueError("retention_days must be at least 1")
        if max_records < 1:
            raise ValueError("max_records must be at least 1")
        cutoff = _iso_utc(_as_utc(now) - timedelta(days=retention_days))
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute(
                "DELETE FROM usage_records WHERE occurred_at < ?", (cutoff,)
            ).rowcount
            remaining = int(
                connection.execute("SELECT COUNT(*) FROM usage_records").fetchone()[0]
            )
            overflow = 0
            if remaining > max_records:
                overflow = connection.execute(
                    """
                    DELETE FROM usage_records
                    WHERE id IN (
                        SELECT id FROM usage_records
                        ORDER BY occurred_at ASC, id ASC
                        LIMIT ?
                    )
                    """,
                    (remaining - max_records,),
                ).rowcount
            remaining = int(
                connection.execute("SELECT COUNT(*) FROM usage_records").fetchone()[0]
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return {
            "deleted_old": max(0, int(old)),
            "deleted_overflow": max(0, int(overflow)),
            "remaining": remaining,
        }

    @staticmethod
    def _empty_global_period() -> dict[str, Any]:
        return {
            "requests": 0,
            "tokens": 0,
            "input_other": 0,
            "input_cached": 0,
            "output": 0,
        }


def _provider_period(
    connection: sqlite3.Connection,
    start: datetime | None,
    end: datetime | None,
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    # AstrBot declares provider_stats.created_at as a timezone-naive
    # SQLAlchemy DateTime but populates it with aware UTC values, which SQLite
    # stores as naive UTC text.  Compare normalized UTC text directly; using
    # SQLite datetime() would strip the offset and reintroduce an 8-hour shift
    # for Asia/Shanghai boundaries.
    if start is not None:
        clauses.append("substr(replace(created_at, 'T', ' '), 1, 26) >= ?")
        params.append(_sqlite_utc_text(start))
    if end is not None:
        clauses.append("substr(replace(created_at, 'T', ' '), 1, 26) < ?")
        params.append(_sqlite_utc_text(end))
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    row = connection.execute(
        f"""
        SELECT
            COUNT(*) AS requests,
            COALESCE(SUM(token_input_other), 0) AS input_other,
            COALESCE(SUM(token_input_cached), 0) AS input_cached,
            COALESCE(SUM(token_output), 0) AS output,
            COALESCE(SUM(token_input_other + token_input_cached + token_output), 0) AS tokens
        FROM provider_stats
        {where}
        """,
        params,
    ).fetchone()
    requests = int(row["requests"] or 0)
    return {
        "requests": requests,
        "tokens": int(row["tokens"] or 0),
        "input_other": int(row["input_other"] or 0),
        "input_cached": int(row["input_cached"] or 0),
        "output": int(row["output"] or 0),
    }


def global_provider_summary(
    db_path: str | Path,
    timezone_name: str | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    """Read AstrBot's global ``provider_stats`` table without writing to it.

    This scope is deliberately separate from ``zhiban`` and callers must not
    add the two together.  A missing or incompatible database yields an
    ``available=False`` payload instead of raising into the dashboard.
    """

    tz, label = _resolve_timezone(timezone_name)
    now_utc = _as_utc(now)
    today_start, last7_start, tomorrow_start = UsageService._bounds(now_utc, tz)
    result: dict[str, Any] = {
        "available": False,
        "scope": "astrbot_global",
        "timezone": label,
        "today": UsageService._empty_global_period(),
        "last7": UsageService._empty_global_period(),
        "all": UsageService._empty_global_period(),
    }

    path = Path(db_path)
    if not path.is_file():
        result["error"] = "provider_stats database unavailable"
        return result
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=3.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only = ON")
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'provider_stats'"
            ).fetchone()
            if table is None:
                result["error"] = "provider_stats table missing"
                return result
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(provider_stats)").fetchall()
            }
            required = {
                "created_at",
                "token_input_other",
                "token_input_cached",
                "token_output",
            }
            if not required.issubset(columns):
                result["error"] = "provider_stats schema unsupported"
                return result
            result["today"] = _provider_period(connection, today_start, tomorrow_start)
            result["last7"] = _provider_period(connection, last7_start, tomorrow_start)
            result["all"] = _provider_period(connection, None, None)
            result["available"] = True
            return result
        finally:
            connection.close()
    except (OSError, sqlite3.Error, ValueError):
        result["error"] = "provider_stats unavailable"
        return result
