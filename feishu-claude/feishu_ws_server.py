"""
Feishu × Claude —— WebSocket 长连接版（无需 ngrok / 公网回调）
================================================================

用飞书官方 lark-oapi 的长连接接收事件：服务主动连飞书，事件经 WS 推下来，
彻底干掉 ngrok（URL 漂移、要回后台重填、Flask dev server 等痛点一起没了）。

和 feishu_app_server.py 的关系：
  - 业务逻辑（run_claude / 单飞限并发 / 按 chat_id 会话复用 / event_id 去重 /
    fail-closed 白名单 / @机器人严格比对）全部复用 feishu_app_server.py，不重写一遍。
  - 这里只替换"收事件 + 回消息"的传输层：Flask+ngrok  →  lark.ws.Client。
  - webhook 版保留作 fallback，两者别同时跑同一个应用。

启动：
  python feishu_ws_server.py

前置（飞书开放平台后台，一次性）：
  事件订阅 → 订阅方式从"将事件发送至开发者服务器(URL)" 改为 "使用长连接接收事件"。
  仍需开启 im.message.receive_v1 事件 + 对应权限。
"""

import json
import time

import lark_oapi as lark
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

# 复用 webhook 版里的全部业务逻辑与配置（导入不会启动 Flask，app.run 在 __main__ 守卫里）
import feishu_app_server as core

log = core.log

# 用于回消息的 REST 客户端（长连接只管收，回消息走普通 OpenAPI）
_client = lark.Client.builder().app_id(core.APP_ID).app_secret(core.APP_SECRET).build()


def reply(message_id: str, text: str) -> None:
    """以"引用回复"形式回到原消息下"""
    req = (
        ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(
            ReplyMessageRequestBody.builder()
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        .build()
    )
    resp = _client.im.v1.message.reply(req)
    if not resp.success():
        log.error("reply 失败 code=%s msg=%s", resp.code, resp.msg)


def handle(message_id: str, sender: str, chat_id: str, text: str) -> None:
    """与 webhook 版同构：fail-closed 白名单 → 单飞 → 跑 claude(会话复用) → 分段回复"""
    if not core.ALLOWED_USERS:
        log.warning("白名单未配置，已拒绝 %s。把该 open_id 加入 .env 的 ALLOWED_USERS", sender)
        reply(message_id, "本机器人尚未配置白名单（ALLOWED_USERS），出于安全已拒绝所有请求。")
        return
    if sender not in core.ALLOWED_USERS:
        log.warning("拒绝 %s（不在白名单）", sender)
        reply(message_id, f"抱歉 {sender}，你不在白名单里。")
        return

    if not core._claude_slots.acquire(blocking=False):
        reply(message_id, "⏳ 正在处理上一条，等它完成再发我哦。")
        return

    try:
        log.info("处理 from=%s chat=%s text=%r", sender, chat_id, text[:80])
        reply(message_id, "思考中...")

        with core._sessions_lock:
            resume = core._sessions.get(chat_id, "")
        result = core.run_claude(text, sender, resume_session=resume)
        if result.get("session_id"):
            with core._sessions_lock:
                core._sessions[chat_id] = result["session_id"]

        answer = result["text"]
        MAX = 4000
        if len(answer) <= MAX:
            reply(message_id, answer)
        else:
            chunks = [answer[i:i + MAX] for i in range(0, len(answer), MAX)]
            for i, c in enumerate(chunks, 1):
                reply(message_id, f"[{i}/{len(chunks)}] {c}")
                time.sleep(0.5)
        log.info("回复完成 from=%s len=%d", sender, len(answer))
    except Exception as e:
        log.exception("处理消息出错")
        try:
            reply(message_id, f"出错了：{e}")
        except Exception:
            pass
    finally:
        core._claude_slots.release()


def on_message(data) -> None:
    """lark.ws 收到 im.message.receive_v1 的回调（跑在 SDK 线程里）"""
    try:
        # 幂等去重（长连接也可能瞬时重投）
        event_id = getattr(data.header, "event_id", "") if data.header else ""
        if core.already_handled(event_id):
            log.info("重复事件 event_id=%s，已忽略", event_id)
            return

        msg = data.event.message
        sender = data.event.sender
        message_id = msg.message_id
        chat_id = msg.chat_id or ""
        sender_open_id = (
            sender.sender_id.open_id if sender and sender.sender_id else "anon"
        )

        # 群里：只在严格 @ 本机器人 时响应（私聊直接处理）
        if msg.chat_type == "group":
            mentions = msg.mentions or []
            bot_id = core.get_bot_open_id()
            if bot_id:
                if not any(m.id and m.id.open_id == bot_id for m in mentions):
                    return
            elif not mentions:
                return

        if msg.message_type != "text":
            reply(message_id, "暂时只支持文本消息")
            return

        try:
            text = json.loads(msg.content or "{}").get("text", "").strip()
        except json.JSONDecodeError:
            text = ""
        # 去掉 @ 占位符
        for m in (msg.mentions or []):
            if m.key:
                text = text.replace(m.key, "").strip()
        if not text:
            return

        handle(message_id, sender_open_id, chat_id, text)
    except Exception:
        log.exception("WS 处理事件出错")


def main() -> None:
    handler = (
        EventDispatcherHandler.builder(core.ENCRYPT_KEY, core.VERIFY_TOKEN)
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )
    ws_client = lark.ws.Client(
        core.APP_ID,
        core.APP_SECRET,
        event_handler=handler,
        log_level=lark.LogLevel.INFO,
        auto_reconnect=True,  # 断网自动重连
    )

    log.info("=" * 60)
    log.info("Feishu WS 长连接启动（无需 ngrok / 公网回调）")
    log.info("  工具: %s", core.ALLOWED_TOOLS)
    log.info("  并发上限: %d", core.MAX_CONCURRENCY)
    log.info("  白名单: %s", core.ALLOWED_USERS or "（未配置 → 已 fail-closed，拒绝所有请求）")
    log.info("=" * 60)
    if not core.ALLOWED_USERS:
        log.warning("⚠ ALLOWED_USERS 为空：当前会拒绝所有人。先发一条消息从日志拿 open_id 填进 .env 再重启。")
    log.info("提醒：飞书后台「事件订阅」需切到「使用长连接接收事件」，否则收不到消息。")

    ws_client.start()  # 阻塞运行，内部自动重连/鉴权


if __name__ == "__main__":
    main()
