"""DK sidecar —— PyInstaller 冻结后的统一入口（A1）。

按 argv[1] 分发：supervisor（默认）/ hub / telegram / feishu / wecom。
frozen 时 supervisor 用 sys.executable(=本二进制) + 模式名起子进程，替代 5 个 venv python。
dev 下也能直接 `python sidecar.py <mode>` 跑（与原 venv 脚本等价）。

注意：repo 的 telegram/ 目录名与 PyPI 的 telegram 包同名 —— 用 `import telegram_bot`
（顶层模块名，不撞）而非 `from telegram import ...`；各入口的 sys.path 按需补。
"""
import os
import sys
from pathlib import Path

# 配置根：frozen 时 __file__ 在 bundle 内不可靠 → 优先 DK_ROOT（launchd/supervisor 注入）
ROOT = Path(os.environ.get("DK_ROOT") or Path(__file__).resolve().parent)


def _add(*parts):
    for p in parts:
        sp = str(ROOT.joinpath(*p)) if p else str(ROOT)
        if sp not in sys.path:
            sys.path.insert(0, sp)


def _supervisor():
    _add(())
    import supervisor
    supervisor.main()


def _hub():
    _add(())
    from hub import app as hub_app
    hub_app.main()


def _telegram():
    _add((), ("telegram",))
    import telegram_bot
    telegram_bot.main()


def _feishu():
    _add((), ("feishu-claude",))
    import feishu_ws_server
    feishu_ws_server.main()


def _wecom():
    import asyncio
    _add((), ("wecom",))
    import wecom_ws_server
    asyncio.run(wecom_ws_server.amain())


_MODES = {
    "supervisor": _supervisor,
    "hub": _hub,
    "telegram": _telegram,
    "feishu": _feishu,
    "wecom": _wecom,
}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "supervisor"
    fn = _MODES.get(mode)
    if fn is None:
        sys.stderr.write(f"[sidecar] 未知模式: {mode}（应为 {'/'.join(_MODES)}）\n")
        sys.exit(2)
    fn()


if __name__ == "__main__":
    main()
