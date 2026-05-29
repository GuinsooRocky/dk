"""Claude Bridge —— 把微信消息桥接到 Claude（请求/响应式，分段在 Node 端做）。

只负责 HTTP 接口；业务逻辑（白名单/单飞/会话/跑 claude）复用 core。
运行：python claude_bridge.py  （端口默认 5858，仅绑 127.0.0.1）
"""
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config, runner, security  # noqa: E402

config.load_env(Path(__file__).parent / ".env")
CFG = config.load(str(Path.home() / "claude-wechat-workdir"))
PORT = int(os.getenv("BRIDGE_PORT", "5858"))

CFG.work_dir.mkdir(parents=True, exist_ok=True)
LOG_DIR = CFG.work_dir / ".logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "bridge.log"), logging.StreamHandler()],
)
log = logging.getLogger("bridge")

SLOTS = runner.Slots(CFG.max_concurrency)
SESSIONS = runner.Sessions()
app = Flask(__name__)


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(force=True, silent=True) or {}
    user = payload.get("user", "unknown")
    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "text": "空消息"}), 400

    # fail-closed 白名单
    if not security.is_allowed(user, CFG.allowed_users):
        log.warning("拒绝 from=%s（白名单%s）", user, "未配置" if not CFG.allowed_users else "不含此人")
        reason = "本机器人尚未配置白名单（ALLOWED_USERS），出于安全已拒绝。" if not CFG.allowed_users else "你不在白名单里"
        return jsonify({"ok": False, "text": reason}), 403

    # 单飞：忙时让用户稍后重发
    if not SLOTS.acquire():
        return jsonify({"ok": True, "text": "⏳ 正在处理上一条，等它完成再发我哦。"})
    try:
        log.info("收到消息 from=%s len=%d: %s", user, len(message), message[:80])
        work_dir = CFG.work_dir / runner.safe_user(user)
        work_dir.mkdir(exist_ok=True)
        resume = SESSIONS.get(user)
        prompt = config.build_prompt("微信", user, work_dir, message)
        result = runner.run_claude(CFG, prompt, work_dir, resume_session=resume)
        SESSIONS.update(user, result, was_resume=bool(resume))
        log.info("回复 to=%s len=%d", user, len(result["text"]))
        return jsonify({"ok": result["ok"], "text": result["text"]})
    finally:
        SLOTS.release()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "time": datetime.now().isoformat(),
        "work_dir": str(CFG.work_dir),
        "tools": CFG.allowed_tools,
        "whitelist": list(CFG.allowed_users) or "all",
        "engine": CFG.engine,
    })


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("Claude Bridge 启动  端口=%d  引擎=%s", PORT, CFG.engine)
    log.info("  工具=%s  并发上限=%d", CFG.allowed_tools, CFG.max_concurrency)
    log.info("  白名单=%s", list(CFG.allowed_users) or "（未配置→fail-closed 拒绝所有）")
    log.info("=" * 60)
    if not CFG.allowed_users:
        log.warning("⚠ ALLOWED_USERS 为空：当前拒绝所有人。发一条消息从日志拿昵称填进 .env 再重启。")
    app.run(host="127.0.0.1", port=PORT, debug=False)
