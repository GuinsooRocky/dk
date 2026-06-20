"""出站通知 —— hub → 渠道的反向通道（入站 /chat 的镜像）。

一条 /notify 按 session_id 查路由后扇出到飞书 / Telegram。路由存
runtime_dir()/notify_routes.json，行：{session_id: {channel, target, registered_at}}。

- 飞书：逐字复用 feishu-claude/feishu_send.py --raw（子进程，走飞书自己的 venv）。
  webhook 没配时 feishu_send.py exit 1 → 这里把 ok:false 暴露出来，绝不挂住。
- Telegram：新建一次 HTTP 调 sendMessage —— telegram_bot 的 Application 只活在它自己
  进程内，跨进程够不着，新建 HTTP 是官方认可的跨进程发送路径。chat_id 只用注册时存进
  路由的真实 target，绝不从 allowed_users 反推（提案 §5 P1 串台）。
  注：proposal 写的是 httpx(trust_env=False)，但 hub venv 只装了 fastapi/uvicorn、没 httpx
  （httpx 在各渠道壳 venv 里）。这里用 stdlib urllib + 空 ProxyHandler 显式不走代理，
  等价于 trust_env=False 的意图（hub 可能被注入了代理给 claude 用，TG 要直连）。
"""
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from core import config

ROUTES_PATH = config.runtime_dir() / "notify_routes.json"
TOKEN_PATH = config.runtime_dir() / ".notify_token"


# ---- 鉴权 token（N-M2：堵未鉴权的开放转发器，§5 P1）----

_TOKEN = None


