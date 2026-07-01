# DK

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

把**飞书 / Telegram / 企业微信**的消息（含**语音**）桥接到本机 Claude Code，在你自己的 Mac 上跑任务并把结果回到对话里。**可自托管**：拿走填自己的 Claude + 自己的 bot token，跑自己的实例。

**环境要求**：macOS + 本机已安装并登录 Claude Code（`claude` 命令可执行）+ Python 3。

**两个底气：**
- **默认安静**：群里不 @ 它、不用触发词就一句不说，不刷屏（私聊才有问必答）。
- **隐私即架构**：对话只在你自己的 Mac 上经 Claude 处理——Hub 绑 `127.0.0.1` 只本机可达、不经任何第三方中继；工具默认只读；白名单 fail-closed（空名单=谁都拒）。

## 架构（hub 中枢）

```
Telegram / 飞书 / 企微 三个渠道壳（收消息+语音转写）
              │
              ▼  POST /chat
Hub（FastAPI，只绑 127.0.0.1，唯一大脑）── 跑 claude · 全局单飞 · 按会话记忆
              ▲
              │  你也能直接 curl
菜单栏 App(rumps) ── 轮询 /status /stats，显示存活/用量

supervisor.py 一条命令拉起 hub + 全部启用渠道，崩溃自愈
```

- **Hub** = 唯一跑 claude 的地方（全局单飞，内存可控）；渠道是**薄转发壳**；加渠道≈复制一个壳。
- **语音**：壳下载语音 → 本地 SenseVoice 转写（复用 MK 模型，离线免费）→ 走 /chat。

## 🚀 一键启动

```bash
cp config.example.toml config.toml     # 填：至少一个渠道 enabled + token + allowed_users
./run.sh                               # = python3 supervisor.py，起 hub + enabled 渠道，崩溃自愈
```

**菜单栏仪表盘**（macOS，显示存活/用量）：`menubar/.venv/bin/python menubar/app.py &`

> 各渠道首次需建自己的 venv + 装依赖（见各子目录 README）。详细从零上手：[使用说明.md](./使用说明.md)。

## 结构

```
core/                      跨渠道共享（唯一一份）：config / runner(run_claude·cli+sdk) / security / dedup / chunking
feishu-claude/
  feishu_common.py         飞书共用层：凭证 / token / bot_id / 单飞·会话·去重状态 / process() 编排
  feishu_ws_server.py      ⭐WS 长连接入口（无 ngrok）
  feishu_app_server.py     webhook 入口（需 ngrok，fallback）
  feishu_send.py           单向：终端 → 群
telegram/
  telegram_bot.py          Telegram 官方 Bot API 长轮询入口（无 ngrok，调 core）
wecom/
  wecom_ws_server.py       企业微信智能机器人长连接入口（无 ngrok，调 core）
daemon/                    launchd 守护（开机自启 + 崩溃自愈）
sandbox-settings.example.json + SANDBOX.md   真隔离模板
```

| 渠道 | 入站方式 | 触发 |
|------|----------|------|
| 飞书/Lark | WS 长连接（推荐，无 ngrok）/ webhook | 群里 @机器人 |
| Telegram | 官方 Bot API 长轮询（无 ngrok，零封号） | 私聊直接发 / 群 `/c ` 前缀 / @机器人 |
| 企业微信 | 智能机器人长连接（无 ngrok） | 群里 @机器人 |

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

## License

[MIT](./LICENSE)

> 个人自用工具起步，欢迎 fork/自托管；不主动维护 issue/PR。
