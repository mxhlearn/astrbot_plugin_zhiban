from __future__ import annotations

import importlib.util
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from zoneinfo import ZoneInfo


SERVICE_PATH = Path(__file__).parents[1] / "astrbot_plugin_zhiban" / "usage_service.py"
spec = importlib.util.spec_from_file_location("zhiban_usage_service_under_test", SERVICE_PATH)
usage_service = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = usage_service
spec.loader.exec_module(usage_service)

UsageService = usage_service.UsageService
global_provider_summary = usage_service.global_provider_summary

UTC = timezone.utc
SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 15, 4, 0, tzinfo=UTC)  # 12:00 in Asia/Shanghai


@dataclass(frozen=True)
class TokenUsage:
    input_other: int = 0
    input_cached: int = 0
    output: int = 0

    @property
    def total(self) -> int:
        return self.input_other + self.input_cached + self.output


@dataclass
class Response:
    id: str | None
    usage: object


def make_service(tmp_path: Path) -> UsageService:
    return UsageService(tmp_path / "usage.db", "Asia/Shanghai")


def test_first_use_persists_and_first_day_is_day_one(tmp_path):
    service = make_service(tmp_path)
    first = service.ensure_started(datetime(2026, 11, 10, 2, 0, tzinfo=UTC))
    assert first["started_day"] == "2026-11-10"
    assert first["days"] == 1
    assert first["timezone"] == "Asia/Shanghai"

    later = service.ensure_started(NOW)
    assert later["started_at"] == first["started_at"]
    assert later["started_day"] == "2026-11-10"
    assert later["days"] == 6

    restarted = make_service(tmp_path)
    after_restart = restarted.ensure_started(datetime(2026, 11, 20, tzinfo=UTC))
    assert after_restart["started_at"] == first["started_at"]
    assert after_restart["started_day"] == "2026-11-10"


def test_summary_uses_natural_days_in_deployment_timezone(tmp_path):
    service = make_service(tmp_path)
    service.ensure_started(datetime(2026, 11, 10, 2, 0, tzinfo=UTC))

    usage = TokenUsage(10, 2, 5)
    assert service.record_response(
        Response("late-yesterday", usage),
        source="chat",
        occurred_at=datetime(2026, 11, 14, 15, 59, 59, tzinfo=UTC),
    )
    assert service.record_response(
        Response("today", usage),
        source="memory",
        occurred_at=datetime(2026, 11, 14, 16, 0, 0, tzinfo=UTC),
    )
    assert service.record_response(
        Response("outside-seven-days", usage),
        source="chat",
        occurred_at=datetime(2026, 11, 8, 15, 0, 0, tzinfo=UTC),
    )

    summary = service.summary(NOW)
    assert summary["timezone"] == "Asia/Shanghai"
    assert summary["today"]["requests"] == 1
    assert summary["today"]["tokens"] == 17
    assert summary["last7"]["requests"] == 2
    assert summary["last7"]["tokens"] == 34
    assert summary["all"]["requests"] == 3
    assert summary["all"]["tokens"] == 51
    assert summary["today"]["token_coverage"] == "complete"
    assert {row["source"] for row in summary["sources"]} == {"chat", "memory"}


def test_timezone_changes_which_requests_are_today(tmp_path):
    db_path = tmp_path / "usage.db"
    shanghai = UsageService(db_path, "Asia/Shanghai")
    utc = UsageService(db_path, "UTC")
    shanghai.ensure_started(datetime(2026, 11, 1, tzinfo=UTC))

    occurred = datetime(2026, 11, 14, 15, 50, tzinfo=UTC)  # 23:50 in Shanghai
    shanghai.record_response(Response("edge", TokenUsage(1, 0, 1)), source="chat", occurred_at=occurred)
    edge_now = datetime(2026, 11, 14, 16, 30, tzinfo=UTC)  # 00:30 next day in Shanghai

    assert shanghai.summary(edge_now)["today"]["requests"] == 0
    assert shanghai.summary(edge_now)["last7"]["requests"] == 1
    assert utc.summary(edge_now)["today"]["requests"] == 1


def test_same_request_is_recorded_once_but_retries_with_new_ids_count(tmp_path):
    service = make_service(tmp_path)
    response = Response("resp-1", TokenUsage(10, 2, 5))
    assert service.record_response(response, source="chat", occurred_at=NOW) is True
    assert service.record_response(response, source="chat", occurred_at=NOW) is False
    # A stream emits its final usage through more than one hook; the same id
    # must never double count it.
    assert service.record_response(response, source="stream-final", occurred_at=NOW) is False

    retry = Response("resp-2", TokenUsage(1, 0, 1))
    assert service.record_response(retry, source="chat", occurred_at=NOW) is True
    summary = service.summary(NOW)
    assert summary["all"]["requests"] == 2
    assert summary["all"]["tokens"] == 19


