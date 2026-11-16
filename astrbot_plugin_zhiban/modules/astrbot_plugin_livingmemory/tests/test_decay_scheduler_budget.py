"""DecayScheduler 与知伴 maintenance 预算的集成测试。"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest
from astrbot_plugin_livingmemory.core.schedulers.decay_scheduler import DecayScheduler


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


def _engine() -> Mock:
    engine = Mock()
    engine.config = {
        "auto_cleanup_enabled": False,
        "cleanup_days_threshold": 30,
        "cleanup_importance_threshold": 0.3,
    }
    engine.apply_daily_decay = AsyncMock(return_value=3)
    engine.cleanup_old_memories = AsyncMock(return_value=0)
    engine.maintain_storage = AsyncMock(
        return_value={"success": True, "bytes_reclaimed": 0}
    )
    return engine


@pytest.mark.asyncio
async def test_execute_decay_holds_one_maintenance_ticket(tmp_path):
    budget = _BudgetSpy()
    scheduler = DecayScheduler(
        memory_engine=_engine(),
        decay_rate=0.01,
        data_dir=str(tmp_path),
        budget=budget,
    )

    assert await scheduler._execute_decay(1) is True

    assert budget.entries == 1
    assert budget.exits == 1
    assert budget.active == 0


@pytest.mark.asyncio
async def test_skipped_decay_holds_no_maintenance_ticket(tmp_path):
    budget = _BudgetSpy()
    engine = _engine()
    scheduler = DecayScheduler(
        memory_engine=engine,
        decay_rate=0.01,
        data_dir=str(tmp_path),
        budget=budget,
    )
    await scheduler._set_last_decay_date(scheduler._get_today_str())

    await scheduler._check_and_execute()

    assert budget.entries == 0
    assert budget.active == 0
    engine.apply_daily_decay.assert_not_awaited()


@pytest.mark.asyncio
async def test_maintenance_released_when_decay_raises(tmp_path):
    budget = _BudgetSpy()
    engine = _engine()
    engine.apply_daily_decay = AsyncMock(side_effect=RuntimeError("boom"))
    scheduler = DecayScheduler(
        memory_engine=engine,
        decay_rate=0.01,
        data_dir=str(tmp_path),
        budget=budget,
    )

    assert await scheduler._execute_decay(1) is False

    assert budget.entries == 1
    assert budget.exits == 1
    assert budget.active == 0


@pytest.mark.asyncio
async def test_stop_cancels_idle_scheduler_without_budget_ticket(tmp_path):
    budget = _BudgetSpy()
    scheduler = DecayScheduler(
        memory_engine=_engine(),
        decay_rate=0.01,
        data_dir=str(tmp_path),
        check_hour=23,
        check_minute=59,
        budget=budget,
    )
    # 只验证循环取消路径，不让启动期立即执行维护。
    await scheduler._set_last_decay_date(scheduler._get_today_str())
    await scheduler.start()
    task = scheduler._task
    assert task is not None
    assert budget.entries == 0

    await scheduler.stop()

    assert task.cancelled() or task.done()
    assert budget.entries == budget.exits == 0