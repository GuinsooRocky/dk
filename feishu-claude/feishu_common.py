"""飞书渠道共享层（webhook 版与 WS 版共用）。

把"飞书特有但两个传输都需要"的东西收在这一份：配置/凭证、tenant_token、
机器人 open_id、单飞+会话+去重状态、以及 process() 编排（单飞→思考中→跑 claude→
会话复用→分段回复）。webhook / WS 两个入口只负责"解析入站事件 + 提供 reply 回调"。
"""
import os
import sys
import json
import time
import logging
import threading
from pathlib import Path
from urllib import request as urlreq

# ---- 引入跨渠道 core（core/ 在仓库根目录）----
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config, security, dedup, chunking, hub_client, replies  # noqa: E402

# ---- 加载 .env + 配置 ----
config.load_env(Path(__file__).parent / ".env")
CFG = config.load(str(Path.home() / "claude-feishu-workdir"))

APP_ID = os.getenv("FEISHU_APP_ID", "").strip()
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "").strip()
ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "").strip()
VERIFY_TOKEN = os.getenv("FEISHU_VERIFY_TOKEN", "").strip()
BOT_OPEN_ID = os.getenv("FEISHU_BOT_OPEN_ID", "").strip()
PORT = int(os.getenv("APP_PORT", "5858"))

MAX_FEISHU_MSG = 4000   # 飞书单条文本上限附近，超过分段

CFG.work_dir.mkdir(parents=True, exist_ok=True)
LOG_DIR = CFG.work_dir / ".logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "feishu_app.log"), logging.StreamHandler()],
)
log = logging.getLogger("feishu")

if not APP_ID or not APP_SECRET:
    log.error("缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET，请检查 .env")
    sys.exit(1)

# ---- 渠道侧只留去重（单飞/会话已上移到 Hub）----
DEDUP = dedup.Dedup()


# ---- tenant_access_token（加锁 + double-check 防并发重复刷新）----
_token_cache = {"value": None, "expire_at": 0}
_token_lock = threading.Lock()


def get_tenant_token() -> str:
    now = time.time()
    if _token_cache["value"] and _token_cache["expire_at"] > now + 60:
        return _token_cache["value"]
    with _token_lock:
        now = time.time()
        if _token_cache["value"] and _token_cache["expire_at"] > now + 60:
            return _token_cache["value"]
        body = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode("utf-8")
        req = urlreq.Request(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            data=body, headers={"Content-Type": "application/json"},
        )
        with urlreq.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_token 失败：{data}")
        _token_cache["value"] = data["tenant_access_token"]
        _token_cache["expire_at"] = now + data.get("expire", 7200)
        return _token_cache["value"]


# ---- 机器人自身 open_id（失败 10 分钟冷却，避免每条群消息同步阻塞 ack）----
_bot_id_lock = threading.Lock()
_bot_id_retry_at = 0.0


def get_bot_open_id() -> str:
    global BOT_OPEN_ID, _bot_id_retry_at
    if BOT_OPEN_ID:
        return BOT_OPEN_ID
    with _bot_id_lock:
        if BOT_OPEN_ID:
            return BOT_OPEN_ID
        if time.time() < _bot_id_retry_at:
            return ""
        try:
            token = get_tenant_token()
            req = urlreq.Request(
                "https://open.feishu.cn/open-apis/bot/v3/info",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urlreq.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            BOT_OPEN_ID = data.get("bot", {}).get("open_id", "")
            if BOT_OPEN_ID:
                log.info("自动获取机器人 open_id=%s", BOT_OPEN_ID)
            else:
                _bot_id_retry_at = time.time() + 600
                log.warning("/bot/v3/info 未返回 open_id，10 分钟内不再重试，@检测暂走宽松模式")
        except Exception:
            _bot_id_retry_at = time.time() + 600
            log.exception("获取机器人 open_id 失败，10 分钟内不再重试，@检测暂走宽松模式")
    return BOT_OPEN_ID


def mentioned_bot(mentions: list) -> bool:
    """群里是否 @ 了本机器人。能拿到 bot open_id 就严格比对；拿不到退回宽松模式
    （依赖飞书 group_at_msg 权限已预过滤；即便误判，白名单 fail-closed 仍会拦非授权用户）。"""
    bot_id = get_bot_open_id()
    if bot_id:
        return any((m.get("id") or {}).get("open_id") == bot_id for m in mentions)
    return bool(mentions)


def is_allowed(sender: str) -> bool:
    return security.is_allowed(sender, CFG.allowed_users)


def process(reply, sender: str, chat_id: str, text: str) -> None:
    """薄壳编排：白名单 → 思考中 → 转发给 Hub → 分段回复。reply 是 1 参回调(text)->None。
    不自己跑 claude（做菜在 Hub）；单飞/会话也在 Hub。webhook/WS 共用这一份。"""
    if not is_allowed(sender):
        hub_client.report_pending("feishu", sender)   # 实时抓 ID：上报让 app 显示"想加入"
        return
    if text.strip() in ("/start", "/help"):
        reply(replies.HELP)
        return
    log.info("转发 from=%s chat=%s text=%r", sender, chat_id, text[:80])
    reply(replies.THINKING)
    try:
        resp = hub_client.ask_hub_sync("feishu", chat_id, sender, text)
    except Exception as e:
        log.exception("调 Hub 失败")
        try:
            reply(replies.SERVICE_DOWN)
        except Exception:
            pass
        return
    answer = resp.get("text") or replies.NO_REPLY
    chunks = chunking.split_chunks(answer, MAX_FEISHU_MSG)
    for i, c in enumerate(chunks, 1):
        try:   # 单段失败不中断后续段（否则已发半条+剩余永久丢，且 dedup 已记账不重投）
            reply(c if len(chunks) == 1 else f"[{i}/{len(chunks)}] {c}")
        except Exception:
            log.exception("发送第 %d/%d 段失败，继续发后续段", i, len(chunks))
        if len(chunks) > 1:
            time.sleep(0.5)
    log.info("回复完成 from=%s len=%d", sender, len(answer))
