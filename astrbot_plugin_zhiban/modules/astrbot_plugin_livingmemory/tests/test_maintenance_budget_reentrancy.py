"""Use the real host BudgetScheduler to verify nested maintenance safety."""

import asyncio

import pytest

from astrbot_plugin_zhiban.scheduling import BudgetScheduler


@pytest.mark.asyncio
async def test_nested_maintenance_reuses_ticket_without_deadlock():
    budget = BudgetScheduler(maintenance_concurrency=1, heavy_concurrency=1)
    observed = []

    async def nested_work():
        async with budget.maintenance():
            observed.append(budget.status())
            async with budget.maintenance():
                observed.append(budget.status())
                await asyncio.sleep(0)
            observed.append(budget.status())

    try:
        await asyncio.wait_for(nested_work(), timeout=1.0)
    finally:
        await budget.close()

    assert len(observed) == 3
    assert all(item["maintenance_running"] == 1 for item in observed)
    assert budget.status()["maintenance_running"] == 0
    assert budget.status()["maintenance_waiting"] == 0