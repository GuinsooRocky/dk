#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chat-cc-bot back-pressure —— Ralph loop 的"检查"那一格。

不是单测,是**链路一致性不变量**:验证"同一改动有没有铺满所有渠道、有没有
破坏共享契约"。Ralph 每轮干完一件事跑它,绿了才 commit,否则这一轮作废。
纯 stdlib,不碰任何渠道 venv —— 它检查的是结构契约,不是运行时行为。

退出码:全绿 0,任一红 1。
"""
import ast
import os
import py_compile
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", "__pycache__", ".git", "ralph", "dist", "build"}

# 渠道薄壳 —— 加渠道时在这里登记一行,parity 不变量自动覆盖它。
CHANNEL_SHELLS = {
    "telegram": "telegram/telegram_bot.py",
    "wecom": "wecom/wecom_ws_server.py",
    "feishu": "feishu-claude/feishu_common.py",
}
# 每个渠道薄壳必须走的共享契约(否则就是 drift:某渠道偷偷绕开了 core)。
CONTRACT_MARKERS = ("from core import", "load_env", "hub_client")

# Hub 是唯一承重后端,v1 这些 endpoint 必须在(状态可见化的命脉)。
HUB_FILE = "hub/app.py"
REQUIRED_ENDPOINTS = ("/chat", "/status", "/supervisor", "/health")


def _iter_py():
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for f in fns:
            if f.endswith(".py"):
                yield Path(dp) / f


def check_compile():
    """不变量 1:所有 .py 必须编译通过(语法闸,最便宜的硬信号)。"""
    bad = []
    n = 0
    for p in _iter_py():
        n += 1
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as e:
            bad.append((p, str(e).splitlines()[0]))
    ok = not bad
    detail = f"compiled {n} files" if ok else "; ".join(
        f"{p.relative_to(ROOT)}: {e}" for p, e in bad)
    return ok, detail


def check_channel_parity():
    """不变量 2:每个渠道薄壳都走共享契约(core / load_env / hub_client)。

    防的是"改了 telegram 忘了 wecom/feishu"那类链路没铺完的事故。
    """
    drift = []
    for name, rel in CHANNEL_SHELLS.items():
        p = ROOT / rel
        if not p.exists():
            drift.append(f"{name}: 缺文件 {rel}")
            continue
        src = p.read_text(encoding="utf-8")
        missing = [m for m in CONTRACT_MARKERS if m not in src]
        if missing:
            drift.append(f"{name}: 缺 {missing}")
    return (not drift), ("3 渠道契约齐" if not drift else "; ".join(drift))


def check_lazy_transcribe():
    """不变量 3:core 包不在顶层拉 transcribe(numpy/sherpa),语音保持可选。

    importing core 必须是轻的;telegram 的 transcribe 必须是函数内懒导入。
    """
    problems = []
    core_init = (ROOT / "core/__init__.py").read_text(encoding="utf-8")
    if re.search(r"^\s*(from\s+\.?transcribe|from\s+core\.transcribe|import\s+.*transcribe)",
                 core_init, re.M):
        problems.append("core/__init__.py 顶层拉了 transcribe")
    # telegram:transcribe 只能在函数体内(缩进)出现,不能在模块顶层(列 0)
    tg = (ROOT / "telegram/telegram_bot.py").read_text(encoding="utf-8")
    for m in re.finditer(r"^(\s*)from core import transcribe", tg, re.M):
        if m.group(1) == "":
            problems.append("telegram 顶层 import transcribe(应函数内懒导入)")
    return (not problems), ("懒导入完好" if not problems else "; ".join(problems))


def check_hub_endpoints():
    """不变量 4:Hub 暴露 v1 承重 endpoint(/supervisor 等状态命脉不能丢)。"""
    src = (ROOT / HUB_FILE).read_text(encoding="utf-8")
    missing = [e for e in REQUIRED_ENDPOINTS if f'"{e}"' not in src and f"'{e}'" not in src]
    return (not missing), ("endpoint 齐" if not missing else f"缺 {missing}")


CHECKS = [
    ("compile     全量编译", check_compile),
    ("parity      渠道契约一致", check_channel_parity),
    ("lazy-voice  语音可选", check_lazy_transcribe),
    ("hub-api     承重 endpoint", check_hub_endpoints),
]


def main() -> int:
    print("=== chat-cc-bot 链路一致性冒烟 ===")
    all_ok = True
    for label, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:  # 检查自身炸了也算红,别假绿
            ok, detail = False, f"检查异常: {e}"
        all_ok &= ok
        print(f"  [{'✅' if ok else '❌'}] {label}: {detail}")
    print("=== " + ("全绿 ✅ 可以 commit" if all_ok else "有红 ❌ 这轮作废") + " ===")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
