#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DK back-pressure —— Ralph loop 的"检查"那一格。

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
REQUIRED_ENDPOINTS = ("/chat", "/status", "/supervisor", "/health", "/notify")


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


def check_swift_build():
    """不变量 5:macapp 原生 app 必须 swift build 过(app 侧 back-pressure)。

    macapp/ 不存在 → 跳过(后端单跑也算绿);swift 没装 → 跳过并提示。
    """
    import shutil
    import subprocess
    pkg = ROOT / "macapp" / "Package.swift"
    if not pkg.exists():
        return True, "无 macapp,跳过"
    if not shutil.which("swift"):
        return True, "swift 未装,跳过(装了才验 app)"
    r = subprocess.run(["swift", "build"], cwd=ROOT / "macapp",
                       capture_output=True, text=True)
    if r.returncode == 0:
        return True, "swift build 过"
    tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
    return False, "swift build 失败: " + " | ".join(tail)


def check_voice_autodownload():
    """不变量 6：语音模型缺失走自动下载、不再裸 raise（V1）。

    结构断言：sensevoice 有 _ensure_model 下载函数，且 _recognizer 经它取模型
    （缺模型不再当场 FileNotFoundError）。不真跑下载（228MB，留人工验收）。
    """
    src = (ROOT / "core/transcribe/sensevoice.py").read_text(encoding="utf-8")
    problems = []
    if "_ensure_model" not in src:
        problems.append("缺自动下载函数 _ensure_model")
    tree = ast.parse(src)
    rec_fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "_recognizer"), None)
    if rec_fn is None:
        problems.append("找不到 _recognizer")
    else:
        body = ast.get_source_segment(src, rec_fn) or ""
        if "_ensure_model" not in body:
            problems.append("_recognizer 没走 _ensure_model")
        if any(isinstance(n, ast.Raise) for n in ast.walk(rec_fn)):
            problems.append("_recognizer 仍裸 raise（缺模型应交给 _ensure_model 下载）")
    return (not problems), ("语音自动下载就位" if not problems else "; ".join(problems))


def check_notify_endpoint():
    """不变量 7：出站通知端点齐 + 鉴权（N-M0 + N-M2）。

    N-M0：hub 暴露 /notify + NotifyIn + /config/notify。
    N-M2：/notify 校验 X-Notify-Token（不匹配 403）；token 写 .notify_token 且 0600。
    """
    src = (ROOT / HUB_FILE).read_text(encoding="utf-8")
    nfy = (ROOT / "hub/notify.py").read_text(encoding="utf-8")
    need = {
        "/notify 路由": '"/notify"' in src or "'/notify'" in src,
        "NotifyIn 模型": "class NotifyIn" in src,
        "/config/notify": '"/config/notify"' in src or "'/config/notify'" in src,
        "X-Notify-Token 校验": "x_notify_token" in src or "X-Notify-Token" in src,
        "403 拒绝": "403" in src,
        ".notify_token 0600": ".notify_token" in nfy and "0o600" in nfy,
        # N-M6：24h 残留清扫 + runner 回调默认关
        "24h 路由清扫": "purge_stale_routes" in nfy,
        "runner 回调默认关": "DK_RUNNER_NOTIFY" in (ROOT / "core/runner.py").read_text(encoding="utf-8"),
        # N-M5：/notify 对企微有明确分支（诚实报错改投）
        "企微明确分支": 'channel == "wecom"' in nfy,
    }
    missing = [k for k, ok in need.items() if not ok]
    return (not missing), ("出站通知端点+鉴权+收尾齐" if not missing else "缺 " + ", ".join(missing))


def check_notify_hook():
    """不变量 8：SessionEnd hook + 注册 CLI 就位（N-M1）。

    notify_hook.py：排除 bot work_dir + 查 CHATCC_SUPERVISED + 永远 exit 0（P0 防自循环）。
    watch.py：有 register/unregister，且**不**按 file mtime 认 session（反向断言，铁律）。
    """
    problems = []
    hook = ROOT / "hub/notify_hook.py"
    if not hook.exists():
        problems.append("缺 hub/notify_hook.py")
    else:
        h = hook.read_text(encoding="utf-8")
        if "workdir" not in h.lower():
            problems.append("hook 没排除 bot work_dir")
        if "CHATCC_SUPERVISED" not in h:
            problems.append("hook 没查 CHATCC_SUPERVISED")
        if "sys.exit(0)" not in h:
            problems.append("hook 没保证 exit 0")
        # N-M3：容残 transcript 解析器 + 降级文案常量
        if "parse_transcript" not in h:
            problems.append("hook 缺 transcript 解析器")
        if "摘要不可用" not in h:
            problems.append("hook 缺残读降级文案")
    watch = ROOT / "hub/watch.py"
    if not watch.exists():
        problems.append("缺 hub/watch.py")
    else:
        w = watch.read_text(encoding="utf-8")
        if "register" not in w or "unregister" not in w:
            problems.append("watch 缺 register/unregister")
        if re.search(r"st_mtime|getmtime", w):   # 反向断言：绝不用 file mtime 认 session（铁律）
            problems.append("watch 用了 file mtime 认 session（违反铁律）")
    return (not problems), ("hook+注册 CLI 就位" if not problems else "; ".join(problems))


