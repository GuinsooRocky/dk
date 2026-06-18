"""会话注册表：把"哪条会话续哪个 claude session_id"落盘到 SQLite。

替代原来的内存 dict（runner.Sessions）——它进程内存活，hub 一重启全空 → 下条消息
新开会话 → 失忆（现状最高频的痛点）。落盘后重启照样 --resume 接上。

owner_key = "channel:chat_id"（沿用现状隔离语义）。MVP 每个 owner_key 维护一条当前
session_id；多话题分线（多 thread_id）留给后续扩展，本表已留好结构。
"""
import sqlite3
import threading
import time

from . import config

_DB_PATH = config.runtime_dir() / "threads.db"


class Registry:
    """get/update 接口与原 runner.Sessions 完全一致 → hub 无缝替换。
    两点改进：① 落盘（重启不丢）；② 失效不静默丢史（见 update）。"""

    def __init__(self):
        self._lock = threading.Lock()
        c = self._conn()
        try:
            c.execute(
                "CREATE TABLE IF NOT EXISTS threads("
                "owner_key TEXT PRIMARY KEY, session_id TEXT NOT NULL DEFAULT '', last_used REAL)"
            )
            c.commit()
        finally:
            c.close()

    def _conn(self):
        # 每次新连接 → 线程安全（sqlite 连接不可跨线程共享）；个人规模这点开销无所谓
        return sqlite3.connect(str(_DB_PATH), timeout=5)

    def get(self, key: str) -> str:
        with self._lock:
            c = self._conn()
            try:
                row = c.execute(
                    "SELECT session_id FROM threads WHERE owner_key=?", (key,)
                ).fetchone()
                return row[0] if row and row[0] else ""
            finally:
                c.close()

    def update(self, key: str, result: dict, was_resume: bool) -> None:
        """拿到 session_id 就落盘（重启不丢）。
        仅当"本轮在续接、且 claude 明确说会话没了(session_gone)"才删——而不是任何失败都删。
        避免一次超时/网络抖动把多轮记忆静默清空（现状 Sessions.pop 的坑）。"""
        sid = result.get("session_id")
        with self._lock:
            c = self._conn()
            try:
                if sid:
                    c.execute(
                        "INSERT INTO threads(owner_key, session_id, last_used) VALUES(?,?,?) "
                        "ON CONFLICT(owner_key) DO UPDATE SET "
                        "session_id=excluded.session_id, last_used=excluded.last_used",
                        (key, sid, time.time()),
                    )
                    c.commit()
                elif was_resume and result.get("session_gone"):
                    c.execute("DELETE FROM threads WHERE owner_key=?", (key,))
                    c.commit()
            finally:
                c.close()
