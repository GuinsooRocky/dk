"""渠道薄壳 → Hub 的统一客户端：POST /chat 拿答案。

所有渠道壳（Telegram/飞书/企微）都用这一个去"递单给后厨"，自己不跑 claude。
Hub 在本机 127.0.0.1，所以 trust_env=False —— 不走系统代理（Clash 等），直连本地。
"""
import os
import time
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


async def answer_approval(approval_id: str, decision: str, by_user: str) -> dict:
    """把用户点的审批按钮回给 Hub。**必须 await 拿结果**——不能 fire-and-forget：
    Hub 可能因"点的人不是请求者"拒收，那要如实回给点的人，不能装作批准成功了。"""
    async with httpx.AsyncClient(trust_env=False, timeout=15) as c:
        resp = await c.post(f"{HUB_URL}/approval/answer", json={
            "approval_id": approval_id, "decision": decision, "by_user": str(by_user)})
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


def report_heartbeat(channel: str) -> None:
    """上报一次心跳：告诉 Hub 这个渠道不只是进程活着，连接循环真在跑。fire-and-forget。"""
    def _send():
        try:
            httpx.post(f"{HUB_URL}/heartbeat", json={"channel": channel},
                       trust_env=False, timeout=3)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()


def start_heartbeat(channel: str, interval: int = 120) -> None:
    """后台线程每 interval 秒上报一次心跳。给 telegram/feishu 这种阻塞主循环用——
    它们的 SDK 不暴露连接态，心跳=运行循环活着（已强于 supervisor 的"进程存在"）。"""
    def _loop():
        while True:
            try:
                httpx.post(f"{HUB_URL}/heartbeat", json={"channel": channel},
                           trust_env=False, timeout=3)
            except Exception:
                pass
            time.sleep(interval)
    threading.Thread(target=_loop, daemon=True).start()
