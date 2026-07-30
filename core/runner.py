"""Claude 执行引擎（跨渠道唯一一份 run_claude）+ 单飞闸 + 会话状态。

两个可切换引擎（CLAUDE_ENGINE）：
  - cli（默认）：subprocess 调 `claude -p`，已验证、最稳。
  - sdk：进程内 claude-agent-sdk query()，支持 can_use_tool 等；需 pip install claude-agent-sdk。
两者都吃同一个 Config，返回同一个结构 {ok, text, session_id}。
"""
import json
import logging
import threading
import subprocess
from pathlib import Path

from core import sandbox

log = logging.getLogger("runner")


# ---- 单飞闸：默认 1，满了非阻塞返回 False（调用方回"稍等"）----
class Slots:
    def __init__(self, n: int):
        self._sem = threading.Semaphore(max(1, n))

    def acquire(self) -> bool:
        return self._sem.acquire(blocking=False)

    def release(self) -> None:
        self._sem.release()


# 会话复用搬到 core/threads.py（SQLite 落盘，重启不失忆）；这里只留 claude 执行。


def safe_user(user: str) -> str:
    return "".join(c for c in user if c.isalnum() or c in "-_")[:32] or "anon"


def run_claude(cfg, full_prompt: str, work_dir, resume_session: str = "", run_id: str = "") -> dict:
    """跑一次 claude，返回 {ok, text, session_id}。resume_session 非空则续上一轮会话。
    若续接的会话已失效（claude 报 session not found），原消息立刻开新会话重试一次——
    用户当轮就拿到答案、不静默失忆；带 reset_notice 让 hub 告知"已开新会话"。

    run_id：Hub 在入口冻结的请求者上下文 id，透传给审批 MCP server（见 _mcp_config_for_run）。
    留空 = 这次跑不接审批（例如探针、后台任务）。"""
    fn = _run_sdk if cfg.engine == "sdk" else _run_cli
    result = fn(cfg, full_prompt, work_dir, resume_session, run_id)
    if resume_session and result.get("session_gone"):
        log.info("会话 %s… 已失效，开新会话重试本条", resume_session[:8])
        result = fn(cfg, full_prompt, work_dir, "", run_id)
        result["reset_notice"] = True
    _maybe_notify(result)   # 路径 B 回调（N-M6，**默认关**）
    return result


def _maybe_notify(result: dict) -> None:
    """路径 B（提案 §6 M6 决策③）：bot 自起的跑跑完回调 hub /notify。**默认关**。

    置 DK_RUNNER_NOTIFY=1 才开。默认关是为了和 SessionEnd hook 注册表互斥——hook 管交互式
    跑、runner 回调管 bot 自起跑（§5 P0 第4点：同 session 只能一条路径负责，否则双触发）。
    fire-and-forget + stdlib + 直连不走代理，绝不影响主流程；core 不依赖 hub，自带 POST。
    """
    import os
    if os.getenv("DK_RUNNER_NOTIFY", "") not in ("1", "true", "True"):
        return   # 默认关
    def _post():
        try:
            import json as _json
            import urllib.request as _u
            from pathlib import Path as _P
            try:
                token = (_P.home() / ".chat-cc-bot" / ".notify_token").read_text(encoding="utf-8").strip()
            except OSError:
                token = ""
            hub = os.getenv("HUB_URL", "http://127.0.0.1:8787").rstrip("/")
            payload = {
                "session_id": result.get("session_id") or "runner",
                "status": "ok" if result.get("ok") else "error",
                "summary": (result.get("text") or "")[:500],
            }
            req = _u.Request(f"{hub}/notify", data=_json.dumps(payload).encode("utf-8"),
                             method="POST",
                             headers={"Content-Type": "application/json", "X-Notify-Token": token})
            _u.build_opener(_u.ProxyHandler({})).open(req, timeout=5).read()
        except Exception:
            pass
    threading.Thread(target=_post, daemon=True).start()


# 能执行命令或改文件的工具全集。**必须按"能力"而不是按"名字"想**：
# 2026-07-30 实测 `--disallowedTools Bash` 之后，claude 改用 Monitor 工具跑同一条命令
# （原话：「this session has no Bash tool exposed, so I ran it via the Monitor tool,
#  which executes commands in the same shell environment」）。所以只 deny Bash 是漏的。
# Task/Agent 也算——它派的子 agent 自带工具，等于绕一层拿到 Bash。
_DANGEROUS = (
    "Bash", "BashOutput", "KillShell", "Monitor",   # 能跑命令
    "Task", "Agent",                                 # 能派子 agent（子 agent 自带 Bash）
    "Write", "Edit", "MultiEdit", "NotebookEdit",     # 能改文件
)


def _effective_tools(cfg) -> str:
    """给 --allowedTools 的清单。

    ⚠ 2026-07-30 实测纠正：`--allowedTools` **是免提示放行清单，不是能力白名单**。
    从它里面剥掉 Bash，claude 照样能用 Bash（实测 `--allowedTools "Read,Glob,Grep,WebFetch"`
    跑 `echo` 成功、permission_denials 为空）。老 GUARD-3 靠"从清单里剥"来限权是**无效的**，
    真正管用的是 `--disallowedTools`（见 _disallowed_tools）。
    这里只保留"哪些工具免提示"的语义。"""
    return cfg.allowed_tools


