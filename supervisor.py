"""supervisor —— 一条命令起全部。

读 config.toml → 起 hub + 所有 enabled 渠道（各用自己的 venv）→ 崩溃指数退避自愈。
配置注入走子进程环境变量（子进程代码零改，继续 os.getenv）。Ctrl+C 全部停。
同时把每个渠道的实时状态（在线/没配/崩溃/退避/最近错误）写到 supervisor.json，
供 Hub 的 /supervisor 暴露给菜单栏/App —— 让"开没开、谁能用、有没有坏"一眼可见。

跑：python3 supervisor.py
"""
import os
import sys
import time
import json
import signal
import threading
import subprocess
from collections import deque
from pathlib import Path

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:
    print("需要 Python 3.11+（tomllib）"); sys.exit(1)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from core import config as core_config  # noqa: E402

CONFIG = ROOT / "config.toml"
STATUS_PATH = core_config.supervisor_status_path()


def load_cfg() -> dict:
    if not CONFIG.exists():
        print(f"没有 config.toml。先 `cp config.example.toml config.toml` 填好再跑。")
        sys.exit(1)
    with open(CONFIG, "rb") as f:
        return tomllib.load(f)


def _venv_py(sub: str) -> str:
    return str(ROOT / sub / ".venv" / "bin" / "python")


def _find_certifi(venv_pythons) -> str:
    """本机系统 CA 坏（链里有自签名证书）→ 找一个 venv 里的 certifi 干净证书包，给子进程统一用。"""
    for py in venv_pythons:
        try:
            r = subprocess.run([py, "-m", "certifi"], capture_output=True, text=True, timeout=10)
            path = r.stdout.strip()
            if path and Path(path).exists():
                return path
        except Exception:
            pass
    return ""


def channel_meta(cfg: dict) -> list:
    """所有已知渠道（含未启用）的元信息，用于状态展示：是否启用 + 凭证是否齐。

    凭证不齐（缺 token/secret，或白名单为空=没人能用）→ 状态 needs_setup。
    """
    def filled(*vals):
        return all((v or "").strip() for v in vals)

    tg = cfg.get("telegram", {})
    fs = cfg.get("feishu", {})
    wc = cfg.get("wecom", {})
    return [
        {"name": "telegram", "enabled": bool(tg.get("enabled")),
         "creds_ok": filled(tg.get("token")) and filled(tg.get("allowed_users"))},
        {"name": "feishu", "enabled": bool(fs.get("enabled")),
         "creds_ok": filled(fs.get("app_id"), fs.get("app_secret")) and filled(fs.get("allowed_users"))},
        {"name": "wecom", "enabled": bool(wc.get("enabled")),
         "creds_ok": filled(wc.get("bot_id"), wc.get("bot_secret")) and filled(wc.get("allowed_users"))},
    ]


def build_components(cfg: dict) -> list:
    claude = cfg.get("claude", {})
    hub_port = cfg.get("hub", {}).get("port", 8787)
    hub_url = f"http://127.0.0.1:{hub_port}"
    proxy = (cfg.get("proxy", {}).get("url") or "").strip()
    voice = cfg.get("voice", {})

    proxy_env = {}
    if proxy:
        proxy_env = {
            "http_proxy": proxy, "https_proxy": proxy,
            "NO_PROXY": "localhost,127.0.0.1,::1", "no_proxy": "localhost,127.0.0.1,::1",
        }
    voice_env = {}
    if voice.get("sensevoice_dir"):
        voice_env["SENSEVOICE_DIR"] = voice["sensevoice_dir"]

    claude_env = {
        "CLAUDE_TOOLS": claude.get("tools", "Read,Glob,Grep,WebFetch"),
        "CLAUDE_MAX_CONCURRENCY": str(claude.get("max_concurrency", 1)),
        "CLAUDE_TIMEOUT": str(claude.get("timeout", 300)),
        "CLAUDE_ENGINE": claude.get("engine", "cli"),
        "HUB_PORT": str(hub_port),
    }
    if claude.get("cmd"):
        claude_env["CLAUDE_CMD"] = claude["cmd"]

    comps = [{
        "name": "hub",
        "cmd": [_venv_py("hub"), "-m", "hub.app"],
        "cwd": str(ROOT),
        "env": {**claude_env, **proxy_env},  # hub 跑 claude，要代理
    }]

    tg = cfg.get("telegram", {})
    if tg.get("enabled"):
        comps.append({
            "name": "telegram",
            "cmd": [_venv_py("telegram"), str(ROOT / "telegram" / "telegram_bot.py")],
            "cwd": str(ROOT / "telegram"),
            "env": {
                "TELEGRAM_BOT_TOKEN": tg.get("token", ""),
                "ALLOWED_USERS": tg.get("allowed_users", ""),
                "TRIGGER_PREFIX": tg.get("trigger_prefix", "/c "),
                "HUB_URL": hub_url, **proxy_env, **voice_env,
            },
        })

    fs = cfg.get("feishu", {})
    if fs.get("enabled"):
        comps.append({
            "name": "feishu",
            "cmd": [_venv_py("feishu-claude"), str(ROOT / "feishu-claude" / "feishu_ws_server.py")],
            "cwd": str(ROOT),
            "env": {
                "FEISHU_APP_ID": fs.get("app_id", ""), "FEISHU_APP_SECRET": fs.get("app_secret", ""),
                "ALLOWED_USERS": fs.get("allowed_users", ""), "HUB_URL": hub_url, **voice_env,
            },
        })

    wc = cfg.get("wecom", {})
    if wc.get("enabled"):
        comps.append({
            "name": "wecom",
            "cmd": [_venv_py("wecom"), str(ROOT / "wecom" / "wecom_ws_server.py")],
            "cwd": str(ROOT),
            "env": {
                "WECOM_BOT_ID": wc.get("bot_id", ""), "WECOM_BOT_SECRET": wc.get("bot_secret", ""),
                "ALLOWED_USERS": wc.get("allowed_users", ""), "HUB_URL": hub_url, **proxy_env, **voice_env,
            },
        })
    return comps


