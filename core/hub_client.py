"""渠道薄壳 → Hub 的统一客户端：POST /chat 拿答案。

所有渠道壳（Telegram/飞书/企微）都用这一个去"递单给后厨"，自己不跑 claude。
Hub 在本机 127.0.0.1，所以 trust_env=False —— 不走系统代理（Clash 等），直连本地。
"""
import os
import threading

import httpx

HUB_URL = os.getenv("HUB_URL", "http://127.0.0.1:8787").rstrip("/")
# 必须 > Hub 的 CLAUDE_TIMEOUT(默认 300s)，留余量等 claude 跑完
_TIMEOUT = float(os.getenv("HUB_CLIENT_TIMEOUT", "320"))


def _payload(channel: str, chat_id: str, user: str, text: str, image_path: str) -> dict:
    return {
        "channel": channel, "chat_id": str(chat_id), "user": str(user),
        "text": text, "image_path": image_path,
    }


async def ask_hub(channel: str, chat_id: str, user: str, text: str, image_path: str = "") -> dict:
    """异步版（Telegram 等 async 壳用）。image_path 非空时让 claude 读图分析。"""
    async with httpx.AsyncClient(trust_env=False, timeout=_TIMEOUT) as c:
        resp = await c.post(f"{HUB_URL}/chat", json=_payload(channel, chat_id, user, text, image_path))
        resp.raise_for_status()
        return resp.json()


def ask_hub_sync(channel: str, chat_id: str, user: str, text: str, image_path: str = "") -> dict:
    """同步版（飞书/企微等跑在线程里的同步壳用）。"""
    with httpx.Client(trust_env=False, timeout=_TIMEOUT) as c:
        resp = c.post(f"{HUB_URL}/chat", json=_payload(channel, chat_id, user, text, image_path))
        resp.raise_for_status()
        return resp.json()


def report_pending(channel: str, sender: str) -> None:
    """把被白名单拒掉的发送者上报 Hub /pending（实时抓 ID）。fire-and-forget，绝不阻塞/抛错。"""
    def _send():
        try:
            httpx.post(f"{HUB_URL}/pending", json={"channel": channel, "user": str(sender)},
                       trust_env=False, timeout=3)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()
