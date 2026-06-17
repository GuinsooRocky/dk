# 企业微信（WeCom）渠道

把企业微信智能机器人接到本机 Claude Code。走 **WebSocket 长连接**（`bot_id + secret` 直连），
**无需 ngrok / 公网回调**，机制与飞书 WS 版对称，业务逻辑全复用 `../core`。

## 为什么走「智能机器人 + 长连接」而不是「自建应用 + 回调」

| 路子 | 公网回调(ngrok) | 加解密 | 备注 |
|---|---|---|---|
| 自建应用 + 回调 URL | 必需 | 需要 | 要内网穿透，麻烦 |
| **智能机器人 + 长连接** ⭐ | **不需要** | **不需要** | 本项目采用，镜像飞书 WS |

## 5 步上手

1. **建机器人**：企业微信管理后台 → 应用管理 → 机器人 → **智能机器人** → 创建，拿到 `bot_id` + `secret`
   （注册企业微信免费、不需要营业执照；未认证支持 200 成员，够个人 + 小群用）
2. **拉进群**：把机器人拉进一个群
3. **配 .env**：
   ```bash
   cd wecom && cp .env.example .env
   # 填 WECOM_BOT_ID / WECOM_BOT_SECRET，ALLOWED_USERS 先留空
   ```
4. **装依赖 + 启动**：
   ```bash
   pip install -r requirements.txt
   python wecom_ws_server.py
   ```
   看到 `WeCom 智能机器人长连接启动` 即连上。此时白名单空 → 拒绝所有人。
5. **拿 userid 回填**：群里 @ 机器人发一句 → 看日志 `拒绝非白名单 from=xxx` → 把 `xxx` 填进
   `.env` 的 `ALLOWED_USERS` → 重启。再 @ 它应回「思考中…」+ 答案。✅

> 首条消息会在日志打印完整 `frame.body`（标了 ⭐），用于核对企业微信回调真实字段名。

## 安全

与飞书/微信同：工具默认只读、白名单 fail-closed、开 Bash 必须配 `../SANDBOX.md`。详见根目录 `../使用说明.md` §8。
