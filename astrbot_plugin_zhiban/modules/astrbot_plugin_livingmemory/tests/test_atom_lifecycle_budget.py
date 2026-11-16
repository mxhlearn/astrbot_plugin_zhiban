"""AtomLifecycleManager 与知伴 maintenance 预算的边界测试。"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from astrbot_plugin_livingmemory.core.managers.atom_lifecycle_manager import (
    AtomLifecycleManager,
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


class _Store:
    def __init__(self):
        self.expire_stale_atoms = AsyncMock(return_value=2)
        self.forget_expired_atoms = AsyncMock(return_value=1)
        self.cleanup_forgotten = AsyncMock(return_value=3)


@pytest.mark.asyncio
async def test_run_maintenance_holds_one_ticket_for_entire_pass():
    budget = _BudgetSpy()
    store = _Store()
    manager = AtomLifecycleManager(store, budget=budget)

    assert await manager.run_maintenance() == {
        "expired": 2,
        "forgotten": 1,
        "purged": 3,
    }

    assert budget.entries == 1
    assert budget.exits == 1
    assert budget.active == 0


@pytest.mark.asyncio
async def test_maintenance_released_when_store_raises():
    budget = _BudgetSpy()
    store = _Store()
    store.forget_expired_atoms = AsyncMock(side_effect=RuntimeError("boom"))
    manager = AtomLifecycleManager(store, budget=budget)

    with pytest.raises(RuntimeError, match="boom"):
        await manager.run_maintenance()

    assert budget.entries == budget.exits == 1
    assert budget.active == 0


@pytest.mark.asyncio
async def test_stop_idle_loop_does_not_hold_ticket(monkeypatch):
    budget = _BudgetSpy()
    manager = AtomLifecycleManager(_Store(), budget=budget)

    async def idle_maintenance():
        return {}

    monkeypatch.setattr(manager, "run_maintenance", idle_maintenance)
    await manager.start()
    await asyncio.sleep(0)
    await manager.stop()

    assert budget.entries == 0
    assert budget.active == 0