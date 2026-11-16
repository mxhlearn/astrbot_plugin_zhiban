"""MemoryConsolidationManager maintenance-budget boundary tests."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest
from astrbot_plugin_livingmemory.core.managers.consolidation_manager import (
    MemoryConsolidationManager,
)


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


class _Config:
    def __init__(self, enabled=True, trigger="reflection"):
        self.cfg = {
            "enabled": enabled,
            "trigger": trigger,
            "max_importance": 0.5,
            "min_age_days": 7,
        }

    def get_section(self, name):
        assert name == "memory_consolidation"
        return dict(self.cfg)


@pytest.mark.asyncio
async def test_real_consolidation_holds_ticket_but_skip_does_not():
    budget = _BudgetSpy()
    manager = MemoryConsolidationManager(
        Mock(), Mock(), _Config(enabled=False), budget=budget
    )
    assert await manager.maybe_run("reflection") == {"skipped": True}
    assert budget.entries == 0

    manager = MemoryConsolidationManager(Mock(), Mock(), _Config(), budget=budget)
    manager._query_candidates = AsyncMock(return_value=[])
    result = await manager.maybe_run("reflection")

    assert result["candidates"] == 0
    assert budget.entries == budget.exits == 1
    assert budget.active == 0


@pytest.mark.asyncio
async def test_cooldown_skip_holds_no_ticket():
    budget = _BudgetSpy()
    manager = MemoryConsolidationManager(Mock(), Mock(), _Config(), budget=budget)
    manager._last_run_at = 10**12
    await manager.run_consolidation(force=False)

    assert budget.entries == 0
    assert budget.active == 0


@pytest.mark.asyncio
async def test_cancelled_consolidation_releases_ticket():
    budget = _BudgetSpy()
    manager = MemoryConsolidationManager(Mock(), Mock(), _Config(), budget=budget)
    manager._query_candidates = AsyncMock(side_effect=RuntimeError("boom"))

    # The implementation converts ordinary failures to an error result, but the
    # budget context must still release in either path.
    result = await manager.run_consolidation(force=True)

    assert "error" in result
    assert budget.entries == budget.exits == 1
    assert budget.active == 0