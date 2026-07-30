"""沙箱验证：判断给 claude 的 --settings 是否真把它关进沙箱（GUARD-2/3 共用判据）。

写/全权工具只有在沙箱确实生效时才安全自动放行。判据（全真才算 verified）：
  1. CLAUDE_SETTINGS 指向的文件存在；
  2. 文件里 sandbox.enabled == true 且 sandbox.failIfUnavailable == true
     （这两字段嵌在顶层 "sandbox" key 下，按平铺读会永远验不过）；
  3. 本机 sandbox-exec 能起一个最小 profile（macOS 沙箱机制可用）。
"""
import json
import time
import subprocess
from pathlib import Path


def _settings_ok(settings_path: str) -> bool:
    if not settings_path:
        return False
    p = Path(settings_path).expanduser()
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text())
    except Exception:
        return False
    sb = data.get("sandbox") or {}
    return bool(sb.get("enabled")) and bool(sb.get("failIfUnavailable"))


_exec_ok_cache = None
_exec_ok_at = 0.0
_EXEC_TTL = 60   # 秒：缓存带 TTL，避免机制运行期失效后永久 fail-open（仍报已验证→不剥危险工具）


def _sandbox_exec_ok() -> bool:
    """sandbox-exec 能起最小 profile 即认为机制可用。带 TTL 缓存，避免每条消息都 fork 探测，
    又不至于像永久缓存那样在机制中途失效后一直误判可用。"""
    global _exec_ok_cache, _exec_ok_at
    now = time.monotonic()
    if _exec_ok_cache is None or now - _exec_ok_at > _EXEC_TTL:
        try:
            r = subprocess.run(
                ["sandbox-exec", "-p", "(version 1)(allow default)", "true"],
                capture_output=True, timeout=5,
            )
            _exec_ok_cache = (r.returncode == 0)
        except Exception:
            _exec_ok_cache = False
        _exec_ok_at = now
    return _exec_ok_cache


def status(settings_path: str) -> dict:
    """给 hub /sandbox 用：判据细节 + 总 verified。"""
    settings = _settings_ok(settings_path)
    execable = _sandbox_exec_ok()
    return {
        "settings_path": settings_path or "",
        "settings_ok": settings,
        "sandbox_exec_ok": execable,
        "verified": bool(settings and execable),
    }


def verified(settings_path: str) -> bool:
    return status(settings_path)["verified"]


# ————————————————————————————————————————————————————————————————
# 外层包裹（allow-list 姿态）。上面那套管的是 claude 内置的 sandbox.*，
# 只包 Bash 起的子进程；claude 自己的 Read/Grep/WebFetch 不在里面。
# 这里是从**进程外**用 srt 把整个 claude 包住，那些工具才一起落进 OS 边界。
# 实测数据与踩坑见 SANDBOX.md、scripts/outer-sandbox-probe.sh。
# ————————————————————————————————————————————————————————————————

class OuterSandboxError(RuntimeError):
    """外层包裹装不起来。**永远 fail-closed**：宁可这条消息不跑，也不裸跑。

    跟 sandbox.failIfUnavailable 同一个道理 —— 静默降级成"没有沙箱"是最坏的结果，
    因为外面看起来一切正常。"""


# 默认落点，跟 node 版本解绑（nvm 升级不会带走）。装法见 scripts/install-srt.sh
_DEFAULT_SRT_CLI = "~/.local/lib/srt/node_modules/@anthropic-ai/sandbox-runtime/dist/cli.js"


def _resolve_srt(cfg) -> tuple:
    """定位 (node, cli.js)，都要绝对路径。

    ⚠ 不能调 `node_modules/.bin/srt` 那个 shim：它的 shebang 是 `#!/usr/bin/env node`，
    而 launchd 给的 PATH 只有 /usr/bin:/bin:/usr/sbin:/sbin，实测直接
    `env: node: No such file or directory`。所以显式用绝对 node 跑 cli.js。"""
    cli = (getattr(cfg, "srt_cli", "") or _DEFAULT_SRT_CLI)
    cli_p = Path(cli).expanduser()
    if not cli_p.is_file():
        raise OuterSandboxError(
            f"srt 不在 {cli_p}。跑 scripts/install-srt.sh 装，或设 DK_SRT_CLI 指过去")

    node = (getattr(cfg, "srt_node", "") or "").strip()
    node_p = Path(node).expanduser() if node else Path("~/.local/bin/node").expanduser()
    if not node_p.is_file():
        raise OuterSandboxError(f"node 不在 {node_p}（设 DK_SRT_NODE）")

    return str(node_p), str(cli_p)


