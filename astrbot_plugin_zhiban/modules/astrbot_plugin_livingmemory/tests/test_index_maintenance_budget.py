"""PluginInitializer index-maintenance budget integration tests."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from astrbot_plugin_livingmemory.core.base.config_manager import ConfigManager
from astrbot_plugin_livingmemory.core.plugin_initializer import PluginInitializer


class _BudgetSpy:
    def __init__(self):
        self.entries = 0
        self.exits = 0
        self.active = 0
        self.peak = 0

    @asynccontextmanager
    async def maintenance(self):
        self.entries += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            yield
        finally:
            self.active -= 1
            self.exits += 1


def _initializer(tmp_path, budget):
    context = Mock()
    return PluginInitializer(
        context,
        ConfigManager(),
        str(tmp_path),
        budget=budget,
    )


@pytest.mark.asyncio
async def test_index_consistency_only_pass_holds_one_ticket(tmp_path):
    budget = _BudgetSpy()
    initializer = _initializer(tmp_path, budget)
    initializer.index_validator = SimpleNamespace(
        get_migration_status=AsyncMock(return_value=(False, 0)),
        check_consistency=AsyncMock(
            return_value=SimpleNamespace(
                is_consistent=True,
                needs_rebuild=False,
                reason="ok",
                documents_count=3,
            )
        )
    )
    initializer.memory_engine = SimpleNamespace(index_maintenance_status={})

    await initializer._run_index_maintenance()

    assert budget.entries == budget.exits == 0
    assert budget.peak == 0
    assert budget.active == 0
    assert initializer.index_maintenance_status["state"] == "ready"


@pytest.mark.asyncio
async def test_index_rebuild_nested_flush_does_not_take_second_ticket(tmp_path):
    budget = _BudgetSpy()
    initializer = _initializer(tmp_path, budget)
    initializer.index_validator = SimpleNamespace(
        get_migration_status=AsyncMock(return_value=(False, 0)),
        provider_fingerprint_changed=AsyncMock(return_value=True),
        check_consistency=AsyncMock(
            side_effect=[
                SimpleNamespace(
                    is_consistent=False,
                    needs_rebuild=True,
                    reason="changed",
                    documents_count=4,
                ),
                SimpleNamespace(
                    is_consistent=True,
                    needs_rebuild=False,
                    reason="ok",
                    documents_count=4,
                ),
            ]
        ),
        rebuild_indexes=AsyncMock(
            return_value={
                "success": True,
                "processed": 4,
                "errors": 0,
                "total": 4,
                "partial": False,
                "message": "done",
            }
        ),
    )
    initializer.memory_engine = SimpleNamespace(
        index_maintenance_status={},
        rebuild_graph_index=AsyncMock(return_value={"rebuilt": 4, "skipped": 0}),
    )

    await initializer._run_index_maintenance()

    assert budget.entries == budget.exits == 1
    assert budget.peak == 1
    assert budget.active == 0


@pytest.mark.asyncio
async def test_index_rebuild_cancellation_releases_ticket(tmp_path):
    import asyncio

    budget = _BudgetSpy()
    initializer = _initializer(tmp_path, budget)
    entered = asyncio.Event()

    async def rebuild_indexes(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    initializer.index_validator = SimpleNamespace(
        get_migration_status=AsyncMock(return_value=(False, 0)),
        provider_fingerprint_changed=AsyncMock(return_value=True),
        check_consistency=AsyncMock(
            return_value=SimpleNamespace(
                is_consistent=False,
                needs_rebuild=True,
                reason="changed",
                documents_count=4,
            )
        ),
        rebuild_indexes=AsyncMock(side_effect=rebuild_indexes),
    )
    initializer.memory_engine = SimpleNamespace(index_maintenance_status={})

    task = asyncio.create_task(initializer._run_index_maintenance())
    await entered.wait()
    assert budget.active == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert budget.entries == budget.exits == 1
    assert budget.active == 0
    assert initializer.index_maintenance_status["state"] == "cancelled"


@pytest.mark.asyncio
async def test_index_failure_releases_ticket(tmp_path):
    budget = _BudgetSpy()
    initializer = _initializer(tmp_path, budget)
    initializer.index_validator = SimpleNamespace(
        get_migration_status=AsyncMock(return_value=(False, 0)),
        check_consistency=AsyncMock(side_effect=RuntimeError("boom")),
    )
    initializer.memory_engine = SimpleNamespace(index_maintenance_status={})

    await initializer._run_index_maintenance()

    assert budget.entries == budget.exits == 0
    assert budget.active == 0
    assert initializer.index_maintenance_status["state"] == "failed"


@pytest.mark.asyncio
async def test_background_status_reports_missing_providers_without_ids():
    from types import SimpleNamespace
    from astrbot_plugin_livingmemory.core.page_api import PluginPageApi

    plugin = SimpleNamespace(
        initializer=SimpleNamespace(
            embedding_provider=None,
            llm_provider=None,
            _initialization_failed=True,
            _provider_check_attempts=60,
        )
    )
    api = object.__new__(PluginPageApi)
    api.plugin = plugin

    status = api._background_status()

    assert status["ready"] is False
    assert status["state"] == "not_ready"
    assert "Embedding Provider" in status["message"]
    assert "LLM Provider" in status["message"]
    assert status["attempts"] == 60
    assert "provider_id" not in status
    assert "api_key" not in status


@pytest.mark.asyncio
async def test_background_status_marks_ready_without_provider_details():
    from types import SimpleNamespace
    from astrbot_plugin_livingmemory.core.page_api import PluginPageApi

    plugin = SimpleNamespace(
        initializer=SimpleNamespace(
            embedding_provider=object(),
            llm_provider=object(),
            _initialization_failed=False,
            _provider_check_attempts=0,
        )
    )
    api = object.__new__(PluginPageApi)
    api.plugin = plugin

    status = api._background_status()

    assert status["ready"] is True
    assert status["state"] == "ready"
    assert status["message"] == "后台组件已就绪"
    assert set(status) == {
        "ready",
        "state",
        "message",
        "embedding_ready",
        "llm_ready",
        "attempts",
    }