def _derive_state(meta: dict, st: dict) -> tuple:
    """(显示状态, pid) —— off / needs_setup / connected / error。"""
    alive = bool(st and st["p"] and st["p"].poll() is None)
    pid = st["p"].pid if alive else None
    if not meta["enabled"]:
        return "off", None
    if not meta["creds_ok"]:
        return "needs_setup", pid
    if alive and st["backoff"] == 1:
        return "connected", pid
    return "error", pid


def write_status(state: dict, metas: list) -> None:
    """把当前各渠道状态原子写到 supervisor.json（hub /supervisor 读它）。"""
    channels = []
    for m in metas:
        st = state.get(m["name"])
        s, pid = _derive_state(m, st)
        channels.append({
            "name": m["name"],
            "enabled": m["enabled"],
            "state": s,
            "pid": pid,
            "last_rc": (st["last_rc"] if st else None),
            "restarts": (st["restarts"] if st else 0),
            "backoff": (st["backoff"] if st else 1),
            "last_error": (st["last_error"] if st else None),
        })

    hst = state.get("hub")
    halive = bool(hst and hst["p"] and hst["p"].poll() is None)
    hub_info = {
        "state": "connected" if (halive and hst["backoff"] == 1) else "error",
        "pid": hst["p"].pid if halive else None,
        "restarts": hst["restarts"] if hst else 0,
        "last_error": hst["last_error"] if hst else None,
    }

    out = {"ok": True, "ts": time.time(), "hub": hub_info, "channels": channels}
    try:
        tmp = STATUS_PATH.with_name(STATUS_PATH.name + ".tmp")
        tmp.write_text(json.dumps(out, ensure_ascii=False))
        tmp.replace(STATUS_PATH)
    except Exception as e:
        print(f"[supervisor] 写状态失败：{e}")


def main() -> None:
    cfg = load_cfg()
    comps = build_components(cfg)
    metas = channel_meta(cfg)

    # 修系统 CA 坏：统一用 certifi 证书包（否则飞书/企微 WS 握手报 self-signed certificate）
    certifi_path = _find_certifi([c["cmd"][0] for c in comps])
    if certifi_path:
        print(f"[supervisor] SSL_CERT_FILE={certifi_path}")

    # 代理由 config.toml 全权管理：先把继承来的代理变量清掉，再按需注入，避免外层 shell 的代理泄进子进程
    proxy_keys = ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")

    def _pump_stderr(p, st):
        """逐行读子进程 stderr：tee 给本进程 stderr（launchd 日志照常）+ 留最近若干行做 last_error。"""
        for line in iter(p.stderr.readline, ""):
            sys.stderr.write(line)
            s = line.strip()
            if s:
                st["stderr_tail"].append(s)
        try:
            p.stderr.close()
        except Exception:
            pass

    def start(c: dict, st: dict):
        base = {k: v for k, v in os.environ.items() if k not in proxy_keys}
        base["CHATCC_SUPERVISED"] = "1"  # 渠道读 .env 时只补缺，不覆盖这里注入的 config.toml 值
        if certifi_path:
            base["SSL_CERT_FILE"] = certifi_path
        p = subprocess.Popen(
            c["cmd"], cwd=c["cwd"], env={**base, **c["env"]},
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        st["stderr_tail"].clear()
        threading.Thread(target=_pump_stderr, args=(p, st), daemon=True).start()
        print(f"[supervisor] 起 {c['name']} pid={p.pid}")
        return p

    state = {
        c["name"]: {"c": c, "p": None, "backoff": 1, "last_rc": None,
                    "restarts": 0, "last_error": None, "stderr_tail": deque(maxlen=12)}
        for c in comps
    }
    for st in state.values():
        st["p"] = start(st["c"], st)
    print(f"[supervisor] 共 {len(comps)} 个进程在跑：{', '.join(state)}。Ctrl+C 全停。")
    write_status(state, metas)

    def shutdown(*_):
        print("\n[supervisor] 收到退出信号，停所有子进程…")
        for st in state.values():
            try:
                st["p"].terminate()
            except Exception:
                pass
        try:
            STATUS_PATH.unlink()  # 退出即抹掉状态文件，避免 hub 读到陈旧"在线"
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(2)
        for name, st in state.items():
            if st["p"].poll() is not None:
                rc = st["p"].returncode
                st["last_rc"] = rc
                st["restarts"] += 1
                if rc not in (0, None):
                    # 崩溃：拿 stderr 尾巴最近一条非空行当 last_error
                    st["last_error"] = next((ln for ln in reversed(st["stderr_tail"]) if ln), None)
                print(f"[supervisor] {name} 退出(rc={rc})，{st['backoff']}s 后重启")
                write_status(state, metas)  # 先把"error"刷出去，别等退避结束才可见
                time.sleep(st["backoff"])
                st["backoff"] = min(st["backoff"] * 2, 30)
                st["p"] = start(st["c"], st)
            else:
                if st["backoff"] != 1:
                    st["backoff"] = 1  # 稳定运行则重置退避
                    st["last_error"] = None  # 恢复了就清掉旧错误，状态回到 connected
        write_status(state, metas)


if __name__ == "__main__":
    main()
