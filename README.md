# chat-cc-bot

把**飞书 / 微信**的消息桥接到本机 Claude Code（`claude -p`），在你自己的 Mac 上跑任务并把结果回到对话里。

两个独立渠道：

| 目录 | 渠道 | 入站方式 | 说明 |
|------|------|----------|------|
| [`feishu-claude/`](./feishu-claude) | 飞书/Lark | ngrok webhook（双向）/ 群机器人 webhook（单向） | 群里 @机器人 提问 → claude 回答 |
| [`wechat-claude-bot/`](./wechat-claude-bot) | 微信 | Wechaty（不需 ngrok） | 私聊 `/c` 前缀 / 群里 @机器人 |

各自的 `README.md` 有详细搭建步骤。

---

## ⚠️ 安全前提（先读）

这套的本质是 **"一条 IM 消息 → 在你电脑上执行"**。所以：

- **工具默认只读**（`Read,Glob,Grep,WebFetch`）。开 `Bash/Write/Edit` 等于把 shell 暴露给任何能给机器人发消息的人——要开就必须配合真沙箱。
- **白名单 fail-closed**：`ALLOWED_USERS` 留空 = 拒绝所有人。
- **`CLAUDE_WORK_DIR` 不是沙箱**：它只是初始目录，开了 Bash 照样能读写全盘。真隔离用 `~/.claude/settings.json` 的 `sandbox` 块或 Docker。
- **secrets 不入库**：根目录 `.gitignore` 已挡住 `.env`、wechaty 登录态、日志。

---

## 改造路线

- [x] **第一批 · 安全/正确性止血**：工具默认只读 / 白名单 fail-closed / 飞书 @机器人严格比对 open_id / event_id 去重 / 单飞限并发 + busy 提示 / 按会话复用 claude session（多轮记忆）/ token 缓存加锁 / 绑 127.0.0.1
- [x] **第二批 · 干掉痛点**（代码完成，待飞书后台切「长连接」+ 实跑验证）：飞书新增 `feishu_ws_server.py` 用 [lark-oapi](https://github.com/larksuite/oapi-sdk-python) WebSocket 长连接（无 ngrok，复用 B 全部逻辑，webhook 版保留作 fallback）；`daemon/` 下 launchd 守护 + 开机自启 + 崩溃自愈
- [ ] **第三批 · 架构重构**：抽 `core/` + `ChannelAdapter`，三份 `run_claude` 收成一份；Claude 执行迁到 [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) 进程内常驻；`settings.json` sandbox 真隔离

---

> 个人自用工具。需要本机已安装并登录 Claude Code（`claude` 可执行）。
