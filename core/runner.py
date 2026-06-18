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


def run_claude(cfg, full_prompt: str, work_dir, resume_session: str = "") -> dict:
    """跑一次 claude，返回 {ok, text, session_id}。resume_session 非空则续上一轮会话。
    若续接的会话已失效（claude 报 session not found），原消息立刻开新会话重试一次——
    用户当轮就拿到答案、不静默失忆；带 reset_notice 让 hub 告知"已开新会话"。"""
    fn = _run_sdk if cfg.engine == "sdk" else _run_cli
    result = fn(cfg, full_prompt, work_dir, resume_session)
    if resume_session and result.get("session_gone"):
        log.info("会话 %s… 已失效，开新会话重试本条", resume_session[:8])
        result = fn(cfg, full_prompt, work_dir, "")
        result["reset_notice"] = True
    return result


def _effective_tools(cfg) -> str:
    """沙箱已验证 → 用配置工具；未验证 → 强制只读，剥掉 Bash/Write/Edit。GUARD-3 真正的闸。
    （--allowedTools 一旦含危险工具就已放行，光改 permission-mode 拦不住，必须从工具清单剥。）"""
    if sandbox.verified(cfg.claude_settings):
        return cfg.allowed_tools
    dangerous = {"Bash", "Write", "Edit"}
    safe = [t.strip() for t in cfg.allowed_tools.split(",")
            if t.strip() and t.strip() not in dangerous]
    return ",".join(safe)


def _permission_mode(cfg) -> str:
    """沙箱已验证 → acceptEdits；未验证 → default。与 _effective_tools 一道做防御纵深。GUARD-3。"""
    return "acceptEdits" if sandbox.verified(cfg.claude_settings) else "default"


def _run_cli(cfg, full_prompt: str, work_dir, resume_session: str) -> dict:
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
    if cfg.claude_settings:
        cmd += ["--settings", cfg.claude_settings]   # 套用 sandbox 隔离（见 SANDBOX.md）

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


def _run_sdk(cfg, full_prompt: str, work_dir, resume_session: str) -> dict:
    """进程内 claude-agent-sdk。同步包装 async query()，便于在现有线程模型里调用。"""
    import asyncio
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage
    except ImportError:
        log.error("未安装 claude-agent-sdk（pip install claude-agent-sdk）")
        return {"ok": False, "text": "服务还没准备好，稍后再试。", "session_id": ""}

    async def _go():
        opts = ClaudeAgentOptions(
            allowed_tools=[t.strip() for t in _effective_tools(cfg).split(",") if t.strip()],
            permission_mode=_permission_mode(cfg),
            cwd=str(work_dir),
            resume=resume_session or None,
            settings=cfg.claude_settings or None,
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