def test_same_request_id_in_another_scope_is_independent(tmp_path):
    service = make_service(tmp_path)
    response = Response("shared-id", TokenUsage(2, 0, 3))
    assert service.record_response(response, source="chat", scope="zhiban", occurred_at=NOW)
    assert service.record_response(response, source="chat", scope="other", occurred_at=NOW)
    with sqlite3.connect(tmp_path / "usage.db") as connection:
        count = connection.execute("SELECT COUNT(*) FROM usage_records").fetchone()[0]
    assert count == 2
    assert service.summary(NOW)["all"]["requests"] == 1


def test_missing_usage_and_measured_zero_are_distinct(tmp_path):
    service = make_service(tmp_path)
    assert service.record_response(Response("missing", None), source="chat", occurred_at=NOW)
    assert service.record_response(Response("zero", TokenUsage(0, 0, 0)), source="chat", occurred_at=NOW)
    assert service.record_response(
        Response(
            "provider-shape",
            {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 999,
                "prompt_tokens_details": {"cached_tokens": 40},
            },
        ),
        source="meme",
        occurred_at=NOW,
    )

    summary = service.summary(NOW)["today"]
    assert summary["requests"] == 3
    assert summary["usage_requests"] == 2
    assert summary["missing_usage"] == 1
    assert summary["tokens"] == 120  # 60 uncached + 40 cached + 20 output
    assert summary["input_other"] == 60
    assert summary["input_cached"] == 40
    assert summary["output"] == 20
    assert summary["token_coverage"] == "partial"
    assert summary["tokens_available"] is True


def test_generic_input_output_aliases_are_not_dropped(tmp_path):
    service = make_service(tmp_path)
    service.record_response(
        Response("generic", {"input": 12, "output": 8}),
        source="tts",
        occurred_at=NOW,
    )
    today = service.summary(NOW)["today"]
    assert today["input_other"] == 12
    assert today["input_cached"] == 0
    assert today["output"] == 8
    assert today["tokens"] == 20


def test_no_usage_is_not_reported_as_a_measured_zero(tmp_path):
    service = make_service(tmp_path)
    service.record_response(Response("missing", None), source="chat", occurred_at=NOW)
    today = service.summary(NOW)["today"]
    assert today["usage_requests"] == 0
    assert today["missing_usage"] == 1
    assert today["tokens"] is None
    assert today["input_other"] is None
    assert today["tokens_available"] is False
    assert today["token_coverage"] == "missing"


def test_empty_summary_is_no_data_not_zero_usage(tmp_path):
    service = make_service(tmp_path)
    today = service.summary(NOW)["today"]
    assert today["requests"] == 0
    assert today["usage_requests"] == 0
    assert today["tokens"] is None
    assert today["token_coverage"] == "no_data"
    assert today["tokens_available"] is False


def test_failed_response_with_usage_is_real_consumption(tmp_path):
    service = make_service(tmp_path)
    assert service.record_response(
        Response("failed-1", TokenUsage(3, 4, 5)),
        source="chat",
        status="error",
        occurred_at=NOW,
    )
    assert service.record_response(
        Response("unknown-1", TokenUsage(1, 0, 0)),
        source="chat",
        status="something-new",
        occurred_at=NOW,
    )
    with sqlite3.connect(tmp_path / "usage.db") as connection:
        rows = connection.execute(
            "SELECT request_id, status FROM usage_records ORDER BY request_id"
        ).fetchall()
    assert rows == [("failed-1", "failed"), ("unknown-1", "unknown")]
    assert service.summary(NOW)["today"]["tokens"] == 13


def test_event_records_only_usage_source_marker(tmp_path):
    service = make_service(tmp_path)

    class Event:
        extra = {"_zhiban_usage_source": "chat-event"}

        @property
        def message_str(self):
            raise AssertionError("event body must not be read")

    assert service.record_event(
        Event(), Response("event-1", TokenUsage(1, 2, 3)), source="fallback", occurred_at=NOW
    )
    assert service.summary(NOW)["sources"][0]["source"] == "chat-event"


