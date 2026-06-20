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

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from core import config as core_config  # noqa: E402

FROZEN = getattr(sys, "frozen", False)   # PyInstaller sidecar 打包后为 True
ROOT = core_config.app_root()            # frozen=DK_ROOT(launchd 注入)；dev=仓库根

CONFIG = ROOT / "config.toml"
STATUS_PATH = core_config.supervisor_status_path()
RELOAD_PATH = core_config.reload_request_path()
RELOAD_ALL_PATH = core_config.reload_all_request_path()
RUNTIME_DIR = core_config.runtime_dir()


def load_cfg() -> dict:
    if not CONFIG.exists():
        print(f"没有 config.toml。先 `cp config.example.toml config.toml` 填好再跑。")
        sys.exit(1)
    with open(CONFIG, "rb") as f:
        return tomllib.load(f)


def _venv_py(sub: str) -> str:
    return str(ROOT / sub / ".venv" / "bin" / "python")


def _find_certifi(venv_pythons) -> str:
    """本机系统 CA 坏（链里有自签名证书）→ 找一个 certifi 干净证书包，给子进程统一用。"""
    if FROZEN:
        try:
            import certifi
            return certifi.where()   # bundle 内自带 certifi
        except Exception:
            return ""
    for py in venv_pythons:
        try:
            r = subprocess.run([py, "-m", "certifi"], capture_output=True, text=True, timeout=10)
            path = r.stdout.strip()
            if path and Path(path).exists():
                return path
        except Exception:
            pass
    return ""


def _stop(p, kill_after: float = 5.0) -> None:
    """停一个子进程及其整个进程组（hub 会 fork claude 孙进程，只 terminate 父进程会留孤儿），
    超时未退再 SIGKILL，并 wait 回收避免僵尸/端口未释放。"""
    if p is None:
        return
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            p.terminate()
        except Exception:
            pass
    try:
        p.wait(timeout=kill_after)
    except Exception:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        try:
            p.wait(timeout=2)
        except Exception:
            pass


def _new_state(c: dict) -> dict:
    """单渠道/进程的运行时状态。restart_at：>0 表示已死、待到点重启（非阻塞退避）。"""
    return {"c": c, "p": None, "backoff": 1, "last_rc": None, "restarts": 0,
            "last_error": None, "restart_at": 0.0, "stderr_tail": deque(maxlen=12)}


def channel_meta(cfg: dict) -> list:
    """所有已知渠道（含未启用）的元信息，用于状态展示：是否启用 + 凭证是否齐。

    凭证可放 config.toml 或渠道 .env（很多人只放 .env），两处任一有值即算齐。
    凭证不齐（缺 token/secret，或白名单为空=没人能用）→ 状态 needs_setup。
    """
    def has(cfg_val, env_path, env_key):
        return bool((cfg_val or "").strip()) or bool(core_config.read_env_value(env_path, env_key))

    tg = cfg.get("telegram", {})
    fs = cfg.get("feishu", {})
    wc = cfg.get("wecom", {})
    tg_env = ROOT / "telegram" / ".env"
    fs_env = ROOT / "feishu-claude" / ".env"
    wc_env = ROOT / "wecom" / ".env"
    return [
        {"name": "telegram", "enabled": bool(tg.get("enabled")),
         "creds_ok": has(tg.get("token"), tg_env, "TELEGRAM_BOT_TOKEN")
                     and has(tg.get("allowed_users"), tg_env, "ALLOWED_USERS")},
        {"name": "feishu", "enabled": bool(fs.get("enabled")),
         "creds_ok": has(fs.get("app_id"), fs_env, "FEISHU_APP_ID")
                     and has(fs.get("app_secret"), fs_env, "FEISHU_APP_SECRET")
                     and has(fs.get("allowed_users"), fs_env, "ALLOWED_USERS")},
        {"name": "wecom", "enabled": bool(wc.get("enabled")),
         "creds_ok": has(wc.get("bot_id"), wc_env, "WECOM_BOT_ID")
                     and has(wc.get("bot_secret"), wc_env, "WECOM_BOT_SECRET")
                     and has(wc.get("allowed_users"), wc_env, "ALLOWED_USERS")},
    ]