def ensure_token() -> str:
    """返回 /notify 的共享密钥；不存在则生成并写 .notify_token（0600）。进程内缓存。

    hook / runner 回调读这个文件，放进 X-Notify-Token 头；hub 启动时调一次先把文件备好。
    """
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    try:
        cached = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if cached:
            _TOKEN = cached
            return _TOKEN
    except OSError:
        pass
    import secrets
    tok = secrets.token_urlsafe(32)
    # 0o600 原子建文件（别先 644 再 chmod 留窗口）：本机任意进程都够得着 127.0.0.1，token 是唯一闸
    fd = os.open(str(TOKEN_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(tok)
    _TOKEN = tok
    return _TOKEN


# ---- 简易限流（N-M2：同一 session 刷屏防护）----

_RATE: dict = {}            # session_id -> 上次通过的时刻
_RATE_MIN_INTERVAL = 2.0    # 秒：同一 session 最快 2s 一条（完成通知本就低频，足够堵 flood）


def rate_ok(session_id: str) -> bool:
    now = time.time()
    if now - _RATE.get(session_id, 0.0) < _RATE_MIN_INTERVAL:
        return False
    _RATE[session_id] = now
    return True


# ---- 路由存储（注册 CLI 写、/notify 读，详见 N-M1）----

def load_routes() -> dict:
    try:
        return json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_routes(routes: dict) -> None:
    tmp = ROUTES_PATH.with_name(ROUTES_PATH.name + ".tmp")
    tmp.write_text(json.dumps(routes, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ROUTES_PATH)


def get_route(session_id: str):
    return load_routes().get(session_id)


ROUTE_TTL_SEC = 24 * 3600


def purge_stale_routes(max_age_sec: float = ROUTE_TTL_SEC) -> int:
    """清掉注册超过 max_age_sec 的残留路由行（session 崩了没走 SessionEnd 的兜底，N-M6）。

    一次性生命周期下正常路由在 SessionEnd 即被消费，这里只扫崩溃残留，保证注册表不无限长。
    返回清掉的条数。
    """
    routes = load_routes()
    if not routes:
        return 0
    now = time.time()
    keep = {sid: row for sid, row in routes.items()
            if now - float(row.get("registered_at", 0) or 0) < max_age_sec}
    removed = len(routes) - len(keep)
    if removed:
        save_routes(keep)
    return removed


def is_bot_workdir(cwd: str) -> bool:
    """cwd 落在 bot 自己的 work_dir 树下（~/claude-*-workdir）→ 是 bot 自起的 claude。

    P0 防自循环/自通知：这类 session 绝不纳管、绝不通知。bot 跑在 ~/claude-hub-workdir、
    ~/claude-feishu-workdir 等，天然与用户项目目录隔离。
    """
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


# ---- 默认渠道（config.toml [notify].channel）----

def default_channel() -> str:
    try:
        import tomllib
        with open(config.app_root() / "config.toml", "rb") as f:
            return (tomllib.load(f).get("notify", {}).get("channel") or "feishu").strip()
    except Exception:
        return "feishu"


# ---- 渠道 pusher ----

def push_feishu(text: str) -> dict:
    """子进程跑 feishu_send.py --raw（逐字复用 standalone 发送器，走飞书 venv）。"""
    root = config.app_root()
    py = root / "feishu-claude" / ".venv" / "bin" / "python"
    script = root / "feishu-claude" / "feishu_send.py"
    if not py.exists():
        return {"ok": False, "reason": f"飞书 venv 不存在：{py}"}
    try:
        r = subprocess.run([str(py), str(script), "--raw", text],
                           capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "飞书发送超时"}
    if r.returncode == 0:
        return {"ok": True, "reason": ""}
    return {"ok": False, "reason": (r.stderr or r.stdout or "").strip()[-200:]}


def _telegram_token() -> str:
    tok = ""
    try:
        import tomllib
        with open(config.app_root() / "config.toml", "rb") as f:
            tok = (tomllib.load(f).get("telegram", {}).get("token") or "").strip()
    except Exception:
        tok = ""
    if not tok:   # config.toml 留空时回落渠道 .env（很多人只放 .env）
        tok = config.read_env_value(config.channel_env_path("telegram"), "TELEGRAM_BOT_TOKEN")
    return tok


# 直连 opener：空 ProxyHandler 显式不走任何代理（等价 httpx trust_env=False），
# 即便 hub 进程被注入了 http_proxy（supervisor 给 hub 跑 claude 用）也不影响 TG 直连。
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def push_telegram(text: str, chat_id: str) -> dict:
    """新建一次 HTTP 调 sendMessage（直连不走代理）。chat_id 只用注册时存的真实 target，
    绝不从 allowed_users 反推（§5 P1：群是负数 chat id，白名单是 user id）。"""
    token = _telegram_token()
    if not token:
        return {"ok": False, "reason": "未配 [telegram].token"}
    if not chat_id:
        return {"ok": False, "reason": "缺真实 chat_id（注册时未抓到目标，拒发以防串台）"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _DIRECT_OPENER.open(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        ok = bool(body.get("ok"))
        return {"ok": ok, "reason": "" if ok else str(body)[:200]}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


# ---- 文案 + 分发 ----

def format_notification(n) -> str:
    """组装通知文案（n 是 NotifyIn）。status 是启发式，未必精确。"""
    icon = "✅" if n.status == "ok" else ("❌" if n.status == "error" else "ℹ️")
    head = f"{icon} Claude 会话完成"
    if n.cwd:
        head += f" · {n.cwd}"
    meta = []
    if n.duration_sec:
        m, s = divmod(int(n.duration_sec), 60)
        meta.append(f"用时 {m}m{s:02d}s" if m else f"用时 {s}s")
    if n.turns:
        meta.append(f"{n.turns} 轮")
    parts = [head]
    if meta:
        parts.append(" · ".join(meta))
    parts.append(f"最后输出：{(n.summary or '（摘要不可用）').strip()}")
    return "\n".join(parts)


def dispatch(n) -> dict:
    """按 session_id 查路由扇出。无路由则回落默认渠道（hook 应已先过滤未注册的）。"""
    route = get_route(n.session_id) or {}
    channel = route.get("channel") or default_channel()
    target = route.get("target")
    text = format_notification(n)
    if channel == "feishu":
        return {"channel": "feishu", **push_feishu(text)}
    if channel == "telegram":
        return {"channel": "telegram", **push_telegram(text, target or "")}
    if channel == "wecom":
        # N-M5 调研结论：wecom_aibot_sdk 确有 WSClient.send_message(chatid, body)
        # 「Proactively send message (no callback frame needed)」——by-chatid 主动发送 API 存在。
        # 但它经**渠道进程持有的那条已认证 WS 连接**发；hub 进程够不着那条连接，另开同 bot_id 的
        # 第二条 WS 会和在线渠道抢连接（很可能把渠道踢下线）。安全做法是经 wecom 进程中转（未来 IPC），
        # 不在 hub 里 fabricate 一条竞争连接。当前诚实报错改投（决策⑥：不编造 SDK 调用）。
        return {"channel": "wecom", "ok": False,
                "reason": "企微出站需经渠道进程的 WS 连接中转（hub 够不着），暂不支持主动发送，请改投飞书/Telegram"}
    return {"channel": channel, "ok": False,
            "reason": f"{channel} 暂不支持出站主动发送，请改投飞书/Telegram"}