def test_concurrent_duplicate_hooks_insert_only_one_row(tmp_path):
    db_path = tmp_path / "usage.db"
    services = [UsageService(db_path, "Asia/Shanghai") for _ in range(4)]
    response = Response("concurrent-id", TokenUsage(7, 8, 9))

    def record(service):
        return service.record_response(response, source="chat", occurred_at=NOW)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(record, services * 2))
    assert results.count(True) == 1
    assert results.count(False) == 7
    with sqlite3.connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM usage_records").fetchone()[0]
    assert count == 1
    assert services[0].summary(NOW)["all"]["tokens"] == 24


def test_completed_and_failed_responses_are_reported_without_fake_success(tmp_path):
    service = make_service(tmp_path)
    service.record_response(
        Response("ok", TokenUsage(2, 1, 3)),
        source="chat",
        status="completed",
        occurred_at=NOW,
    )
    service.record_response(
        Response("failed", None),
        source="chat",
        status="failed",
        occurred_at=NOW,
    )
    today = service.summary(NOW)["today"]
    assert today["requests"] == 2
    assert today["successful_responses"] == 1
    assert today["failed_responses"] == 1
    assert today["unknown_responses"] == 0
    assert today["tokens"] == 6
    assert today["missing_usage"] == 1


def test_database_persists_across_restart_without_content_columns(tmp_path):
    service = make_service(tmp_path)
    service.record_response(
        Response("persisted", TokenUsage(5, 6, 7)),
        source="memory",
        model="test-model",
        occurred_at=NOW,
    )
    restarted = make_service(tmp_path)
    summary = restarted.summary(NOW)
    assert summary["all"]["requests"] == 1
    assert summary["all"]["tokens"] == 18
    columns = {
        row[1]
        for row in sqlite3.connect(tmp_path / "usage.db").execute(
            "PRAGMA table_info(usage_records)"
        )
    }
    assert not columns.intersection(
        {"prompt", "prompt_text", "message", "message_text", "content", "cookie", "api_key"}
    )


def test_cleanup_applies_time_and_size_retention_without_resetting_start(tmp_path):
    service = make_service(tmp_path)
    started = service.ensure_started(NOW)
    service.record_response(
        Response("old", TokenUsage(1, 0, 0)),
        source="chat",
        occurred_at=NOW - timedelta(days=200),
    )
    service.record_response(
        Response("recent-1", TokenUsage(1, 0, 0)),
        source="chat",
        occurred_at=NOW - timedelta(days=2),
    )
    service.record_response(
        Response("recent-2", TokenUsage(1, 0, 0)),
        source="chat",
        occurred_at=NOW - timedelta(days=1),
    )

    result = service.cleanup(NOW, retention_days=180, max_records=1)
    assert result == {"deleted_old": 1, "deleted_overflow": 1, "remaining": 1}
    assert service.ensure_started(NOW)["started_at"] == started["started_at"]


def _create_provider_db(path: Path, rows: list[tuple[str, int, int, int]]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE provider_stats (
                created_at TEXT NOT NULL,
                token_input_other INTEGER NOT NULL,
                token_input_cached INTEGER NOT NULL,
                token_output INTEGER NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO provider_stats VALUES (?, ?, ?, ?)", rows
        )


def test_global_provider_summary_is_separate_and_bounded_by_day(tmp_path):
    path = tmp_path / "astrbot.db"
    _create_provider_db(
        path,
        [
            ("2026-11-15 02:00:00.000000", 100, 20, 30),
            ("2026-11-12 02:00:00.000000", 10, 1, 2),
            ("2026-01-01 02:00:00.000000", 5, 0, 0),
        ],
    )
    result = global_provider_summary(path, "Asia/Shanghai", NOW)
    assert result["available"] is True
    assert result["scope"] == "astrbot_global"
    assert result["today"] == {
        "requests": 1,
        "tokens": 150,
        "input_other": 100,
        "input_cached": 20,
        "output": 30,
    }
    assert result["last7"]["requests"] == 2
    assert result["all"]["requests"] == 3
    assert result["all"]["tokens"] == 168
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM provider_stats").fetchone()[0] == 3


def test_global_provider_summary_empty_and_unavailable(tmp_path):
    empty_path = tmp_path / "empty.db"
    _create_provider_db(empty_path, [])
    empty = global_provider_summary(empty_path, "Asia/Shanghai", NOW)
    assert empty["available"] is True
    assert empty["today"]["requests"] == 0
    assert empty["all"]["tokens"] == 0

    missing_table = tmp_path / "no-table.db"
    with sqlite3.connect(missing_table) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER)")
    unavailable = global_provider_summary(missing_table, "Asia/Shanghai", NOW)
    assert unavailable["available"] is False
    assert "table missing" in unavailable["error"]

    no_file = global_provider_summary(tmp_path / "absent.db", "Asia/Shanghai", NOW)
    assert no_file["available"] is False
    assert no_file["error"]


