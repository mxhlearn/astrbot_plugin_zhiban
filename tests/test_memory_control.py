import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astrbot_plugin_zhiban.memory_control import MemoryControl, scope_for_event


@pytest.mark.asyncio
async def test_proposal_requires_admin_and_is_session_scoped(tmp_path):
    store = MemoryControl(tmp_path / "persona.sqlite3")
    proposal = await store.propose("qq:private:1", "称呼用户为小明", "用户明确要求")
    assert await store.approved_text("qq:private:1") == ""
    assert await store.list_proposals("qq:group:1") == []
    with pytest.raises(PermissionError):
        await store.approve("qq:private:1", proposal, "attacker")
    with pytest.raises(ValueError):
        await store.approve("qq:group:1", proposal, "admin", is_admin=True)
    await store.approve("qq:private:1", proposal, "admin", is_admin=True)
    assert await store.approved_text("qq:private:1") == "称呼用户为小明"
    assert await store.approved_text("qq:group:1") == ""


@pytest.mark.asyncio
async def test_versions_reopen_reject_and_rollback(tmp_path):
    path = tmp_path / "persona.sqlite3"
    store = MemoryControl(path)
    first = await store.propose("scope", "简洁表达")
    await store.approve("scope", first, "admin", is_admin=True)
    second = await store.propose("scope", "详细表达")
    await store.approve("scope", second, "admin", is_admin=True)
    store = MemoryControl(path)
    assert await store.approved_text("scope") == "详细表达"
    assert await store.rollback("scope", "admin", is_admin=True) == "简洁表达"
    assert await store.rollback("scope", "admin", is_admin=True) == ""
    third = await store.propose("scope", "不该生效")
    await store.reject("scope", third, "admin", is_admin=True)
    assert await store.list_proposals("scope") == []
    with pytest.raises(ValueError):
        await store.approve("scope", third, "admin", is_admin=True)


@pytest.mark.asyncio
async def test_proposal_dedup_and_bounded_pending(tmp_path):
    store = MemoryControl(tmp_path / "persona.sqlite3")
    ids = await asyncio.gather(*(store.propose("scope", "同一建议") for _ in range(5)))
    assert len(set(ids)) == 1
    for i in range(19):
        await store.propose("scope", f"建议{i}")
    with pytest.raises(ValueError):
        await store.propose("scope", "第21条")
    with pytest.raises(ValueError):
        await store.propose("scope", "a" * 1501)


def test_event_scope_is_original_umo_and_empty_fails_closed():
    assert scope_for_event(SimpleNamespace(unified_msg_origin="qq:GroupMessage:1")) == "qq:GroupMessage:1"
    with pytest.raises(ValueError):
        scope_for_event(SimpleNamespace())
