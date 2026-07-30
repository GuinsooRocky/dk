"""外层包裹接线的检查：不起 claude、不花钱，只验参数拼装与 fail-closed 分支。

跟 outer-sandbox-probe.sh 的分工：
  outer-sandbox-probe.sh  真起 claude，验沙箱**行为**（读得到/读不到、能不能外传）
  outer-wiring-check.py   不起 claude，验**接线**（前缀怎么拼、配置坏掉时是不是真拒跑）

后者盖的是探针盖不到的地方：配置写错时代码有没有老老实实 fail-closed。
改 core/sandbox.py 的外层包裹部分之后跑一下：python3 scripts/outer-wiring-check.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import sandbox  # noqa: E402

HOME = Path.home()
CLAUDE = HOME / ".local/bin/claude"
CLI = HOME / ".local/lib/srt/node_modules/@anthropic-ai/sandbox-runtime/dist/cli.js"
NODE = HOME / ".local/bin/node"


class Cfg:
    def __init__(self, **kw):
        self.outer_sandbox = kw.get("outer_sandbox", False)
        self.srt_settings = kw.get("srt_settings", "")
        self.srt_cli = kw.get("srt_cli", "")
        self.srt_node = kw.get("srt_node", "")


def write_srt(tmp, allow_read):
    p = Path(tmp) / "srt.json"
    p.write_text(json.dumps({
        "filesystem": {"denyRead": [str(HOME)], "allowRead": allow_read,
                       "allowWrite": ["."], "denyWrite": []},
        "network": {"allowedDomains": ["api.anthropic.com"], "deniedDomains": []},
    }))
    return str(p)


ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}  {detail}")


tmp = tempfile.mkdtemp(prefix="dk-wiring-")
work = Path(tmp) / "work"
work.mkdir()

print("1. 没开外层包裹 → 前缀为空，行为跟以前一致")
check("返回 []", sandbox.outer_wrap_prefix(Cfg(), work, {}) == [])

print("2. 开了但没给 DK_SRT_SETTINGS → fail-closed")
try:
    sandbox.outer_wrap_prefix(Cfg(outer_sandbox=True), work, {})
    check("应该抛异常", False, "没抛")
except sandbox.OuterSandboxError as e:
    check("抛了 OuterSandboxError", "DK_SRT_SETTINGS" in str(e), str(e))

print("3. srt 配置文件不存在 → fail-closed")
try:
    sandbox.outer_wrap_prefix(Cfg(outer_sandbox=True, srt_settings="/nope/x.json"), work, {})
    check("应该抛异常", False, "没抛")
except sandbox.OuterSandboxError as e:
    check("抛了并指出路径", "/nope/x.json" in str(e), str(e))

print("4. srt cli.js 不存在 → fail-closed")
s = write_srt(tmp, ["."])
try:
    sandbox.outer_wrap_prefix(
        Cfg(outer_sandbox=True, srt_settings=s, srt_cli="/nope/cli.js"), work, {})
    check("应该抛异常", False, "没抛")
except sandbox.OuterSandboxError as e:
    check("抛了并提示装法", "install-srt.sh" in str(e), str(e))

print("5. allowRead 盖不到 claude 二进制 → 提前炸（别等 command not found）")
s = write_srt(tmp, ["."])
try:
    sandbox.outer_wrap_prefix(
        Cfg(outer_sandbox=True, srt_settings=s), work, {"claude 二进制": str(CLAUDE)})
    check("应该抛异常", False, "没抛")
except sandbox.OuterSandboxError as e:
    check("点名了 claude 二进制", "claude 二进制" in str(e), str(e))

print("6. 软链方向要跟实测一致（沙箱认字面路径，不认 resolve 后的真身）")
# 实测 C：只放行软链那头就能跑 → 检查也该放行
s = write_srt(tmp, [".", str(HOME / ".local/bin")])
try:
    sandbox.outer_wrap_prefix(
        Cfg(outer_sandbox=True, srt_settings=s), work, {"claude 二进制": str(CLAUDE)})
    check("只放行软链那头 → 通过", True)
except sandbox.OuterSandboxError as e:
    check("只放行软链那头 → 通过", False, str(e))
# 实测 A：只放行真身、却用软链路径调 → 运行时 Operation not permitted，检查必须提前炸
s = write_srt(tmp, [".", str(HOME / ".local/share/claude")])
try:
    sandbox.outer_wrap_prefix(
        Cfg(outer_sandbox=True, srt_settings=s), work, {"claude 二进制": str(CLAUDE)})
    check("只放行真身+用软链调 → 提前炸", False, "没抛，会拖到运行时才炸")
except sandbox.OuterSandboxError as e:
    check("只放行真身+用软链调 → 提前炸", "claude 二进制" in str(e), str(e))

print("7. 配置齐全 → 拼出正确前缀，且带 -- 分隔")
s = write_srt(tmp, [".", str(HOME / ".local/bin"), str(HOME / ".local/share/claude")])
pref = sandbox.outer_wrap_prefix(
    Cfg(outer_sandbox=True, srt_settings=s), work, {"claude 二进制": str(CLAUDE)})
check("node 在首位", pref[0] == str(NODE), pref[:1])
check("接 cli.js", pref[1] == str(CLI), pref[1:2])
check("带 -s <配置>", pref[2] == "-s" and pref[3] == s, pref[2:4])
check("末尾是 --（srt 会抢 --settings）", pref[-1] == "--", pref[-1:])

print("8. allowRead 里的 '.' 按 work_dir 解析")
s = write_srt(tmp, ["."])
try:
    sandbox.outer_wrap_prefix(
        Cfg(outer_sandbox=True, srt_settings=s), work, {"工作目录内的文件": str(work / "a.txt")})
    check("work_dir 内的路径算被盖到", True)
except sandbox.OuterSandboxError as e:
    check("work_dir 内的路径算被盖到", False, str(e))

print(f"\n通过 {ok}，失败 {fail}")
sys.exit(1 if fail else 0)
