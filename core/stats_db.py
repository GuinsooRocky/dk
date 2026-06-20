"""持久化用量统计（SQLite，B4 / 战略 §9 v2）：每次 /chat 落一行，支持窗口查询。

落盘到 runtime_dir/stats.db，重启不丢；与内存 _STATS（菜单栏快照）并存。
Insights 据此可显真「past 7 days」+ per-day 趋势 + by-user/channel，不再只是内存降级。
"""
import time
import sqlite3
import threading

from core import config

_DB = config.runtime_dir() / "stats.db"
_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(str(_DB), timeout=5)
    c.execute("CREATE TABLE IF NOT EXISTS events(ts REAL, channel TEXT, user TEXT, ok INTEGER)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
    return c


def record(channel: str, user: str, ok: bool) -> None:
    """记一次调用。失败静默——统计不该拖垮主链路。"""
    try:
        with _lock, _conn() as c:
            c.execute("INSERT INTO events(ts,channel,user,ok) VALUES(?,?,?,?)",
                      (time.time(), channel, user, 1 if ok else 0))
    except Exception:
        pass


def insights(days: int = 7) -> dict:
    since = time.time() - max(1, days) * 86400
    try:
        with _lock, _conn() as c:
            total = c.execute("SELECT COUNT(*) FROM events WHERE ts>=?", (since,)).fetchone()[0]
            ok = c.execute("SELECT COUNT(*) FROM events WHERE ts>=? AND ok=1", (since,)).fetchone()[0]
            by_user = dict(c.execute(
                "SELECT user,COUNT(*) FROM events WHERE ts>=? GROUP BY user ORDER BY 2 DESC LIMIT 20",
                (since,)).fetchall())
            by_channel = dict(c.execute(
                "SELECT channel,COUNT(*) FROM events WHERE ts>=? GROUP BY channel", (since,)).fetchall())
            per_day = dict(c.execute(
                "SELECT strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime') d, COUNT(*) "
                "FROM events WHERE ts>=? GROUP BY d ORDER BY d", (since,)).fetchall())
        return {"days": days, "total": total, "ok": ok, "err": total - ok,
                "by_user": by_user, "by_channel": by_channel, "per_day": per_day}
    except Exception as e:
        return {"days": days, "total": 0, "ok": 0, "err": 0,
                "by_user": {}, "by_channel": {}, "per_day": {}, "error": str(e)}


def clear() -> None:
    """清除历史（GUARD-4 的清除历史连这个一起清）。"""
    try:
        with _lock, _conn() as c:
            c.execute("DELETE FROM events")
    except Exception:
        pass


def purge_older_than(days: int = 90) -> None:
    """保留策略：删超过 N 天的行（默认 90 天）。"""
    try:
        with _lock, _conn() as c:
            c.execute("DELETE FROM events WHERE ts < ?", (time.time() - max(1, days) * 86400,))
    except Exception:
        pass
