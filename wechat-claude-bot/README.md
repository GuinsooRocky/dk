# WeChat × Claude Code 桥接

让你在微信里给 Claude Code 发消息，Claude 在你的 Mac 上执行任务并把结果回到微信。

## 架构

```
手机微信 ──消息──> 微信服务器
                      │
                      ▼
            wechat_bot.js (Node + Wechaty)
                      │ HTTP POST /chat
                      ▼
            claude_bridge.py (Python + Flask)
                      │ subprocess
                      ▼
                 claude -p "..."  ← 跑在你的 Mac 上
                      │
                      ▼
              结果原路返回到微信
```

**关键点：** 你不需要 ngrok。Wechaty 主动连微信服务器，所有服务都在 localhost。

---

## 1. 一键安装

```bash
cd wechat-claude-bot
chmod +x setup.sh
./setup.sh
```

脚本会自动：检查 Node/Python、安装 Claude Code、安装 Python 和 Node 依赖、创建 `.env` 模板。

## 2. 配置 API Key

```bash
nano .env   # 或用其他编辑器
```

填入你的 `ANTHROPIC_API_KEY`（从 https://console.anthropic.com 拿）。

## 3. 启动两个进程

打开两个终端窗口：

**终端 1 — 启动 Bridge（Python 服务）：**
```bash
python3 claude_bridge.py
```
看到 `Claude Bridge 启动 端口: 5858` 就成功了。

**终端 2 — 启动 WeChat Bot（Node 服务）：**
```bash
node wechat_bot.js
```
首次运行会在终端打印一个二维码，**用手机微信扫码登录**（账号会作为机器人）。

> 二维码看不清？终端会打印一个网址 `https://wechaty.js.org/qrcode/...`，浏览器打开后扫码。

## 4. 测试

登录后试试：

| 场景 | 怎么发 |
|------|--------|
| **私聊自己**（最简单的测试） | 在微信里搜「文件传输助手」，发：`你好` |
| **私聊好友** | 让好友给你发：`/c 帮我写个 Python 冒泡排序` |
| **群聊** | 把这个微信号拉进群，群里 `@机器人名 + 内容` |

Claude 会在你 Mac 上的 `~/claude-wechat-workdir/<用户昵称>/` 目录里执行任务。

---

## 安全提醒（重要）

**加你的人理论上能让你的 Mac 跑命令。** 默认已收紧，下面是基线：

1. ✅ **工具默认只读**：`CLAUDE_TOOLS` 已默认 `Read,Glob,Grep,WebFetch`。开 Bash/Write/Edit = 微信消息可拿到 shell，务必配合下面的真沙箱
2. ✅ **白名单 fail-closed**：`ALLOWED_USERS` 留空 = 拒绝所有人（不再"空=放行所有人"）。在 `.env` 填 `ALLOWED_USERS=你的昵称,可信好友昵称`
3. ⚠️ **`CLAUDE_WORK_DIR` 不是沙箱**：它只是 claude 的初始目录，开了 Bash 仍能 `cd /` 读写全盘、读 `~/.ssh`。真隔离要在 `~/.claude/settings.json` 配 `sandbox` 块（写限工作目录 + 网络 allowlist），或把 claude 跑进 Docker
4. ⚠️ **白名单按微信昵称匹配，可被改名冒充**——只在可信小圈子用；长期方案是改用稳定的 contact id（见后续重构）

---

## Wechaty 风险说明

`wechaty-puppet-wechat4u` 用的是 web 微信协议，可能：
- **被微信封号**（小号风险高，主号慎用！强烈建议注册一个专用小号）
- 偶尔掉线，需要重新扫码
- 部分新功能不支持

如果你需要稳定的方案，可以付费购买 [puppet-padlocal](https://wechaty.js.org/docs/puppet-services/padlocal)（约 $60/月），或换成下面的企业微信方案。

---

## 备选：企业微信（WeCom）方案

如果你有企业微信，可以用更稳定的官方 API。和当前架构的区别：

- **消息接收**：企业微信服务器主动 POST 到你电脑 → **需要 ngrok 暴露 5858 端口**
- **消息发送**：你的服务调用企业微信 API 发消息

**需要改动：**

1. 在 [企业微信管理后台](https://work.weixin.qq.com) 创建「自建应用」
2. 启动 ngrok：`ngrok http 5858`，把得到的 URL 配到企业微信"接收消息 URL"
3. `claude_bridge.py` 加一个 `/wecom-callback` 路由处理企业微信的加密消息（参考 [企业微信回调文档](https://developer.work.weixin.qq.com/document/path/90930)）
4. 不需要 `wechat_bot.js`

如果你要走这条路，告诉我，我可以另写一份。

---

## 故障排查

**`claude: command not found`**
→ 把 `.env` 里的 `CLAUDE_CMD` 设为绝对路径，比如 `/Users/你的名字/.claude/local/claude`。用 `which claude` 查路径。

**Bridge 报 `Authentication error`**
→ `.env` 里的 `ANTHROPIC_API_KEY` 没填或写错了。

**Wechaty 一直显示扫码超时**
→ 用浏览器打开终端打印的二维码网址扫，别用终端里的字符二维码。

**消息收到了但 Claude 不回**
→ 看 Bridge 终端的输出。如果显示 `任务超过 X 秒`，把 `.env` 的 `CLAUDE_TIMEOUT` 调大。

**Bot 启动后掉线**
→ Wechat4u puppet 不太稳定，重启 `node wechat_bot.js` 再扫码即可。考虑换 padlocal。

**消息回复太长被微信截断**
→ Bot 已自动分段（每段 1500 字），如果还嫌长，调小 `wechat_bot.js` 里的 `MAX_LEN`。

---

## 文件清单

```
wechat-claude-bot/
├── claude_bridge.py    # Python: 包装 claude -p，HTTP 接口
├── wechat_bot.js       # Node:   Wechaty 监听微信消息
├── package.json        # Node 依赖
├── requirements.txt    # Python 依赖
├── setup.sh            # 一键安装
├── .env.example        # 配置模板
└── README.md           # 你正在看的这份
```

## 下一步可以加的功能

- 上下文记忆：把每个用户的对话历史存起来传给 Claude（用 `--resume`）
- 文件上传：用户发图片/文件，下载到工作目录，告诉 Claude 路径
- 流式输出：用 `--output-format stream-json` 边跑边发"进度"消息
- 命令快捷方式：`/code`、`/translate`、`/summarize` 等指令路由到不同 system prompt

需要哪个告诉我。