def _cmd(mode: str, dev_cmd: list) -> list:
    """frozen → 本 sidecar 二进制 + 模式名；dev → 渠道 venv python。"""
    return [sys.executable, mode] if FROZEN else dev_cmd


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
        "cmd": _cmd("hub", [_venv_py("hub"), "-m", "hub.app"]),
        "cwd": str(ROOT),
        "env": {**claude_env, **proxy_env},  # hub 跑 claude，要代理
    }]

    tg = cfg.get("telegram", {})
    if tg.get("enabled"):
        comps.append({
            "name": "telegram",
            "cmd": _cmd("telegram", [_venv_py("telegram"), str(ROOT / "telegram" / "telegram_bot.py")]),
            "cwd": str(ROOT / "telegram"),
            "env": {
                "TELEGRAM_BOT_TOKEN": tg.get("token", ""),
                # 白名单不从 config.toml 注入：渠道启动读自己的 .env ALLOWED_USERS，
                # 这样 app 改白名单(写 .env + 重启渠道)才生效（否则注入值会盖死 .env）
                "TRIGGER_PREFIX": tg.get("trigger_prefix", "/c "),
                # 代理只给 hub（跑 claude）用；Telegram 走直连（Clash 7897 到不了 Telegram）
                "HUB_URL": hub_url, **voice_env,
            },
        })

    fs = cfg.get("feishu", {})
    if fs.get("enabled"):
        comps.append({
            "name": "feishu",
            "cmd": _cmd("feishu", [_venv_py("feishu-claude"), str(ROOT / "feishu-claude" / "feishu_ws_server.py")]),
            "cwd": str(ROOT),
            "env": {
                "FEISHU_APP_ID": fs.get("app_id", ""), "FEISHU_APP_SECRET": fs.get("app_secret", ""),
                # 白名单走渠道 .env（见 telegram 处说明），不从 config.toml 注入
                "HUB_URL": hub_url, **voice_env,
            },
        })

    wc = cfg.get("wecom", {})
    if wc.get("enabled"):
        comps.append({
            "name": "wecom",
            "cmd": _cmd("wecom", [_venv_py("wecom"), str(ROOT / "wecom" / "wecom_ws_server.py")]),
            "cwd": str(ROOT),
            "env": {
                "WECOM_BOT_ID": wc.get("bot_id", ""), "WECOM_BOT_SECRET": wc.get("bot_secret", ""),
                # 白名单走渠道 .env（见 telegram 处说明），不从 config.toml 注入
                "HUB_URL": hub_url, **voice_env,
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
        base["DK_ROOT"] = str(ROOT)      # 子进程(含 frozen sidecar)据此找 config.toml/.env
        if certifi_path:
            base["SSL_CERT_FILE"] = certifi_path
        # 只注入 config.toml 里有值的项：空字符串别注入，否则会盖住渠道 .env 里的真实凭证
        # （凭证可在 .env，config.toml 仅 enabled=true 留空时，让 .env 补上）。
        inject = {k: v for k, v in c["env"].items() if v != ""}
        p = subprocess.Popen(
            c["cmd"], cwd=c["cwd"], env={**base, **inject},
            stderr=subprocess.PIPE, text=True, bufsize=1,
            start_new_session=True,   # 独立进程组：停止时能连 hub fork 出的 claude 孙进程一起收
        )
        st["stderr_tail"].clear()
        threading.Thread(target=_pump_stderr, args=(p, st), daemon=True).start()
        print(f"[supervisor] 起 {c['name']} pid={p.pid}")
        return p

    state = {c["name"]: _new_state(c) for c in comps}
    for st in state.values():
        st["p"] = start(st["c"], st)
    print(f"[supervisor] 共 {len(comps)} 个进程在跑：{', '.join(state)}。Ctrl+C 全停。")
    write_status(state, metas)

    def shutdown(*_):
        print("\n[supervisor] 收到退出信号，停所有子进程…")
        for st in state.values():
            _stop(st["p"])   # 连进程组一起停并 wait 回收，别留孤儿/占端口
        try:
            STATUS_PATH.unlink()  # 退出即抹掉状态文件，避免 hub 读到陈旧"在线"
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(2)
        # 整体重启：改了影响 hub 环境的配置（如代理）→ 全停全起
        if RELOAD_ALL_PATH.exists():
            try:
                RELOAD_ALL_PATH.unlink()
            except Exception:
                pass
            print("[supervisor] 整体重启（配置变更，如代理）…")
            cfg = load_cfg()
            metas = channel_meta(cfg)
            for st in state.values():
                _stop(st["p"])   # 连进程组一起停并 wait，确保端口/连接释放后再起新的
            comps = build_components(cfg)
            state = {c["name"]: _new_state(c) for c in comps}
            for st in state.values():
                st["p"] = start(st["c"], st)
            write_status(state, metas)
            continue
        # 单渠道重启：白名单改了 → 重启相关渠道（它们启动时重读自己的 .env，新白名单生效）。
        # 按 restart_channel.<name> 文件排空，避免一个 tick 内多次编辑互相覆盖丢单。
        restart_markers = list(RUNTIME_DIR.glob("restart_channel.*"))
        if restart_markers:
            cfg = load_cfg()
            metas = channel_meta(cfg)   # 刷新 metas，避免白名单状态显示持续过期
            for mp in restart_markers:
                try:
                    name = mp.name.split(".", 1)[1]
                    mp.unlink()
                except Exception:
                    continue
                if name in state and name != "hub":
                    print(f"[supervisor] 重启渠道 {name}（白名单变更）")
                    _stop(state[name]["p"])
                    state[name]["backoff"] = 1
                    state[name]["restart_at"] = 0.0
                    state[name]["last_error"] = None
                    state[name]["p"] = start(state[name]["c"], state[name])
            write_status(state, metas)
            continue
        # 热重载：hub 改了 config.toml 会 touch reload 标记 → 起新启用 / 停新禁用的渠道（hub 不动）
        if RELOAD_PATH.exists():
            try:
                RELOAD_PATH.unlink()
            except Exception:
                pass
            cfg = load_cfg()
            metas = channel_meta(cfg)
            new_comps = {c["name"]: c for c in build_components(cfg)}
            for name in list(state):
                if name not in new_comps:   # 被禁用（hub 永远在 new_comps 里）
                    print(f"[supervisor] 渠道 {name} 被禁用，停掉")
                    _stop(state[name]["p"])
                    del state[name]
            for name, c in new_comps.items():
                if name not in state:       # 被启用
                    print(f"[supervisor] 渠道 {name} 被启用，起")
                    st = _new_state(c)
                    st["p"] = start(c, st)
                    state[name] = st
            write_status(state, metas)
        now = time.monotonic()
        for name, st in state.items():
            if st["p"].poll() is None:
                # 活着：稳定运行则重置退避（restart_at==0 表示不在待重启态）
                if st["restart_at"] == 0.0 and st["backoff"] != 1:
                    st["backoff"] = 1
                    st["last_error"] = None  # 恢复了就清掉旧错误，状态回到 connected
                continue
            # 已退出。restart_at==0 → 刚发现，登记错误并按退避排定重启时刻（不在循环里 sleep，
            # 否则一个 flapping 渠道会把全局监控/热重载卡死最多 30s）
            if st["restart_at"] == 0.0:
                rc = st["p"].returncode
                st["last_rc"] = rc
                st["restarts"] += 1
                if rc not in (0, None):
                    st["last_error"] = next((ln for ln in reversed(st["stderr_tail"]) if ln), None)
                print(f"[supervisor] {name} 退出(rc={rc})，{st['backoff']}s 后重启")
                st["restart_at"] = now + st["backoff"]
                write_status(state, metas)  # 先把"error"刷出去，别等退避到点才可见
            elif now >= st["restart_at"]:
                st["restart_at"] = 0.0
                st["backoff"] = min(st["backoff"] * 2, 30)
                st["p"] = start(st["c"], st)
        write_status(state, metas)


if __name__ == "__main__":
    main()