def _disallowed_tools(cfg) -> str:
    """危险工具到底给不给 —— **判据是"有没有人在回路里"，不是"沙箱验没验过"**。

    - 开了审批：不摘。它们会去问 permission-prompt-tool，由人按钮放行（沙箱是第二层兜底）。
    - 没开审批：全摘。没人把关时唯一安全的姿态是根本没有这些工具。

    2026-07-30 实测纠正：原来这里按"沙箱验过就不摘"，结果沙箱一配上、审批又没开，
    Bash 就无声可用了（e2e 用例 C 抓到的 fail-open）。**沙箱管的是"跑起来能碰到什么"，
    管不了"该不该跑"** —— 后者只能靠人或靠没有这个工具。

    仍是按名字 deny，claude 升级长出新的执行类工具就会漏，所以 scripts/approval-e2e.sh
    验的是**行为**（一条 shell 命令在没批准时到底跑没跑），不是核对这张名单。"""
    if cfg.approvals:
        return ""
    return ",".join(_DANGEROUS)


def _permission_mode(cfg) -> str:
    """开审批 → 必须 default；否则沙箱已验证 → acceptEdits；未验证 → default。

    ⚠ 开审批时**不能用 acceptEdits**：它会自动接受 Write/Edit，那些工具就不会来问审批了
    （2026-07-30 实测：acceptEdits + autoAllowBashIfSandboxed 组合下，permission-prompt-tool
    压根没被调用，命令直接跑了）。审批要生效，得让每个危险工具都真的走"问一下"这条路。"""
    if cfg.approvals:
        return "default"
    return "acceptEdits" if sandbox.verified(cfg.claude_settings) else "default"