def _canon(raw) -> Path:
    """归一化到可比较形式：只展开 `~`，**不做 resolve**（理由见 _uncovered）。

    唯一的例外是 macOS 那两个系统级别名：/var → /private/var、/tmp → /private/tmp。
    它们是同一个对象的两种写法，不归一化会把 `.`=work_dir 这类 tmp 路径误判成没盖到。"""
    p = Path(raw).expanduser()
    s = str(p)
    for alias in ("/var/", "/tmp/"):
        if s.startswith(alias):
            return Path("/private" + s)
    if s in ("/var", "/tmp"):
        return Path("/private" + s)
    return p


def _allow_read_roots(srt_settings: str, cwd) -> list:
    p = Path(srt_settings).expanduser()
    if not p.is_file():
        raise OuterSandboxError(f"srt 配置不在：{p}（设 DK_SRT_SETTINGS）")
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        raise OuterSandboxError(f"srt 配置不是合法 JSON：{p}（{e}）")

    fs = data.get("filesystem") or {}
    entries = fs.get("allowRead") or []
    if not entries:
        raise OuterSandboxError(f"srt 配置里 filesystem.allowRead 是空的：{p}")

    # "." 是相对沙箱进程的 cwd —— runner 用 cwd=work_dir 起 claude
    return [_canon(cwd if e == "." else e) for e in entries]


def _uncovered(roots: list, needed: dict) -> list:
    """返回 allowRead 没盖到的项，形如 ["审批 MCP server → /path/x"]。

    ⚠ 比的是**字面路径**，不做 resolve。实测过软链的两种方向：

      allowRead 只有 ~/.local/share/claude（真身），调 ~/.local/bin/claude（软链）
        → Operation not permitted
      allowRead 只有 ~/.local/bin（软链那头），调 ~/.local/bin/claude
        → 正常跑

    结论：沙箱认你**实际用的那条路径**，不认 resolve 后的真身。所以这里也必须按字面比 ——
    要是先 resolve 再比，上面第一种情况会被判成"盖到了"，然后运行时才炸。"""
    def covered(p) -> bool:
        return any(p == r or r in p.parents for r in roots)

    missing = []
    for label, raw in needed.items():
        if not raw:
            continue
        if not covered(_canon(raw)):
            missing.append(f"{label} → {Path(raw).expanduser()}")
    return missing


def outer_wrap_prefix(cfg, work_dir, needed_reads: dict) -> list:
    """拼出 argv 前缀：[node, cli.js, -s, <srt配置>, --]。没开外层包裹返回 []。

    `--` 不能省：srt 自己也有 `-s, --settings`，它的 commander 不认命令边界，
    `srt -s a.json claude --settings b.json` 会把 b.json 当成 srt 的配置，
    报 `network: Required / filesystem: Required` 然后拒绝启动（实测）。

    needed_reads：这次跑必须读得到的东西（claude 二进制、bot 配置目录、审批用的
    mcp_server.py 与 python 等）。allowRead 盖不到就在这儿炸 —— 否则现象会是
    claude 起来了但莫名其妙报 command not found / 审批装不上，很难查。"""
    if not getattr(cfg, "outer_sandbox", False):
        return []

    node, cli = _resolve_srt(cfg)

    srt_settings = (getattr(cfg, "srt_settings", "") or "").strip()
    if not srt_settings:
        raise OuterSandboxError("开了外层包裹但没给 DK_SRT_SETTINGS（每个 bot 一份，见 SANDBOX.md）")

    roots = _allow_read_roots(srt_settings, work_dir)
    missing = _uncovered(roots, needed_reads)
    if missing:
        raise OuterSandboxError(
            "srt 配置的 allowRead 盖不到这些必须读的路径：\n  " + "\n  ".join(missing)
            + f"\n补进 {srt_settings} 的 filesystem.allowRead 再跑")

    return [node, cli, "-s", str(Path(srt_settings).expanduser()), "--"]
