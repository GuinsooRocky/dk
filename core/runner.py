"""Claude 执行引擎（跨渠道唯一一份 run_claude）+ 单飞闸 + 会话状态。

两个可切换引擎（CLAUDE_ENGINE）：
  - cli（默认）：subprocess 调 `claude -p`，已验证、最稳。
  - sdk：进程内 claude-agent-sdk query()，支持 can_use_tool 等；需 pip install claude-agent-sdk。
两者都吃同一个 Config，返回同一个结构 {ok, text, session_id}。
"""
import json
import threading
import subprocess


# ---- 单飞闸：默认 1，满了非阻塞返回 False（调用方回"稍等"）----
class Slots:
    def __init__(self, n: int):
        self._sem = threading.Semaphore(max(1, n))

    def acquire(self) -> bool:
        return self._sem.acquire(blocking=False)

    def release(self) -> None:
        self._sem.release()


# ---- 会话复用：按 key 存上一轮 session_id，实现多轮记忆 ----
class Sessions:
    def __init__(self):
        self._d: dict = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str:
        with self._lock:
            return self._d.get(key, "")

    def update(self, key: str, result: dict, was_resume: bool) -> None:
        """成功拿到 session_id 就存；仅在"真失败(not ok)且本轮在续接"时清掉失效会话。
        rc=0 但解析失败(ok=True 无 session_id)不算失败，保留旧会话避免误删多轮记忆。"""
        with self._lock:
            if result.get("session_id"):
                self._d[key] = result["session_id"]
            elif was_resume and not result.get("ok"):
                self._d.pop(key, None)


def safe_user(user: str) -> str:
    return "".join(c for c in user if c.isalnum() or c in "-_")[:32] or "anon"


def run_claude(cfg, full_prompt: str, work_dir, resume_session: str = "") -> dict:
    """跑一次 claude，返回 {ok, text, session_id}。resume_session 非空则续上一轮会话。"""
    if cfg.engine == "sdk":
        return _run_sdk(cfg, full_prompt, work_dir, resume_session)
    return _run_cli(cfg, full_prompt, work_dir, resume_session)


def _run_cli(cfg, full_prompt: str, work_dir, resume_session: str) -> dict:
    cmd = [cfg.claude_cmd, "-p", full_prompt]
    if resume_session:
        cmd += ["--resume", resume_session]
    cmd += [
        "--allowedTools", cfg.allowed_tools,
        "--output-format", "json",
        "--permission-mode", "acceptEdits",
    ]
    if cfg.claude_settings:
        cmd += ["--settings", cfg.claude_settings]   # 套用 sandbox 隔离（见 SANDBOX.md）

    try:
        proc = subprocess.run(
            cmd, cwd=str(work_dir),
            capture_output=True, text=True, timeout=cfg.timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "text": f"任务超过 {cfg.timeout} 秒，已中断。", "session_id": ""}
    except FileNotFoundError:
        return {"ok": False, "text": f"找不到 claude 命令（CLAUDE_CMD={cfg.claude_cmd}）", "session_id": ""}

    if proc.returncode != 0:
        return {"ok": False, "text": f"Claude 出错：\n{proc.stderr[:1500]}", "session_id": ""}

    # rc==0 即成功；即便 stdout 偶发非 JSON 也不当失败、不误删会话
    try:
        data = json.loads(proc.stdout)
        text = (data.get("result") or data.get("text") or proc.stdout).strip()
        return {"ok": True, "text": text or "(Claude 没返回内容)", "session_id": data.get("session_id", "")}
    except json.JSONDecodeError:
        return {"ok": True, "text": proc.stdout.strip() or "(Claude 没返回内容)", "session_id": ""}


def _run_sdk(cfg, full_prompt: str, work_dir, resume_session: str) -> dict:
    """进程内 claude-agent-sdk。同步包装 async query()，便于在现有线程模型里调用。"""
    import asyncio
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage
    except ImportError:
        return {"ok": False, "text": "未安装 claude-agent-sdk（pip install claude-agent-sdk）", "session_id": ""}

    async def _go():
        opts = ClaudeAgentOptions(
            allowed_tools=[t.strip() for t in cfg.allowed_tools.split(",") if t.strip()],
            permission_mode="acceptEdits",
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
        return {"ok": not is_err, "text": text or "(Claude 没返回内容)", "session_id": sid}

    try:
        return asyncio.run(_go())
    except Exception as e:
        return {"ok": False, "text": f"Claude SDK 出错：{e}", "session_id": ""}
