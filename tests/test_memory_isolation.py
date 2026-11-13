"""Real p-memory database tests use only temporary directories and no providers."""
import sys
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astrbot_plugin_zhiban.modules.astrbot_plugin_angel_memory.core.plugin_context import PluginContext
from astrbot_plugin_zhiban.modules.astrbot_plugin_angel_memory.pmemory.config import read_scopes
from astrbot_plugin_zhiban.modules.astrbot_plugin_angel_memory.pmemory.kb import PMemory
from astrbot_plugin_zhiban.modules.astrbot_plugin_angel_memory.pmemory.memory import MemoryStore
from astrbot_plugin_zhiban.modules.astrbot_plugin_angel_memory.pmemory.notes import NotesStore
from astrbot_plugin_zhiban.modules.astrbot_plugin_angel_memory.core.memory_runtime.pmemory_runtime import PMemoryMemoryRuntime
from astrbot_plugin_zhiban.modules.astrbot_plugin_angel_memory.core.services.note_index_service import NoteIndexService
from astrbot_plugin_zhiban.modules.astrbot_plugin_angel_memory.core.services.sleep_service import DeepMindSleepService
from astrbot_plugin_zhiban.modules.astrbot_plugin_angel_memory.core.deepmind import DeepMind


def scope(umo):
    ctx = PluginContext.__new__(PluginContext)
    ctx._conversation_scope_map = {"same persona": "public", "qq:private:1": "shared"}
    return ctx.resolve_memory_scope(umo, "same persona")


def test_persona_and_old_maps_cannot_join_scopes():
    assert scope("qq:private:1") != scope("qq:group:1")
    assert scope("qq:private:1") == scope("qq:private:1")
    assert read_scopes(scope("qq:private:1")) == [scope("qq:private:1")]
    for value in (None, "", "public"):
        with pytest.raises(ValueError):
            read_scopes(value)


@pytest.fixture
def db(tmp_path):
    pm = PMemory()
    pm.configure(tmp_path / "pmemory", raw_dir=tmp_path / "raw")
    yield pm
    pm.close()


def test_memory_search_and_update_cannot_cross_scope(db):
    store = MemoryStore(db)
    a, b = scope("private:1"), scope("group:1")
    one = store.remember("喜欢苹果", "用户陈述", ["苹果"], "知识记忆", a)
    store.remember("喜欢香蕉", "用户陈述", ["香蕉"], "知识记忆", b)
    assert store.get(one["id"], b) is None
    assert store.update(one["id"], judgment="泄露", scope=b) == {}
    assert store.get(one["id"], a)["judgment"] == "喜欢苹果"
    assert not store.search("苹果", b)
    assert store.search("苹果", a)


def test_merge_validates_every_source_before_delete(db):
    store = MemoryStore(db)
    runtime = PMemoryMemoryRuntime(store)
    a, b = scope("private:1"), scope("group:1")
    one = store.remember("苹果", "", ["苹果"], "知识记忆", a)
    two = store.remember("香蕉", "", ["香蕉"], "知识记忆", b)
    action = {"action":"merge", "source_memory_ids":[one["id"],two["id"]], "memory":{"judgment":"混合", "tags":["水果"]}}
    assert runtime._apply_action(action, a) is None
    assert store.get(one["id"], a) and store.get(two["id"], b)
    action["action"] = "delete"
    assert runtime._apply_action(action, a) is None
    assert store.get(one["id"], a)


def test_notes_are_filtered_by_scope_before_returning_content(db, tmp_path):
    raw = tmp_path / "raw"
    a, b = scope("private:1"), scope("group:1")
    pa = raw / ".angel/note" / a / "apple.md"
    pb = raw / ".angel/note" / b / "banana.md"
    pa.parent.mkdir(parents=True)
    pb.parent.mkdir(parents=True)
    pa.write_text("# 苹果\n我最爱苹果。", encoding="utf-8")
    pb.write_text("# 香蕉\n我最爱香蕉。", encoding="utf-8")
    notes = NotesStore(raw, db)
    index = NoteIndexService(raw, notes)
    assert index.upsert_file(pa)
    assert index.upsert_file(pb)
    rows = index.search_notes("苹果", domains=["angel"], scope=a)
    assert rows
    nid = rows[0]["metadata"]["note_id"]
    assert index.find_note(nid, ["angel"], scope=a)[1]
    assert index.find_note(nid, ["angel"], scope=b) == (None,None)
    assert index.search_notes("苹果", domains=["angel"], scope=b) == []


@pytest.mark.asyncio
async def test_retirement_never_calls_deletion_or_model():
    class Forbidden:
        def __getattr__(self, name):
            raise AssertionError(f"retirement accessed {name}")
    service = DeepMindSleepService.__new__(DeepMindSleepService)
    service.deepmind = Forbidden()
    result = await service._recycle_memories()
    assert result["deleted"] == 0


def test_reflection_input_is_bounded():
    dm = DeepMind.__new__(DeepMind)
    dm.logger = logging.getLogger("test")
    rows = [{"role":"user", "sender_id":"123456", "sender_name":"test", "content":"x"*5000,"timestamp":i} for i in range(100)]
    result = dm._dedupe_and_sort_chat_records(rows)
    assert len(result) <= 40
    assert sum(len(r["content"]) for r in result) <= 8000