def _mcp_config_for_run(run_id: str) -> str:
    """给这一次跑写一份 mcp-config，把 run_id 钉在 MCP server 的环境变量里。

    为什么按 run 写而不是共用一份：审批要回给**发起这次请求的人**。run_id 只有 Hub 知道
    对应哪个 chat，MCP server 拿不到也伪造不了别人的 endpoint → 串台在结构上不成立
    （PRD §14 冻结通知路由）。返回临时文件路径，调用方负责删。"""
    import os
    import sys
    import tempfile
    # 冻结的 sidecar 里 sys.executable 是那个二进制、不是 python → 允许显式指定。
    py = os.getenv("DK_MCP_PYTHON", "").strip()
    if not py:
        py = sys.executable if "python" in Path(sys.executable).name.lower() else "/usr/bin/python3"
    server = Path(__file__).resolve().parent.parent / "approvals" / "mcp_server.py"
    # 冻结打包时 approvals/mcp_server.py 需要显式 --add-data 进 bundle（build_sidecar.sh 是
    # 逐个模块 stage 的，新目录不会自动进）。缺了就必须**炸在这里**：
    # 悄悄不带审批参数往下跑 = 危险工具无闸可用，比报错严重得多。
    if not server.exists():
        raise FileNotFoundError(f"审批 MCP server 不在：{server}（打包漏了 --add-data？）")
    if not Path(py).exists():
        raise FileNotFoundError(f"跑 MCP server 的 python 不在：{py}（设 DK_MCP_PYTHON）")
    server = str(server)
    cfg_obj = {"mcpServers": {"dkapproval": {
        "command": py,
        "args": [server],
        "env": {
            "DK_RUN_ID": run_id,
            "DK_HUB_URL": os.getenv("HUB_URL", f"http://127.0.0.1:{os.getenv('HUB_PORT', '8787')}"),
            "DK_APPROVAL_BUDGET_SEC": os.getenv("DK_APPROVAL_BUDGET_SEC", "1800"),
            "DK_APPROVAL_DEBUG_LOG": os.getenv("DK_APPROVAL_DEBUG_LOG", ""),
        },
    }}}
    fd, path = tempfile.mkstemp(prefix="dk-mcp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg_obj, f)
    return path


def _run_cli(cfg, full_prompt: str, work_dir, resume_session: str, run_id: str = "") -> dict:
    cmd = [cfg.claude_cmd, "-p", full_prompt]
    if resume_session:
        cmd += ["--resume", resume_session]
    cmd += [
        "--allowedTools", _effective_tools(cfg),
        "--output-format", "json",
        "--permission-mode", _permission_mode(cfg),
        # 只用项目级 settings：堵住 owner 全局 ~/.claude/CLAUDE.md / RTK.md 泄漏进每个远程用户会话
        "--setting-sources", "project",
    ]
    disallowed = _disallowed_tools(cfg)
    if disallowed:
        cmd += ["--disallowedTools", disallowed]
    if cfg.claude_settings:
        cmd += ["--settings", cfg.claude_settings]   # 套用 sandbox 隔离（见 SANDBOX.md）

    # 审批链路：settings 里 permissions.ask 命中的工具会来问这个 MCP 工具（实测契约见
    # approvals/mcp_server.py 头注释）。没开审批时 ask 命中的工具会直接被拒 —— fail-closed，
    # 这是有意的：宁可干不了活，也不能在没人把关时放行危险动作。
    mcp_cfg_path = ""
    if cfg.approvals and run_id:
        try:
            mcp_cfg_path = _mcp_config_for_run(run_id)
        except FileNotFoundError as e:
            # 审批装不起来 → 这条直接不跑。绝不降级成"无闸执行"
            log.error("审批链路起不来：%s", e)
            return {"ok": False, "session_id": "",
                    "text": "审批链路没装好，为安全起见这条没执行。看 hub 日志。"}
        cmd += ["--mcp-config", mcp_cfg_path,
                "--permission-prompt-tool", "mcp__dkapproval__permission_prompt"]

    try:
        try:
            proc = subprocess.run(
                cmd, cwd=str(work_dir),
                capture_output=True, text=True, timeout=cfg.timeout,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "text": f"处理太久超时了（超过 {cfg.timeout} 秒），这条先停了。", "session_id": ""}
        except FileNotFoundError:
            log.error("找不到 claude 命令 CLAUDE_CMD=%s", cfg.claude_cmd)
            return {"ok": False, "text": "服务还没准备好，稍后再试。", "session_id": ""}

        if proc.returncode != 0:
            log.warning("claude 非零退出 rc=%s stderr=%s", proc.returncode, proc.stderr[:1500])
            blob = (proc.stdout or "") + (proc.stderr or "")
            # 区分"续接的会话真没了" vs 一般失败：前者要开新会话重试，后者保留会话下轮重试
            gone = bool(resume_session) and "No conversation found" in blob
            # 连不上 claude API（代理断/网络断）→ 喂给 hub 的"大脑可达"判定
            unreachable = ("Unable to connect to API" in blob or "ConnectionRefused" in blob
                           or "Connection refused" in blob)
            return {"ok": False, "text": "处理出错了，稍后再试。", "session_id": "",
                    "session_gone": gone, "api_unreachable": unreachable}

        # rc==0 即成功；即便 stdout 偶发非 JSON 也不当失败、不误删会话
        try:
            data = json.loads(proc.stdout)
            text = (data.get("result") or data.get("text") or proc.stdout).strip()
            return {"ok": True, "text": text or "（这次没返回内容）", "session_id": data.get("session_id", "")}
        except json.JSONDecodeError:
            return {"ok": True, "text": proc.stdout.strip() or "（这次没返回内容）", "session_id": ""}
    finally:
        if mcp_cfg_path:
            try:
                Path(mcp_cfg_path).unlink()
            except OSError:
                pass


def _run_sdk(cfg, full_prompt: str, work_dir, resume_session: str, run_id: str = "") -> dict:
    """进程内 claude-agent-sdk。同步包装 async query()，便于在现有线程模型里调用。"""
    import asyncio
    # 审批链路目前只在 CLI 路径实现（--permission-prompt-tool）。SDK 路径要走 can_use_tool，
    # 还没接。**这里必须 fail-closed**：要审批却没有审批能力时直接拒跑，绝不静默无闸执行。
    if cfg.approvals and run_id:
        log.error("审批已开但引擎是 sdk（审批只在 cli 路径实现）→ 拒跑，改 CLAUDE_ENGINE=cli")
        return {"ok": False, "session_id": "",
                "text": "配置冲突：审批链路只支持 cli 引擎，当前是 sdk。这条没执行。"}
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage
    except ImportError:
        log.error("未安装 claude-agent-sdk（pip install claude-agent-sdk）")
        return {"ok": False, "text": "服务还没准备好，稍后再试。", "session_id": ""}

    async def _go():
        opts = ClaudeAgentOptions(
            allowed_tools=[t.strip() for t in _effective_tools(cfg).split(",") if t.strip()],
            disallowed_tools=[t for t in _disallowed_tools(cfg).split(",") if t],
            permission_mode=_permission_mode(cfg),
            cwd=str(work_dir),
            resume=resume_session or None,
            settings=cfg.claude_settings or None,
            # 与 CLI 路径对齐：只用项目级 settings，堵住 owner 全局 ~/.claude/CLAUDE.md /
            # RTK.md 泄漏进每个远程用户会话（SDK 默认 None=加载全部源）。
            setting_sources=["project"],
        )
        text, sid, is_err = "", "", False
        async for msg in query(prompt=full_prompt, options=opts):
            if isinstance(msg, ResultMessage):
                text = (msg.result or "").strip()
                sid = msg.session_id or ""
                is_err = bool(msg.is_error)
        return {"ok": not is_err, "text": text or "（这次没返回内容）", "session_id": sid}

    try:
        return asyncio.run(_go())
    except Exception as e:
        log.warning("claude-agent-sdk 出错：%s", e)
        return {"ok": False, "text": "处理出错了，稍后再试。", "session_id": ""}
