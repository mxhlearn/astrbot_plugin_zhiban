"""知伴人格建议审批。仅保存候选；批准权限由调用方验证并显式传入。

数据库操作放到线程执行，连接短生命周期；可被管理入口与记忆模块共同使用。
"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable


def scope_for_event(event) -> str:
    """审批使用框架原始会话ID；不要以昵称或用户ID合并会话。"""
    return MemoryControl._scope(getattr(event, "unified_msg_origin", ""))


class MemoryControl:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._db_lock = threading.Lock()

    @staticmethod
    def _scope(scope: str) -> str:
        value = str(scope or "").strip()
        if not value or len(value) > 512:
            raise ValueError("需要有效会话标识")
        return value

    @staticmethod
    def _admin(actor_id: str, is_admin: bool) -> str:
        if is_admin is not True or not str(actor_id or "").strip():
            raise PermissionError("仅管理员可以批准、拒绝或回滚人格建议")
        return str(actor_id).strip()

    def _run(self, operation: Callable[[sqlite3.Connection], Any]) -> Any:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._db_lock:
            with sqlite3.connect(self.db_path, timeout=5) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA busy_timeout=5000")
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS proposals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        scope TEXT NOT NULL, text TEXT NOT NULL, reason TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending', created REAL NOT NULL,
                        actor TEXT NOT NULL DEFAULT '', decided REAL
                    );
                    CREATE INDEX IF NOT EXISTS proposal_scope_status ON proposals(scope,status);
                    CREATE TABLE IF NOT EXISTS versions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL,
                        text TEXT NOT NULL, proposal_id INTEGER, parent_id INTEGER,
                        actor TEXT NOT NULL, created REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS current_persona (
                        scope TEXT PRIMARY KEY, version_id INTEGER
                    );
                    CREATE TABLE IF NOT EXISTS persona_audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL,
                        action TEXT NOT NULL, actor TEXT NOT NULL, target_id INTEGER,
                        created REAL NOT NULL
                    );
                """)
                db.execute("BEGIN IMMEDIATE")
                return operation(db)

    async def propose(self, scope: str, text: str, reason: str = "") -> int:
        scope = self._scope(scope)
        text = str(text or "").strip()
        reason = str(reason or "").strip()
        if not text or len(text) > 1500 or len(reason) > 2000:
            raise ValueError("人格建议最多1500字符，依据最多2000字符")
        def op(db):
            row = db.execute("SELECT id FROM proposals WHERE scope=? AND text=? AND status='pending'", (scope,text)).fetchone()
            if row:
                return row[0]
            count = db.execute("SELECT count(*) FROM proposals WHERE scope=? AND status='pending'", (scope,)).fetchone()[0]
            if count >= 20:
                raise ValueError("当前会话待审批建议已达20条，请先处理")
            return db.execute("INSERT INTO proposals(scope,text,reason,created) VALUES(?,?,?,?)", (scope,text,reason,time.time())).lastrowid
        return await asyncio.to_thread(self._run, op)

    async def list_proposals(self, scope: str) -> list[dict]:
        scope = self._scope(scope)
        return await asyncio.to_thread(self._run, lambda db: [dict(r) for r in db.execute("SELECT id,text,reason,created FROM proposals WHERE scope=? AND status='pending' ORDER BY id LIMIT 20", (scope,))])

    async def approved_text(self, scope: str) -> str:
        scope = self._scope(scope)
        def op(db):
            row = db.execute("SELECT v.text FROM current_persona c JOIN versions v ON v.id=c.version_id AND v.scope=c.scope WHERE c.scope=?", (scope,)).fetchone()
            return row[0] if row else ""
        return await asyncio.to_thread(self._run, op)

    async def approve(self, scope: str, proposal_id: int, actor_id: str, *, is_admin: bool = False) -> dict:
        scope, actor = self._scope(scope), self._admin(actor_id, is_admin)
        def op(db):
            row = db.execute("SELECT * FROM proposals WHERE id=? AND scope=? AND status='pending'", (int(proposal_id),scope)).fetchone()
            if not row:
                raise ValueError("未找到当前会话的待审批建议")
            current = db.execute("SELECT version_id FROM current_persona WHERE scope=?", (scope,)).fetchone()
            parent = current[0] if current else None
            now = time.time()
            vid = db.execute("INSERT INTO versions(scope,text,proposal_id,parent_id,actor,created) VALUES(?,?,?,?,?,?)", (scope,row['text'],row['id'],parent,actor,now)).lastrowid
            db.execute("INSERT INTO current_persona(scope,version_id) VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET version_id=excluded.version_id", (scope,vid))
            db.execute("UPDATE proposals SET status='approved',actor=?,decided=? WHERE id=?", (actor,now,row['id']))
            db.execute("INSERT INTO persona_audit(scope,action,actor,target_id,created) VALUES(?,?,?,?,?)", (scope,'approve',actor,vid,now))
            return {'version':vid, 'text':row['text']}
        return await asyncio.to_thread(self._run, op)

    async def reject(self, scope: str, proposal_id: int, actor_id: str, *, is_admin: bool = False) -> bool:
        scope, actor = self._scope(scope), self._admin(actor_id, is_admin)
        def op(db):
            now = time.time()
            cur = db.execute("UPDATE proposals SET status='rejected',actor=?,decided=? WHERE id=? AND scope=? AND status='pending'", (actor,now,int(proposal_id),scope))
            if not cur.rowcount:
                raise ValueError("未找到当前会话的待审批建议")
            db.execute("INSERT INTO persona_audit(scope,action,actor,target_id,created) VALUES(?,?,?,?,?)", (scope,'reject',actor,int(proposal_id),now))
            return True
        return await asyncio.to_thread(self._run, op)

    async def rollback(self, scope: str, actor_id: str, *, is_admin: bool = False) -> str:
        scope, actor = self._scope(scope), self._admin(actor_id, is_admin)
        def op(db):
            row = db.execute("SELECT v.parent_id FROM current_persona c JOIN versions v ON v.id=c.version_id AND v.scope=c.scope WHERE c.scope=?", (scope,)).fetchone()
            if not row:
                raise ValueError("当前会话没有可回滚的人格版本")
            parent = row[0]
            db.execute("UPDATE current_persona SET version_id=? WHERE scope=?", (parent,scope))
            db.execute("INSERT INTO persona_audit(scope,action,actor,target_id,created) VALUES(?,?,?,?,?)", (scope,'rollback',actor,parent,time.time()))
            prev = db.execute("SELECT text FROM versions WHERE id=? AND scope=?", (parent,scope)).fetchone()
            return prev[0] if prev else ''
        return await asyncio.to_thread(self._run, op)

    async def close(self) -> None:
        # 每次操作自行关闭连接，无常驻数据库线程。
        return None
