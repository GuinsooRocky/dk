#!/usr/bin/env python3
"""SessionEnd hook —— 任意本机 Claude session 跑完 → 查注册表 → 命中才通知（提案 N-M1）。

Claude Code 在 session 结束时用 stdin 喂一段 JSON（session_id / transcript_path / cwd /
reason）。本脚本：
  1. P0 防自循环：cwd 在 bot work_dir 树下（~/claude-*-workdir）/ 带 CHATCC_SUPERVISED
     → 立刻放过（这是 bot 自己起的 claude，绝不能触发自通知，否则可能循环）。
  2. 没注册（notify_routes.json 里没这条 session）→ 放过（全局 hook 看到机器上**所有**
     session，绝大多数是噪声）。
  3. 命中 → 带 X-Notify-Token POST 127.0.0.1:8787/notify。

铁律：
- **永远 exit 0**，任何异常都吞掉——绝不阻塞/拖慢/卡崩用户自己的 session。
- **自包含**：只用 stdlib，不 import 本仓任何模块（hook 跑在用户的 python 环境里，
  那里既没有 httpx 也未必能 import 到本仓）。
- 直连不走代理（等价 hub_client 的 trust_env=False）：用户环境可能挂着 Clash，
  空 ProxyHandler 保证打到本地 127.0.0.1，不被代理拦。
- transcript 解析摘要/轮数/用时留 N-M3；这里先把 status 用 reason 做最粗的启发式。
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

RUNTIME_DIR = Path.home() / ".chat-cc-bot"
ROUTES_PATH = RUNTIME_DIR / "notify_routes.json"
TOKEN_PATH = RUNTIME_DIR / ".notify_token"
HUB_URL = os.getenv("HUB_URL", "http://127.0.0.1:8787").rstrip("/")
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _is_bot_workdir(cwd: str) -> bool:
    """cwd 在 ~/claude-*-workdir 树下 → bot 自起的跑（与 hub/notify.is_bot_workdir 同逻辑，
    这里**故意自带一份**保持 hook 零仓内依赖）。"""
    if not cwd:
        return False
    try:
        p = Path(cwd).expanduser().resolve()
    except Exception:
        return False
    home = Path.home().resolve()
    for parent in [p, *p.parents]:
        if parent.parent == home and parent.name.startswith("claude-") and parent.name.endswith("-workdir"):
            return True
    return False


def _status_from(reason: str) -> str:
    """reason → ok/error 的**启发式**（N-M3）。注意：clear/logout/other 无法干净映射成败，
    一律当 ok —— status 是猜的、未必精确（NotifyIn.status 注释亦标注此事）。"""
    return "error" if (reason or "").lower() in ("error", "failure", "failed") else "ok"


# N-M3：transcript 解析 + 容错。transcript 可能正被写/写一半（§5 P2），整体抽不出就降级。
DEGRADED_SUMMARY = "completed（摘要不可用）"


def _assistant_text(message: dict) -> str:
    """从一条 assistant 记录里抠出纯文本（content 可能是 str 或 block 列表）。"""
    content = (message or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p)
    return ""


def _duration_sec(first_ts, last_ts) -> float:
    if not first_ts or not last_ts:
        return 0.0
    try:
        from datetime import datetime
        a = datetime.fromisoformat(str(first_ts).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
        return max(0.0, (b - a).total_seconds())
    except Exception:
        return 0.0


def parse_transcript(path: str) -> dict:
    """容忍残读的 JSONL 解析：抽 summary(最后一条 assistant 文本) / turns / duration。

    逐行 try/except 跳过坏行（写一半/被锁），绝不让解析崩掉 hook。整体读不到/抽不出
    → summary 降级成 DEGRADED_SUMMARY。返回 {summary, turns, duration_sec}。
    """
    fallback = {"summary": DEGRADED_SUMMARY, "turns": 0, "duration_sec": 0.0}
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return fallback
    summary, turns, first_ts, last_ts = "", 0, None, None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue   # 残行/写一半 → 跳过，不崩整体
        ts = obj.get("timestamp")
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
        if obj.get("type") == "assistant":
            turns += 1
            text = _assistant_text(obj.get("message") or {})
            if text:
                summary = text   # 留最后一条非空 assistant 文本当摘要
    return {
        "summary": (summary.strip() or DEGRADED_SUMMARY),
        "turns": turns,
        "duration_sec": _duration_sec(first_ts, last_ts),
    }


def run() -> None:
    try:
        ev = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return
    cwd = ev.get("cwd") or ""
    # P0：bot 自己起的 claude 绝不通知（双保险：work_dir 树 + 进程环境标记）
    if _is_bot_workdir(cwd) or os.environ.get("CHATCC_SUPERVISED"):
        return
    sid = ev.get("session_id") or ""
    if not sid:
        return
    try:
        routes = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    if sid not in routes:   # 没注册 = 噪声，放过
        return
    try:
        token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        token = ""
    tp = ev.get("transcript_path") or ""
    parsed = parse_transcript(tp) if tp else {"summary": DEGRADED_SUMMARY, "turns": 0, "duration_sec": 0.0}
    summary = parsed["summary"]
    if len(summary) > 500:   # IM 消息别太长，截断
        summary = summary[:500] + "…"
    payload = {
        "session_id": sid,
        "status": _status_from(ev.get("reason") or ev.get("end_reason") or ""),
        "summary": summary,
        "cwd": cwd,
        "duration_sec": parsed["duration_sec"],
        "turns": parsed["turns"],
    }
    req = urllib.request.Request(
        f"{HUB_URL}/notify",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "X-Notify-Token": token},
    )
    try:
        _DIRECT.open(req, timeout=5).read()
    except Exception:
        pass   # hub 没起 / 超时 / 任何错都不该影响用户 session


if __name__ == "__main__":
    try:
        run()
    finally:
        sys.exit(0)   # 永远 exit 0
