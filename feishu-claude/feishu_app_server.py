"""Feishu × Claude —— webhook 双向机器人（方案 B，需 ngrok）。

本文件只负责飞书 webhook 传输层：收 /event、AES 解密、解析事件、回消息（urllib）。
业务逻辑（白名单/单飞/会话/去重/跑 claude）全在 feishu_common + core。
生产更推荐无 ngrok 的 WS 版 feishu_ws_server.py。

启动：python feishu_app_server.py  （另开终端 ngrok http 5858，URL+/event 填飞书事件订阅）
"""
import json
import hmac
import hashlib
import logging
import threading
from base64 import b64decode
from urllib import request as urlreq
from urllib.error import HTTPError

from flask import Flask, request, jsonify

import feishu_common as fc

log = logging.getLogger("feishu")


# ============ AES 解密（飞书加密推送时用）============
def decrypt_payload(encrypted_b64: str) -> dict:
    """AES-256-CBC，key = SHA256(encrypt_key)，IV = 密文前 16 字节。"""
    from Crypto.Cipher import AES
    key = hashlib.sha256(fc.ENCRYPT_KEY.encode("utf-8")).digest()
    cipher_bytes = b64decode(encrypted_b64)
    iv, ct = cipher_bytes[:16], cipher_bytes[16:]
    raw = AES.new(key, AES.MODE_CBC, iv).decrypt(ct)
    plain = raw[:-raw[-1]]   # 去 PKCS7 padding
    return json.loads(plain.decode("utf-8"))


# ============ 回消息（引用回复）============
def reply_message(message_id: str, text: str) -> dict:
    token = fc.get_tenant_token()
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
    payload = {"msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)}
    req = urlreq.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urlreq.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return {"code": -1, "msg": f"HTTP {e.code}: {e.read().decode('utf-8')}"}


# ============ Flask ============
app = Flask(__name__)


@app.route("/event", methods=["POST"])
def event():
    raw = request.get_json(force=True, silent=True) or {}

    if "encrypt" in raw:
        if not fc.ENCRYPT_KEY:
            log.error("收到加密消息但未配置 ENCRYPT_KEY")
            return jsonify({"code": 1, "msg": "no encrypt key"}), 400
        try:
            payload = decrypt_payload(raw["encrypt"])
        except Exception as e:
            log.exception("解密失败")
            return jsonify({"code": 1, "msg": str(e)}), 400
    else:
        payload = raw

    if payload.get("type") == "url_verification":
        log.info("URL 验证 challenge=%s", payload.get("challenge", ""))
        return jsonify({"challenge": payload.get("challenge", "")})

    header = payload.get("header", {})
    if fc.VERIFY_TOKEN:
        if not hmac.compare_digest(header.get("token", ""), fc.VERIFY_TOKEN):
            log.warning("verify token 不匹配，忽略")
            return jsonify({"code": 1, "msg": "bad token"}), 403
    else:
        log.warning("未配置 FEISHU_VERIFY_TOKEN，webhook 缺少鉴权层（建议在 .env 配上）")

    if header.get("event_type") != "im.message.receive_v1":
        return jsonify({"code": 0})

    # 幂等去重：飞书未在 3s 内收到 ack 会重推同一事件
    if fc.DEDUP.seen(header.get("event_id", "")):
        log.info("重复事件 event_id=%s，已忽略", header.get("event_id", ""))
        return jsonify({"code": 0})

    message = payload.get("event", {}).get("message", {})
    sender = payload.get("event", {}).get("sender", {})
    message_id = message.get("message_id", "")
    chat_id = message.get("chat_id", "")
    chat_type = message.get("chat_type", "")
    msg_type = message.get("message_type", "")
    sender_name = sender.get("sender_id", {}).get("open_id", "anon")

    # 群里只在被 @ 本机器人 时响应
    if chat_type == "group" and not fc.mentioned_bot(message.get("mentions", [])):
        return jsonify({"code": 0})

    # fail-closed 白名单：在任何回复/处理之前（含非文本分支），未授权静默丢弃，不成为存活探针
    if not fc.is_allowed(sender_name):
        log.warning("拒绝非白名单 from=%s（白名单%s）", sender_name,
                    "未配置" if not fc.CFG.allowed_users else "不含此人")
        return jsonify({"code": 0})

    if msg_type != "text":
        threading.Thread(target=reply_message, args=(message_id, "暂时只支持文本消息")).start()
        return jsonify({"code": 0})

    try:
        text = json.loads(message.get("content", "{}")).get("text", "").strip()
    except json.JSONDecodeError:
        text = ""
    for m in message.get("mentions", []):
        if m.get("key"):
            text = text.replace(m["key"], "").strip()
    if not text:
        return jsonify({"code": 0})

    # 异步处理（飞书要求 3s 内 ack）；reply 回调闭包绑定 message_id
    threading.Thread(
        target=fc.process,
        args=(lambda t: reply_message(message_id, t), sender_name, chat_id, text),
        daemon=True,
    ).start()
    return jsonify({"code": 0})


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "app_id": fc.APP_ID[:8] + "...",
        "encrypt_enabled": bool(fc.ENCRYPT_KEY),
        "work_dir": str(fc.CFG.work_dir),
        "tools": fc.CFG.allowed_tools,
        "whitelist": list(fc.CFG.allowed_users) or "all",
        "engine": fc.CFG.engine,
    })


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("Feishu webhook Server 启动  端口=%d  引擎=%s", fc.PORT, fc.CFG.engine)
    log.info("  工具=%s  并发上限=%d", fc.CFG.allowed_tools, fc.CFG.max_concurrency)
    log.info("  白名单=%s", list(fc.CFG.allowed_users) or "（未配置→fail-closed 拒绝所有）")
    log.info("=" * 60)
    if not fc.CFG.allowed_users:
        log.warning("⚠ ALLOWED_USERS 为空：当前拒绝所有人。先发一条消息从日志拿 open_id 填进 .env 再重启。")
    log.info("下一步：另开终端 'ngrok http %d'，URL+/event 填飞书事件订阅", fc.PORT)
    app.run(host="127.0.0.1", port=fc.PORT, debug=False)   # 只绑环回，公网经 ngrok
