"""Feishu × Claude —— WebSocket 长连接版（方案 C，无需 ngrok）⭐推荐。

用飞书官方 lark-oapi 长连接接事件，服务主动连飞书，干掉 ngrok/公网回调/Flask。
只负责 WS 传输层（收事件 + lark reply）；业务逻辑全在 feishu_common + core。

启动：python feishu_ws_server.py
前置：飞书后台「事件订阅」订阅方式改为「使用长连接接收事件」。
"""
import os
import json
import logging

import lark_oapi as lark
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.api.im.v1 import (
    CreateMessageRequest, CreateMessageRequestBody,
    UpdateMessageRequest, UpdateMessageRequestBody,
)

import feishu_common as fc

log = logging.getLogger("feishu")

# 群聊是否要求 @ 机器人才回。个人私人群（就你+机器人）设 false → 发啥都回，不用 @。
GROUP_REQUIRE_MENTION = os.getenv("GROUP_REQUIRE_MENTION", "false").strip().lower() in ("1", "true", "yes")

_client = lark.Client.builder().app_id(fc.APP_ID).app_secret(fc.APP_SECRET).build()


def _send(chat_id: str, text: str) -> str:
    """发消息到群（主聊天里显示，非线程回复），返回 message_id 供后续原地编辑。"""
    req = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        .build()
    )
    resp = _client.im.v1.message.create(req)
    if not resp.success():
        log.error("create 失败 code=%s msg=%s", resp.code, resp.msg)
        return ""
    return resp.data.message_id if resp.data else ""


def _update(message_id: str, text: str) -> None:
    """原地编辑机器人自己发的文本消息（"思考中"→答案，不留废消息）。"""
    req = (
        UpdateMessageRequest.builder()
        .message_id(message_id)
        .request_body(
            UpdateMessageRequestBody.builder()
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        .build()
    )
    resp = _client.im.v1.message.update(req)
    if not resp.success():
        log.error("update 失败 code=%s msg=%s", resp.code, resp.msg)


def on_message(data) -> None:
    """im.message.receive_v1 回调（跑在 lark SDK 线程里）。"""
    try:
        # 先守卫可能为 None 的字段（畸形事件不应在 dedup 记账后被吞掉而无法重投）
        ev = data.event
        msg = ev.message if ev else None
        sender = ev.sender if ev else None
        if msg is None:
            log.warning("WS 事件缺 message，忽略")
            return
        message_id = msg.message_id

        event_id = getattr(data.header, "event_id", "") if data.header else ""
        if fc.DEDUP.seen(event_id):
            log.info("重复事件 event_id=%s，已忽略", event_id)
            return

        chat_id = msg.chat_id or ""
        sender_open_id = sender.sender_id.open_id if sender and sender.sender_id else "anon"

        # 群里默认不要求 @（GROUP_REQUIRE_MENTION=false）；要求时才校验是否 @ 了本机器人
        if msg.chat_type == "group" and GROUP_REQUIRE_MENTION:
            mentions = [
                {"id": {"open_id": (m.id.open_id if m.id else None)}, "key": m.key}
                for m in (msg.mentions or [])
            ]
            if not fc.mentioned_bot(mentions):
                return

        # fail-closed 白名单：在任何回复/处理之前（含非文本），未授权静默丢弃
        if not fc.is_allowed(sender_open_id):
            log.warning("拒绝非白名单 from=%s", sender_open_id)
            fc.hub_client.report_pending("feishu", sender_open_id)   # 实时抓 ID：让 app 显示"想加入"
            return

        if msg.message_type != "text":
            _send(chat_id, "暂时只支持文本消息")   # 原 _reply 未定义，会抛 NameError
            return

        try:
            text = json.loads(msg.content or "{}").get("text", "").strip()
        except json.JSONDecodeError:
            text = ""
        for m in (msg.mentions or []):
            if m.key:
                text = text.replace(m.key, "").strip()
        if not text:
            return

        # 首条"思考中"占位 → 下一条原地编辑成答案（跟 Telegram 一致，不留废消息）
        state = {"mid": None, "first": True}

        def reply(t: str) -> None:
            if state["first"]:
                state["first"] = False
                state["mid"] = _send(chat_id, t)
            elif state["mid"]:
                _update(state["mid"], t)
                state["mid"] = None
            else:
                _send(chat_id, t)

        fc.process(reply, sender_open_id, chat_id, text)
    except Exception:
        log.exception("WS 处理事件出错")


def main() -> None:
    handler = (
        EventDispatcherHandler.builder(fc.ENCRYPT_KEY, fc.VERIFY_TOKEN)
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )
    ws_client = lark.ws.Client(
        fc.APP_ID, fc.APP_SECRET,
        event_handler=handler, log_level=lark.LogLevel.INFO, auto_reconnect=True,
    )
    log.info("=" * 60)
    log.info("Feishu WS 长连接启动（无需 ngrok）  引擎=%s", fc.CFG.engine)
    log.info("  工具=%s  并发上限=%d", fc.CFG.allowed_tools, fc.CFG.max_concurrency)
    log.info("  白名单=%s", list(fc.CFG.allowed_users) or "（未配置→fail-closed 拒绝所有）")
    log.info("=" * 60)
    if not fc.CFG.allowed_users:
        log.warning("⚠ ALLOWED_USERS 为空：当前拒绝所有人。先发一条消息从日志拿 open_id 填进 .env 再重启。")
    log.info("提醒：飞书后台「事件订阅」需切到「使用长连接接收事件」，否则收不到消息。")
    ws_client.start()   # 阻塞运行，内部自动重连/鉴权


if __name__ == "__main__":
    main()