def test_global_provider_summary_rejects_incompatible_schema(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE provider_stats (created_at TEXT)")
    result = global_provider_summary(path, "Asia/Shanghai", NOW)
    assert result["available"] is False
    assert "schema unsupported" in result["error"]

def test_global_provider_naive_utc_timestamps_use_local_day_boundaries(tmp_path):
    path = tmp_path / "astrbot.db"
    _create_provider_db(
        path,
        [
            ("2026-11-14 15:59:59.999999", 1, 0, 0),
            ("2026-11-14 16:00:00.000000", 2, 0, 0),
            ("2026-11-15 15:59:59.999999", 3, 0, 0),
            ("2026-11-15 16:00:00.000000", 4, 0, 0),
        ],
    )
    result = global_provider_summary(path, "Asia/Shanghai", NOW)
    assert result["today"]["requests"] == 2
    assert result["today"]["tokens"] == 5
    assert result["last7"]["requests"] == 3
    assert result["last7"]["tokens"] == 6
    assert result["all"]["requests"] == 4


def test_same_request_upgrades_provisional_status_and_usage_without_double_count(tmp_path):
    service = make_service(tmp_path)
    provisional = Response("stream-final", None)
    assert service.record_response(
        provisional, source="chat", status="unknown", occurred_at=NOW
    )
    assert service.record_response(
        provisional,
        source="chat",
        status="completed",
        usage_missing=False,
        occurred_at=NOW,
        is_final=True,
    ) is True
    final = Response("stream-final", TokenUsage(4, 1, 5))
    assert service.record_response(
        final, source="chat", status="completed", occurred_at=NOW
    ) is True
    assert service.record_response(
        final, source="chat", status="completed", occurred_at=NOW
    ) is False
    summary = service.summary(NOW)["today"]
    assert summary["requests"] == 1
    assert summary["successful_responses"] == 1
    assert summary["unknown_responses"] == 0
    assert summary["tokens"] == 10


def test_failed_retry_with_new_request_id_counts_both_attempts(tmp_path):
    service = make_service(tmp_path)
    service.record_response(
        Response("attempt-1", TokenUsage(2, 0, 1)),
        source="chat",
        status="failed",
        occurred_at=NOW,
    )
    service.record_response(
        Response("attempt-2", TokenUsage(3, 0, 2)),
        source="chat",
        status="completed",
        occurred_at=NOW,
    )
    today = service.summary(NOW)["today"]
    assert today["requests"] == 2
    assert today["failed_responses"] == 1
    assert today["successful_responses"] == 1
    assert today["tokens"] == 8


def test_stream_chunks_require_explicit_final_marker(tmp_path):
    service = make_service(tmp_path)
    chunk = Response("stream-final", TokenUsage(2, 3, 4))
    chunk.is_chunk = True
    assert service.record_response(chunk, source="chat", occurred_at=NOW) is False
    assert service.record_response(
        chunk, source="chat", occurred_at=NOW, is_final=False
    ) is False
    assert service.summary(NOW)["today"]["requests"] == 0
    assert service.record_response(
        chunk, source="chat", occurred_at=NOW, is_final=True
    ) is True
    assert service.summary(NOW)["today"]["tokens"] == 9


def test_astrbot_synthesized_zero_without_provider_usage_is_missing(tmp_path):
    service = make_service(tmp_path)
    synthesized = SimpleNamespace(
        id="no-provider-usage",
        role="assistant",
        usage=TokenUsage(0, 0, 0),
        raw_completion={"usage": None},
    )
    service.record_response(synthesized, source="chat", occurred_at=NOW)
    summary = service.summary(NOW)["today"]
    assert summary["usage_requests"] == 0
    assert summary["missing_usage"] == 1
    assert summary["tokens"] is None


def test_provider_measured_zero_stays_measured_zero(tmp_path):
    service = make_service(tmp_path)
    measured = SimpleNamespace(
        id="provider-zero",
        role="assistant",
        usage=TokenUsage(0, 0, 0),
        raw_completion={"usage": {"prompt_tokens": 0, "completion_tokens": 0}},
    )
    service.record_response(measured, source="chat", occurred_at=NOW)
    summary = service.summary(NOW)["today"]
    assert summary["usage_requests"] == 1
    assert summary["tokens"] == 0
    assert summary["tokens_available"] is True


def test_explicit_missing_usage_overrides_synthesized_token_usage(tmp_path):
    service = make_service(tmp_path)
    response = Response("explicit-missing", TokenUsage(0, 0, 0))
    service.record_response(
        response, source="chat", occurred_at=NOW, usage_missing=True
    )
    summary = service.summary(NOW)["today"]
    assert summary["missing_usage"] == 1
    assert summary["tokens"] is None


def test_raw_provider_usage_is_authoritative_over_adapter_token_usage(tmp_path):
    service = make_service(tmp_path)
    response = SimpleNamespace(
        id="raw-authoritative",
        role="assistant",
        usage=TokenUsage(0, 0, 0),
        raw_completion={
            "usage": {
                "input_tokens": 9,
                "output_tokens": 4,
                "input_tokens_details": {"cached_tokens": 2},
            }
        },
    )
    service.record_response(response, source="chat", occurred_at=NOW)
    today = service.summary(NOW)["today"]
    assert today["input_other"] == 7
    assert today["input_cached"] == 2
    assert today["output"] == 4
    assert today["tokens"] == 13


def test_retry_after_failure_keeps_failed_attempt_and_scoped_success(tmp_path):
    service = make_service(tmp_path)
    service.record_response(
        Response("retry-1", None),
        source="chat",
        status="failed",
        occurred_at=NOW,
    )
    service.record_response(
        Response("retry-2", TokenUsage(5, 0, 1)),
        source="chat",
        status="completed",
        occurred_at=NOW,
    )
    today = service.summary(NOW)["today"]
    assert today["requests"] == 2
    assert today["failed_responses"] == 1
    assert today["successful_responses"] == 1
    assert today["missing_usage"] == 1
    assert today["token_coverage"] == "partial"
    assert today["tokens"] == 6


def test_stored_rows_never_include_message_or_secret_payload(tmp_path):
    service = make_service(tmp_path)
    secret = "SECRET_PROMPT_DO_NOT_STORE"
    response = SimpleNamespace(
        id="privacy",
        role="assistant",
        usage=TokenUsage(1, 0, 1),
        completion_text=secret,
        raw_completion={"usage": {"input_tokens": 1, "output_tokens": 1}, "content": secret},
    )
    service.record_response(response, source="chat", occurred_at=NOW)
    with sqlite3.connect(tmp_path / "usage.db") as connection:
        dump = " ".join(
            str(value)
            for row in connection.execute("SELECT * FROM usage_records")
            for value in row
        )
    assert secret not in dump
    assert "cookie" not in dump.lower()
    assert "api_key" not in dump.lower()


def test_duplicate_response_without_request_id_is_stable(tmp_path):
    service = make_service(tmp_path)
    response = Response(None, TokenUsage(2, 0, 1))
    assert service.record_response(response, source="chat", occurred_at=NOW) is True
    assert service.record_response(response, source="chat", occurred_at=NOW) is False
    with sqlite3.connect(tmp_path / "usage.db") as connection:
        request_id = connection.execute(
            "SELECT request_id FROM usage_records"
        ).fetchone()[0]
    assert request_id.startswith("anonymous:")
    assert request_id.removeprefix("anonymous:").isdigit()
    assert service.summary(NOW)["today"]["requests"] == 1


def test_completed_without_usage_upgrades_failed_attempt_but_clears_tokens(tmp_path):
    service = make_service(tmp_path)
    first = Response("same-response", TokenUsage(7, 0, 2))
    second = Response("same-response", None)
    assert service.record_response(
        first, source="chat", status="failed", occurred_at=NOW
    ) is True
    assert service.record_response(
        second, source="chat", status="completed", occurred_at=NOW
    ) is True
    summary = service.summary(NOW)["today"]
    assert summary["requests"] == 1
    assert summary["successful_responses"] == 1
    assert summary["failed_responses"] == 0
    assert summary["missing_usage"] == 1
    assert summary["tokens"] is None

def test_failed_response_role_is_failed_even_when_status_defaults(tmp_path):
    service = make_service(tmp_path)
    failed = SimpleNamespace(
        id="err-role",
        role="err",
        usage=None,
        raw_completion=None,
    )
    service.record_response(failed, source="chat", occurred_at=NOW)
    today = service.summary(NOW)["today"]
    assert today["successful_responses"] == 0
    assert today["failed_responses"] == 1
    assert today["missing_usage"] == 1