def check_trust_tier():
    """不变量 9：渠道信任分级字段就位（T1）。

    ChannelMeta 含 trustTier，且 KNOWN_CHANNELS 三条都显式给了值（§6.3 插件生态预留）。
    macapp 不存在 → 跳过（同 swift-app）。
    """
    p = ROOT / "macapp/Sources/ChatCCBot/Models.swift"
    if not p.exists():
        return True, "无 macapp，跳过"
    src = p.read_text(encoding="utf-8")
    problems = []
    if "trustTier" not in src:
        problems.append("ChannelMeta 缺 trustTier")
    n = src.count('trustTier: "')   # 只数 .init 里的显式赋值（struct 定义是 trustTier: String，不计）
    if n < 3:
        problems.append(f"KNOWN_CHANNELS trustTier 显式值不足（{n}/3）")
    return (not problems), ("trust_tier 字段就位" if not problems else "; ".join(problems))


def check_health_probe():
    """不变量 10：渠道鉴权探针就位（P1）。

    hub 有周期探针 + /supervisor 输出含 auth_ok + 三渠道各有分支（tg/feishu 主动探、
    wecom 靠心跳反推）。
    """
    app = (ROOT / HUB_FILE).read_text(encoding="utf-8")
    problems = []
    if "_probe_health_loop" not in app:
        problems.append("hub 缺周期健康探针")
    if "auth_ok" not in app:
        problems.append("/supervisor 没输出 auth_ok")
    if '_set_health("wecom"' not in app:
        problems.append("探针缺 wecom 分支")
    h = ROOT / "hub/health.py"
    if not h.exists():
        problems.append("缺 hub/health.py")
    else:
        hs = h.read_text(encoding="utf-8")
        for fn in ("probe_telegram", "probe_feishu"):
            if fn not in hs:
                problems.append(f"health 缺 {fn}")
    return (not problems), ("鉴权探针就位" if not problems else "; ".join(problems))


def check_ratelimit():
    """不变量 11：出站限速器就位（R1）。

    core/ratelimit.py 有 token-bucket，且被 notify pusher + 三渠道分块回复都引用（parity）。
    """
    problems = []
    rl = ROOT / "core/ratelimit.py"
    if not rl.exists():
        problems.append("缺 core/ratelimit.py")
    else:
        s = rl.read_text(encoding="utf-8")
        if "TokenBucket" not in s or "try_acquire" not in s:
            problems.append("ratelimit 缺 token-bucket/try_acquire")
    if "ratelimit" not in (ROOT / "hub/notify.py").read_text(encoding="utf-8"):
        problems.append("notify pusher 没用 ratelimit")
    for ch, f in (("telegram", "telegram/telegram_bot.py"),
                  ("feishu", "feishu-claude/feishu_common.py"),
                  ("wecom", "wecom/wecom_ws_server.py")):
        if "ratelimit" not in (ROOT / f).read_text(encoding="utf-8"):
            problems.append(f"{ch} 分块回复没接 ratelimit")
    return (not problems), ("出站限速器就位" if not problems else "; ".join(problems))


def check_fair_queue():
    """不变量 12：per-guest 公平队列就位（Q1）。

    hub 有队列结构（FIFO 串行闸 + 深度上限）+ 位次计算 + FIFO 取出；runner Slots 单飞语义未变。
    """
    app = (ROOT / HUB_FILE).read_text(encoding="utf-8")
    problems = []
    if "_chat_serial" not in app or "_CHAT_MAX_QUEUE" not in app:
        problems.append("hub 缺公平队列结构")
    if "position" not in app:
        problems.append("缺位次计算")
    if "_chat_serial.acquire" not in app:   # asyncio.Lock 按 FIFO 唤醒 = 按序取出
        problems.append("队列非 FIFO 取出")
    run = (ROOT / "core/runner.py").read_text(encoding="utf-8")
    if "Semaphore(max(1, n))" not in run:   # 单飞闸语义未被动过（反向断言）
        problems.append("runner Slots 单飞语义被改了")
    return (not problems), ("公平队列就位" if not problems else "; ".join(problems))


def check_wizard_skeleton():
    """不变量 13：§4 向导骨架就位（W1，W2/W3 续扩）。macapp 不存在跳过。

    存在 WizardStep 状态机 + 向导复用 ClaudeCheck。视觉/流程对不对留 visual-qa 人工收尾。
    """
    if not (ROOT / "macapp" / "Package.swift").exists():
        return True, "无 macapp，跳过"
    p = ROOT / "macapp/Sources/ChatCCBot/WizardView.swift"
    if not p.exists():
        return False, "缺 WizardView.swift"
    src = p.read_text(encoding="utf-8")
    problems = []
    if "enum WizardStep" not in src:
        problems.append("缺 WizardStep 状态机")
    if "ClaudeCheck" not in src:
        problems.append("Step1 没复用 ClaudeCheck")
    return (not problems), ("向导骨架就位" if not problems else "; ".join(problems))


CHECKS = [
    ("compile     全量编译", check_compile),
    ("parity      渠道契约一致", check_channel_parity),
    ("lazy-voice  语音可选", check_lazy_transcribe),
    ("hub-api     承重 endpoint", check_hub_endpoints),
    ("swift-app   macapp 编译", check_swift_build),
    ("voice-dl    语音缺失自动下载", check_voice_autodownload),
    ("notify-api  出站通知端点", check_notify_endpoint),
    ("notify-hook hook+注册CLI", check_notify_hook),
    ("trust-tier  渠道信任分级", check_trust_tier),
    ("health      渠道鉴权探针", check_health_probe),
    ("ratelimit   出站限速器", check_ratelimit),
    ("fair-queue  公平队列", check_fair_queue),
    ("wizard      §4 向导骨架", check_wizard_skeleton),
]


def main() -> int:
    print("=== DK 链路一致性冒烟 ===")
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
