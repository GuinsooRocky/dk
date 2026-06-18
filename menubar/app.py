"""菜单栏 App —— Hub 的遥控仪表盘（macOS 专属，rumps）。

只读：轮询 Hub 的 /status /stats，菜单栏角标显示存活/忙闲 + 用量。
不自己跑任何东西，纯展示。Hub 没起时显示 🔴。

跑：python app.py（会出现在屏幕右上角菜单栏）
"""
import os
import json
import time
import urllib.request

import rumps
import AppKit

# 隐藏 Dock 图标，只在菜单栏显示（accessory app，不占 Dock）
AppKit.NSBundle.mainBundle().infoDictionary()["LSUIElement"] = "1"

HUB = os.getenv("HUB_URL", "http://127.0.0.1:8787").rstrip("/")
LOG = os.path.expanduser("~/claude-hub-workdir/.logs/hub.log")


def _get(path: str):
    try:
        with urllib.request.urlopen(f"{HUB}{path}", timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None


class App(rumps.App):
    def __init__(self):
        super().__init__("chatcc", title="🤖", quit_button="退出")
        self.m_status = rumps.MenuItem("状态：加载中…")
        self.m_stats = rumps.MenuItem("用量：—")
        self.m_users = rumps.MenuItem("调用者：—")
        self.m_last = rumps.MenuItem("上次：—")
        self.menu = [
            self.m_status, self.m_stats, self.m_users, self.m_last,
            None,
            rumps.MenuItem("刷新", callback=lambda _: self._tick()),
            rumps.MenuItem("打开服务日志", callback=self._open_log),
        ]
        rumps.Timer(lambda _: self._tick(), 10).start()
        self._tick()

    def _open_log(self, _):
        os.system(f"open '{LOG}'")

    def _tick(self):
        st = _get("/status")
        if not st:
            self.title = "🔴"
            self.m_status.title = "状态：服务没连上"
            self.m_stats.title = "用量：—"
            self.m_users.title = "调用者：—"
            self.m_last.title = "上次：—"
            return

        busy = bool(st.get("busy"))
        self.title = "💭" if busy else "🤖"
        up = int(st.get("uptime_sec", 0))
        up_str = f"{up // 3600}h{up % 3600 // 60}m" if up >= 3600 else f"{up // 60}m"
        self.m_status.title = f"状态：🟢 在线 {up_str}（{'忙' if busy else '空闲'}）"

        stats = _get("/stats") or {}
        self.m_stats.title = f"用量：共 {stats.get('total', 0)} 次（成功 {stats.get('ok', 0)} / 忙 {stats.get('busy', 0)}）"
        by_user = stats.get("by_user", {})
        if by_user:
            top = sorted(by_user.items(), key=lambda kv: -kv[1])[:3]
            self.m_users.title = "调用者：" + "  ".join(f"{k.split(':')[-1]}×{v}" for k, v in top)
        else:
            self.m_users.title = "调用者：—"
        last = stats.get("last_at", 0)
        self.m_last.title = "上次：" + (time.strftime("%m-%d %H:%M", time.localtime(last)) if last else "—")


if __name__ == "__main__":
    App().run()
