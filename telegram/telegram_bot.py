"""Telegram 薄客户端 —— 收消息 → POST Hub /chat → 回发。不自己跑 claude。

"薄"：只负责传输层（收 Telegram 消息 + 白名单 + 去重 + 回发），
做菜（claude/单飞/会话）全在 Hub。需先起 Hub（python -m hub.app）。

启动：python telegram_bot.py
前置：@BotFather 拿 token；中国大陆需给本进程设 http_proxy（Telegram 被墙）。
"""
import os
import sys
import asyncio
import logging
import tempfile
from pathlib import Path

# ---- 复用 core 的去重/分段/白名单 + Hub 客户端 + 语音转写 ----
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config, security, dedup, chunking, hub_client  # noqa: E402

from telegram import Update  # noqa: E402
from telegram.ext import Application, MessageHandler, filters, ContextTypes  # noqa: E402

# ---- 加载 .env ----
config.load_env(Path(__file__).parent / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TRIGGER_PREFIX = os.getenv("TRIGGER_PREFIX", "/c ")
ALLOWED = tuple(u.strip() for u in os.getenv("ALLOWED_USERS", "").split(",") if u.strip())

MAX_TG_MSG = 3800   # Telegram 单条上限 4096，留余量分段

LOG_DIR = Path(os.getenv("CLAUDE_WORK_DIR", str(Path.home() / "claude-telegram-workdir"))).expanduser()
LOG_DIR = LOG_DIR / ".logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "telegram.log"), logging.StreamHandler()],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("telegram")

if not BOT_TOKEN:
    log.error("缺少 TELEGRAM_BOT_TOKEN，请检查 .env")
    sys.exit(1)

# ---- 去重留在渠道（去掉 Telegram 重投的同一条 update）----
DEDUP = dedup.Dedup()


def _should_handle(update: Update) -> bool:
    """私聊：所有文本都接。群聊：要么 @ 了 bot，要么 TRIGGER_PREFIX 开头。"""
    chat = update.effective_chat
    msg = update.effective_message
    if chat is None or msg is None or not (msg.text or ""):
        return False
    if chat.type == "private":
        return True
    text = msg.text or ""
    if text.startswith(TRIGGER_PREFIX):
        return True
    bot_username = (update.get_bot().username or "")
    return bool(bot_username) and (f"@{bot_username}" in text)


def _strip_trigger(update: Update, text: str) -> str:
    """去掉群里的触发前缀 / @bot，留下纯问题。"""
    if text.startswith(TRIGGER_PREFIX):
        text = text[len(TRIGGER_PREFIX):]
    bot_username = update.get_bot().username or ""
    if bot_username:
        text = text.replace(f"@{bot_username}", "")
    return text.strip()


async def _respond(context, chat_id: str, sender: str, text: str, heard: str = "", image_path: str = "") -> None:
    """占位 → 转发 Hub → 原地编辑成答案。heard(语音)回显听到的；image_path(图片)让 Hub 读图。"""
    ph_text = "🖼 看图中..." if image_path else (f"🎤 «{heard}»\n思考中..." if heard else "思考中...")
    placeholder = await context.bot.send_message(chat_id=chat_id, text=ph_text)
    log.info("转发 from=%s chat=%s text=%r img=%s", sender, chat_id, text[:80], bool(image_path))
    try:
        resp = await hub_client.ask_hub("telegram", chat_id, sender, text, image_path=image_path)
    except Exception as e:
        log.exception("调 Hub 失败")
        await context.bot.edit_message_text(
            text=f"后端(Hub)没连上：{e}", chat_id=chat_id, message_id=placeholder.message_id
        )
        return
    answer = resp.get("text") or "(空)"
    if heard:
        answer = f"🎤 «{heard}»\n\n{answer}"
    chunks = chunking.split_chunks(answer, MAX_TG_MSG)
    for i, c in enumerate(chunks, 1):
        body = c if len(chunks) == 1 else f"[{i}/{len(chunks)}] {c}"
        if i == 1:
            await context.bot.edit_message_text(
                text=body, chat_id=chat_id, message_id=placeholder.message_id
            )
        else:
            await context.bot.send_message(chat_id=chat_id, text=body)
            await asyncio.sleep(0.5)
    log.info("回复完成 from=%s len=%d", sender, len(answer))


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if not _should_handle(update):
            return
        msg = update.effective_message
        if DEDUP.seen(f"{update.effective_chat.id}:{msg.message_id}"):
            return
        sender = str(update.effective_user.id) if update.effective_user else "anon"
        chat_id = str(update.effective_chat.id)
        text = _strip_trigger(update, msg.text or "")
        if not security.is_allowed(sender, ALLOWED):
            log.warning("拒绝非白名单 from=%s", sender)
            return
        if not text:
            return
        await _respond(context, chat_id, sender, text)
    except Exception:
        log.exception("on_message 处理出错")


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """语音消息：下载 → 本地 SenseVoice 转写 → 当文本走 Hub。私聊才接（群语音难判触发）。"""
    try:
        msg = update.effective_message
        chat = update.effective_chat
        if msg is None or chat is None or chat.type != "private":
            return
        if DEDUP.seen(f"{chat.id}:{msg.message_id}"):
            return
        sender = str(update.effective_user.id) if update.effective_user else "anon"
        chat_id = str(chat.id)
        if not security.is_allowed(sender, ALLOWED):
            log.warning("拒绝非白名单(语音) from=%s", sender)
            return
        voice = msg.voice or msg.audio
        if voice is None:
            return
        try:
            tg_file = await context.bot.get_file(voice.file_id)
            with tempfile.TemporaryDirectory() as td:
                ogg = Path(td) / "v.ogg"
                await tg_file.download_to_drive(str(ogg))
                # transcribe 阻塞(ffmpeg+sherpa) → 丢线程池
                # 懒导入：让 numpy/sherpa-onnx 成为语音可选依赖（v1 无语音时零成本）
                from core import transcribe  # noqa: E402
                text = await asyncio.get_running_loop().run_in_executor(
                    None, transcribe.transcribe, str(ogg)
                )
        except Exception as e:
            log.exception("转写失败")
            await context.bot.send_message(chat_id=chat_id, text=f"语音转写失败：{e}")
            return
        if not (text or "").strip():
            await context.bot.send_message(chat_id=chat_id, text="没听清，再说一次？")
            return
        await _respond(context, chat_id, sender, text, heard=text)
    except Exception:
        log.exception("on_voice 处理出错")


# 图片落盘目录（claude 用 Read 读这里的图；答完即删）
_IMG_DIR = Path(os.getenv("CLAUDE_WORK_DIR", str(Path.home() / "claude-telegram-workdir"))).expanduser() / "images"


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """图片消息：下载最大尺寸 → 传路径给 Hub → claude Read 读图分析。私聊才接。"""
    try:
        msg = update.effective_message
        chat = update.effective_chat
        if msg is None or chat is None or chat.type != "private":
            return
        if DEDUP.seen(f"{chat.id}:{msg.message_id}"):
            return
        sender = str(update.effective_user.id) if update.effective_user else "anon"
        chat_id = str(chat.id)
        if not security.is_allowed(sender, ALLOWED):
            log.warning("拒绝非白名单(图片) from=%s", sender)
            return
        photo = msg.photo[-1] if msg.photo else None   # 最后一个=最大尺寸
        if photo is None:
            return
        caption = msg.caption or ""
        _IMG_DIR.mkdir(parents=True, exist_ok=True)
        img_path = _IMG_DIR / f"{photo.file_unique_id}.jpg"
        try:
            tg_file = await context.bot.get_file(photo.file_id)
            await tg_file.download_to_drive(str(img_path))
            await _respond(context, chat_id, sender, caption, image_path=str(img_path))
        finally:
            try:
                img_path.unlink()
            except Exception:
                pass
    except Exception:
        log.exception("on_photo 处理出错")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(MessageHandler(filters.COMMAND, on_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))

    log.info("=" * 60)
    log.info("Telegram 薄客户端启动（不跑 claude，转发给 Hub %s）", hub_client.HUB_URL)
    log.info("  白名单=%s", list(ALLOWED) or "（未配置→fail-closed 拒绝所有）")
    log.info("=" * 60)
    if not ALLOWED:
        log.warning("⚠ ALLOWED_USERS 为空：当前拒绝所有人。")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
