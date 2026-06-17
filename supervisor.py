"""supervisor —— 一条命令起全部。

读 config.toml → 起 hub + 所有 enabled 渠道（各用自己的 venv）→ 崩溃指数退避自愈。
配置注入走子进程环境变量（子进程代码零改，继续 os.getenv）。Ctrl+C 全部停。

跑：python3 supervisor.py
"""
import os
import sys
import time
import signal
import subprocess
from pathlib import Path

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:
    print("需要 Python 3.11+（tomllib）"); sys.exit(1)

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.toml"


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


def main() -> None:
    cfg = load_cfg()
    comps = build_components(cfg)

    # 修系统 CA 坏：统一用 certifi 证书包（否则飞书/企微 WS 握手报 self-signed certificate）
    certifi_path = _find_certifi([c["cmd"][0] for c in comps])
    if certifi_path:
        print(f"[supervisor] SSL_CERT_FILE={certifi_path}")

    # 代理由 config.toml 全权管理：先把继承来的代理变量清掉，再按需注入，避免外层 shell 的代理泄进子进程
    proxy_keys = ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")

    def start(c: dict):
        base = {k: v for k, v in os.environ.items() if k not in proxy_keys}
        if certifi_path:
            base["SSL_CERT_FILE"] = certifi_path
        p = subprocess.Popen(c["cmd"], cwd=c["cwd"], env={**base, **c["env"]})
        print(f"[supervisor] 起 {c['name']} pid={p.pid}")
        return p

    state = {c["name"]: {"c": c, "p": start(c), "backoff": 1} for c in comps}
    print(f"[supervisor] 共 {len(comps)} 个进程在跑：{', '.join(state)}。Ctrl+C 全停。")

    def shutdown(*_):
        print("\n[supervisor] 收到退出信号，停所有子进程…")
        for st in state.values():
            try:
                st["p"].terminate()
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
                print(f"[supervisor] {name} 退出(rc={rc})，{st['backoff']}s 后重启")
                time.sleep(st["backoff"])
                st["backoff"] = min(st["backoff"] * 2, 30)
                st["p"] = start(st["c"])
            else:
                st["backoff"] = 1  # 稳定运行则重置退避


if __name__ == "__main__":
    main()
