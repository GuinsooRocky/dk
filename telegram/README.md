# Telegram 渠道

把 Telegram bot 接到本机 Claude Code。走**官方 Bot API + long polling**（bot 主动拉消息），
**零公网回调、零封号、全球可用**，业务逻辑全复用 `../core`。三个渠道里最省心的一个。

## 3 步上手

1. **建 bot**：Telegram 里找 [@BotFather](https://t.me/BotFather) → `/newbot` → 取个名字 → 拿到 **token**
2. **配 .env + 装依赖**：
   ```bash
   cd telegram && cp .env.example .env
   # 填 TELEGRAM_BOT_TOKEN，ALLOWED_USERS 先留空
   pip install -r requirements.txt
   python telegram_bot.py
   ```
3. **拿 user id 回填**：私聊你的 bot 发一句 → 看日志 `拒绝非白名单 from=xxx` → 把数字 `xxx` 填进
   `.env` 的 `ALLOWED_USERS` → 重启。再发应回「思考中…」+ 答案。✅

## 怎么用

- **私聊**：直接发问题，所有文本都接
- **群里**：把 bot 拉进群，`@你的bot 问题` 或 `/c 问题` 触发
  （默认隐私模式下 bot 只收到 @它/回复它/命令的消息；想收群里所有消息可在 BotFather → `/setprivacy` 关掉，通常不必）

## 安全

与飞书/微信/企微同：工具默认只读、白名单 fail-closed、开 Bash 必须配 `../SANDBOX.md`。详见根目录 `../使用说明.md` §8。

> 白名单用 Telegram **数字 user id**（稳定），不是 @username（可改）。
