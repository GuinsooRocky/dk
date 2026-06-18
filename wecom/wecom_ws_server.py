"""企业微信（WeCom）× Claude —— 智能机器人长连接版（无需 ngrok）⭐。

用企业微信智能机器人的 WebSocket 长连接接消息（bot_id + secret 直连），
干掉公网回调/内网穿透。镜像 feishu_ws_server.py：只管 WS 传输层（收消息 + reply），
业务逻辑（单飞 / 会话复用 / 去重 / 分段）全调 core。

启动：python wecom_ws_server.py
前置：企业微信管理后台「应用管理 → 机器人 → 智能机器人」创建机器人，拿 bot_id + secret，
      并把机器人拉进一个群。

SDK：pip install wecom-aibot-sdk-python（仓库 chengyongru/wecom_aibot_sdk）。
"""
import os
import sys
import time
import json
import asyncio
import logging
from pathlib import Path

# ---- 引入跨渠道 core（core/ 在仓库根目录，与 feishu-claude 同款引法）----
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config, security, dedup, chunking, hub_client  # noqa: E402

from wecom_aibot_sdk import WSClient, WSClientOptions  # noqa: E402

# ---- 加载 .env + 配置 ----
config.load_env(Path(__file__).parent / ".env")
CFG = config.load(str(Path.home() / "claude-wecom-workdir"))

BOT_ID = os.getenv("WECOM_BOT_ID", "").strip()
BOT_SECRET = os.getenv("WECOM_BOT_SECRET", "").strip()

MAX_WECOM_MSG = 2000   # 企业微信单条文本上限附近，超过分段

CFG.work_dir.mkdir(parents=True, exist_ok=True)
LOG_DIR = CFG.work_dir / ".logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "wecom_ws.log"), logging.StreamHandler()],
)
log = logging.getLogger("wecom")

if not BOT_ID or not BOT_SECRET:
    log.error("缺少 WECOM_BOT_ID 或 WECOM_BOT_SECRET，请检查 .env")
    sys.exit(1)

# ---- 渠道侧只留去重（单飞/会话已上移到 Hub）----
DEDUP = dedup.Dedup()

# 联调用：首条消息把原始 frame.body 打全，肉眼锁定真实字段名（SDK 文档未给完整结构）
_raw_dumped = False


def _extract(frame) -> dict:
    """从 frame 抽出 {msgid, sender, chat_id, chattype, text}。

    企业微信智能机器人标准回调结构（以官方文档为准，联调按首条日志校正）：
      {msgid, aibotid, chatid, chattype:"single"|"group", from:{userid}, msgtype, text:{content}}
    字段做多路兜底，拿不到不崩。
    """
    global _raw_dumped
    body = getattr(frame, "body", None) or {}
    if not _raw_dumped:
        log.info("⭐首条消息原始 frame.body（用于锁定字段名）：%s",
                 json.dumps(body, ensure_ascii=False, default=str))
        _raw_dumped = True

    def dig(*paths, default=""):
        for p in paths:
            cur = body
            ok = True
            for k in p:
                if isinstance(cur, dict) and k in cur:
                    cur = cur[k]
                else:
                    ok = False
                    break
            if ok and cur not in (None, ""):
                return cur
        return default

    # 字段名据 wecom_aibot_sdk types/message.py 确认：from_userid / chattype / chatid / msgid
    sender = dig(("from_userid",), default="anon")
    chatid = dig(("chatid",), default="")
    return {
        "msgid": dig(("msgid",), default=""),
        "sender": sender,
        # 会话 key：群用 chatid；单聊 chatid 可能为空 → 退回 from_userid
        "chat_id": chatid or sender,
        "chattype": dig(("chattype",), default="single"),
        "text": dig(("text", "content"), default="").strip(),
    }


def _process(reply, sender: str, chat_id: str, text: str) -> None:
    """薄壳编排：白名单 → 思考中 → 转发给 Hub → 分段回复。
    不自己跑 claude（做菜在 Hub）；在线程池里跑（同步 HTTP），reply 回调把协程调度回事件循环。"""
    if not security.is_allowed(sender, CFG.allowed_users):
        return
    log.info("转发 from=%s chat=%s text=%r", sender, chat_id, text[:80])
    reply("思考中…")
    try:
        resp = hub_client.ask_hub_sync("wecom", chat_id, sender, text)
    except Exception as e:
        log.exception("调 Hub 失败")
        try:
            reply("服务没连上，稍后再试。")
        except Exception:
            pass
        return
    answer = resp.get("text") or "（没收到回复）"
    chunks = chunking.split_chunks(answer, MAX_WECOM_MSG)
    for i, c in enumerate(chunks, 1):
        reply(c if len(chunks) == 1 else f"[{i}/{len(chunks)}] {c}")
        if len(chunks) > 1:
            time.sleep(0.5)
    log.info("回复完成 from=%s len=%d", sender, len(answer))


async def _make_handler(client):
    loop = asyncio.get_running_loop()

    async def on_text(frame):
        try:
            info = _extract(frame)
            # 去重：同 msgid 只处理一次（企业微信偶发重投）
            if DEDUP.seen(info["msgid"]):
                log.info("重复消息 msgid=%s，已忽略", info["msgid"])
                return
            # fail-closed 白名单：未授权静默丢弃（_process 内也兜底防御）
            if not security.is_allowed(info["sender"], CFG.allowed_users):
                log.warning("拒绝非白名单 from=%s", info["sender"])
                hub_client.report_pending("wecom", info["sender"])   # 实时抓 ID
                return
            if not info["text"]:
                return

            # reply：从线程池工作线程把 client.reply 协程调度回事件循环并等结果
            def reply(text: str) -> None:
                fut = asyncio.run_coroutine_threadsafe(
                    client.reply(frame, {"msgtype": "text", "text": {"content": text}}),
                    loop,
                )
                try:
                    fut.result(timeout=30)
                except Exception:
                    log.exception("reply 失败")

            # _process 里同步 HTTP 调 Hub 是阻塞的，丢线程池，别卡住 WS 心跳
            await loop.run_in_executor(
                None, _process, reply, info["sender"], info["chat_id"], info["text"]
            )
        except Exception:
            log.exception("on_text 处理出错")

    return on_text


async def amain() -> None:
    client = WSClient(WSClientOptions(bot_id=BOT_ID, secret=BOT_SECRET))
    client.on("message.text", await _make_handler(client))

    log.info("=" * 60)
    log.info("WeCom 智能机器人长连接启动（无需 ngrok）  引擎=%s", CFG.engine)
    log.info("  工具=%s  并发上限=%d", CFG.allowed_tools, CFG.max_concurrency)
    log.info("  白名单=%s", list(CFG.allowed_users) or "（未配置→fail-closed 拒绝所有）")
    log.info("=" * 60)
    if not CFG.allowed_users:
        log.warning("⚠ ALLOWED_USERS 为空：当前拒绝所有人。先 @ 机器人发一条，从日志拿 userid 填进 .env 再重启。")

    await client.connect_async()
    last_beat = 0.0
    while getattr(client, "is_connected", True):
        # 只在"认证通过"(is_authenticated：服务器确认 bot_id/secret 有效)时上报心跳。
        # 假凭证 → WS 能握上手(is_connected=真)但认证过不了(is_authenticated=假) → 不拍
        # → hub 显示"连接中"而非假"在线"。纯本地回环、不碰 claude。
        if getattr(client, "is_authenticated", False) and time.monotonic() - last_beat >= 120:
            hub_client.report_heartbeat("wecom")
            last_beat = time.monotonic()
        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass
