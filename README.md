# chat-cc-bot

把**飞书 / 微信**的消息桥接到本机 Claude Code（`claude -p`），在你自己的 Mac 上跑任务并把结果回到对话里。

## 结构

```
core/                      跨渠道共享（唯一一份）：config / runner(run_claude·cli+sdk) / security / dedup / chunking
feishu-claude/
  feishu_common.py         飞书共用层：凭证 / token / bot_id / 单飞·会话·去重状态 / process() 编排
  feishu_ws_server.py      ⭐WS 长连接入口（无 ngrok）
  feishu_app_server.py     webhook 入口（需 ngrok，fallback）
  feishu_send.py           单向：终端 → 群
wechat-claude-bot/
  claude_bridge.py         微信桥（Flask，调 core）
  wechat_bot.js            Wechaty 网关（Node）
daemon/                    launchd 守护（开机自启 + 崩溃自愈）
sandbox-settings.example.json + SANDBOX.md   真隔离模板
```

| 渠道 | 入站方式 | 触发 |
|------|----------|------|
| 飞书/Lark | WS 长连接（推荐，无 ngrok）/ webhook | 群里 @机器人 |
| 微信 | Wechaty（不需 ngrok） | 私聊 `/c ` 前缀 / 群 @机器人 |

各子目录 `README.md` 有详细搭建步骤。加新渠道只需写一个调 `core` 的薄入口。

---

## ⚠️ 安全前提（先读）

这套的本质是 **"一条 IM 消息 → 在你电脑上执行"**。所以：

- **工具默认只读**（`Read,Glob,Grep,WebFetch`）。开 `Bash/Write/Edit` 等于把 shell 暴露给任何能给机器人发消息的人——要开就必须配合真沙箱。
- **白名单 fail-closed**：`ALLOWED_USERS` 留空 = 拒绝所有人。
- **`CLAUDE_WORK_DIR` 不是沙箱**：它只是初始目录，开了 Bash 照样能读写全盘。真隔离见 [SANDBOX.md](./SANDBOX.md)——`cp sandbox-settings.example.json sandbox-settings.json` 后在 `.env` 设 `CLAUDE_SETTINGS=该文件`，只作用于 bot 起的 claude。
- **secrets 不入库**：根目录 `.gitignore` 已挡住 `.env`、wechaty 登录态、日志。

---

## 改造路线

- [x] **第一批 · 安全/正确性止血**：工具默认只读 / 白名单 fail-closed / 飞书 @机器人严格比对 open_id / event_id 去重 / 单飞限并发 + busy 提示 / 按会话复用 claude session（多轮记忆）/ token 缓存加锁 / 绑 127.0.0.1
- [x] **第二批 · 干掉痛点**（代码完成，待飞书后台切「长连接」+ 实跑验证）：飞书新增 `feishu_ws_server.py` 用 [lark-oapi](https://github.com/larksuite/oapi-sdk-python) WebSocket 长连接（无 ngrok，复用 B 全部逻辑，webhook 版保留作 fallback）；`daemon/` 下 launchd 守护 + 开机自启 + 崩溃自愈
- [x] **第三批 · 架构重构 + 真隔离**：抽 `core/`，三/四份 `run_claude` 收成一份；飞书 webhook/WS 共用 `feishu_common.process()`；[Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) 作可切换引擎（`CLAUDE_ENGINE=sdk`，默认 `cli`）；`sandbox-settings.example.json` + `--settings` 透传做真隔离
- [x] **bug 三件套评审**（bug-hunter→adversary→judge）：6 主 bug + 3 漏网全修，无 severe

---

> 个人自用工具。需要本机已安装并登录 Claude Code（`claude` 可执行）。
