# Feishu × Claude Code

三种模式，按需选：

| 模式 | 用谁 | 适用场景 | 需要 ngrok？ |
|------|------|----------|-------------|
| **A. 单向**（终端 → 群） | `feishu_send.py` | 定时报告、CLI 推送 Claude 结果到群 | ❌ |
| **B. 双向 · webhook**（群 ↔ Claude） | `feishu_app_server.py` | 群里 @机器人 提问，Claude 回答 | ✅ |
| **C. 双向 · WS 长连接** ⭐推荐 | `feishu_ws_server.py` | 同 B，但服务主动连飞书 | ❌ |

> ⭐ **新装/想稳定就用方案 C**：飞书官方 `lark-oapi` 长连接，服务主动连飞书，**不用 ngrok**——
> URL 不会漂移、不用回后台重填、不用 Flask dev server。业务逻辑（@严格比对 / 单飞 / 会话复用 /
> 白名单）与 B 完全复用。配合 [`../daemon/`](../daemon) 的 launchd 守护即可开机自启、崩溃自愈、不用开终端。
> 启动：`python feishu_ws_server.py`（前置：飞书后台事件订阅切到「使用长连接接收事件」）。

下面**方案 B** 讲 webhook 的完整搭建（理解原理用）；生产建议直接上 C。

---

## 方案 B 完整工作原理

```
手机飞书群                  飞书服务器                你的 Mac
[用户 @机器人 + 问题]
        │
        │ ① 用户消息上传
        ▼
   ┌─────────────┐
   │ 飞书云      │
   │             │ ② 飞书 POST 到你配置的 URL
   │             │────────────────────┐
   └─────────────┘                    │
                                       ▼
                              ┌────────────────┐
                              │ ngrok 隧道     │ 公网入口
                              │ https://xxx... │
                              └────────┬───────┘
                                       │ ③ 转发到 localhost:5858
                                       ▼
                              ┌────────────────┐
                              │ feishu_app_    │
                              │ server.py      │
                              │ - 解析事件      │
                              │ - 验证 token    │
                              │ - 调 claude -p │
                              └────────┬───────┘
                                       │ ④ 子进程
                                       ▼
                              ┌────────────────┐
                              │ claude -p ...  │ → Anthropic API
                              └────────┬───────┘
                                       │ ⑤ 拿到答案
                                       ▼
                              ┌────────────────┐
                              │ 调飞书 API      │
                              │ /reply          │
                              └────────┬───────┘
                                       │ ⑥ HTTPS
                                       ▼
                              [飞书云]
                                       │ ⑦ 推送
                                       ▼
                              [群里出现 Claude 回复]
```

**为什么需要 ngrok：** 飞书是公网服务，它要主动 push 消息到你电脑，但你 Mac 没有公网 IP。ngrok 给你一个临时公网 https 域名，转发到你 localhost:5858。

---

## 一步步操作

### Step 1：在飞书开放平台创建"企业自建应用"

> 你需要有一个飞书租户（个人注册一个免费的就行）。

1. 打开 https://open.feishu.cn → 登录
2. 左上角 **开发者后台** → **创建企业自建应用**
3. 填名字（例：Claude Bot）、上传图标 → 创建
4. 进入应用，在 **凭证与基础信息** 页面看到：
   - `App ID` 形如 `cli_xxxxxxxxxxxx`
   - `App Secret` 点"获取"
5. 把这两个填到 `.env`：
   ```
   FEISHU_APP_ID=cli_xxxxxxxxxxxx
   FEISHU_APP_SECRET=xxxxxxxxxxxxxxxx
   ```

### Step 2：开启机器人能力

1. 左侧 **添加应用能力** → 选 **机器人** → 启用
2. （可选）给机器人改个友好的名字和头像

### Step 3：配置权限（很重要）

左侧 **权限管理** → 搜索并开通这几个权限：

- `im:message` — 发送消息
- `im:message:send_as_bot` — 以机器人身份发消息
- `im:message.group_at_msg` — 接收群里 @机器人 的消息
- `im:message.group_at_msg:readonly` — 同上
- `im:message.p2p_msg` — 接收私聊消息（可选）
- `im:resource` — 接收图片等资源（可选）

开完后页面顶部会有"创建版本并发布"，提交一下（个人租户秒过）。

### Step 4：装并启动 ngrok

```bash
brew install ngrok
ngrok config add-authtoken <你的token>   # 注册 ngrok.com 拿
```

**先别启动 ngrok**，下面要先把服务器跑起来。

### Step 5：装依赖、配 .env、启动服务器

```bash
cd ~/Desktop/my-code/feishu-claude
cp .env.example .env
nano .env                 # 至少填 APP_ID / APP_SECRET / ANTHROPIC_API_KEY

chmod +x start.sh
./start.sh                # 装依赖 + 启动 server
```

看到这行就成了：
```
Feishu App Server 启动
  端口: 5858
```

### Step 6：另开终端启动 ngrok

```bash
ngrok http 5858
```

会输出：
```
Forwarding  https://abcd-1-2-3-4.ngrok-free.app -> http://localhost:5858
```

**复制这个 https URL，加上 `/event` 后缀**，例如：
```
https://abcd-1-2-3-4.ngrok-free.app/event
```

### Step 7：在飞书后台填事件订阅地址

1. 应用页面 → **事件订阅** → 配置 **请求地址**
2. 粘贴上面的 URL → 保存
3. 飞书会立刻发一个验证请求到这个 URL
4. 看你的 server 终端，应该打印：`URL 验证 challenge=...`
5. 飞书页面应显示"验证成功" ✅

> **加密配置（推荐但可选）：**
> 同一页面有 `Encrypt Key` 和 `Verification Token`。如果你想用：
> 1. 飞书页面点"设置" → 生成两个 key → 复制
> 2. 填到 `.env` 的 `FEISHU_ENCRYPT_KEY` 和 `FEISHU_VERIFY_TOKEN`
> 3. 重启 server

### Step 8：订阅消息事件

同一页面下方 → **添加事件** → 搜索：
- `接收消息 v2.0` (`im.message.receive_v1`) — 必选

加完保存，再次发布版本。

### Step 9：把机器人加进群

1. 飞书 App 里打开你的群 → 群设置 → 群机器人 → 添加
2. 找到你刚创建的 Claude Bot → 添加

### Step 10：测试

在群里 @ 这个机器人：
```
@Claude Bot 用三句话解释什么是大语言模型
```

应该看到：
1. 几秒内：机器人回复 "思考中..."
2. 一会儿后：Claude 的完整回答

同时观察你的 server 终端，应该有日志：
```
处理 from=ou_xxx text='用三句话解释...'
Claude 启动 user=ou_xxx prompt='用三句话解释...'
回复完成 from=ou_xxx len=200
```

---

## 常见坑

**ngrok 重启后 URL 会变** → 飞书后台要重新填一次。免费版每次重启 URL 都换，烦的话买个 $8/月 的固定子域名。

**飞书后台显示"地址不可达"**
- 检查 server 是不是真的在跑（`curl http://localhost:5858/health`）
- 检查 ngrok 是不是真的转发（浏览器打开 ngrok 那个 URL，应该看到 Flask 的 404 页面）
- URL 末尾有没有 `/event`

**消息发出去机器人没反应**
- 群里有没有真的 @机器人（光打名字不算，要弹出选框选）
- server 日志有没有打印消息？没有 = 飞书没推过来 → 检查事件订阅
- 有日志但没回 → 看是不是 Claude 报错或权限不对
- 飞书权限发布了吗？开了权限不发布 = 没生效

**Claude 一直说"思考中..."不出回答**
- `claude -p` 跑超时了 → 调大 `CLAUDE_TIMEOUT`
- `ANTHROPIC_API_KEY` 不对 → 看 server 终端的 stderr
- `claude` 命令找不到 → 在 .env 设 `CLAUDE_CMD` 绝对路径

**机器人回复了但不在我 @ 的那条下面**
- 用的是 `/reply` 接口，正常会"引用回复"。如果你想要新消息形式，把代码里 `reply_message` 改成 `send_message`（自己实现下）。

---

## 文件清单

```
feishu-claude/
├── feishu_send.py          # 方案 A：终端 → 群（一行命令测试 webhook）
├── feishu_app_server.py    # 方案 B：双向机器人服务器
├── start.sh                # 一键启动方案 B
├── .env.example            # 配置模板
├── requirements.txt        # Python 依赖
└── README.md               # 你正在看的这个
```

---

## 安全清单（上线前必检）

> ⚠️ **这套是"飞书消息 → 你 Mac 上跑 claude"**。一旦开了 Bash，**任何能 @ 机器人的人就能在你电脑上执行命令**。下面是默认收紧后的基线，别放松。

1. ✅ `.gitignore` 已含 `.env`（在仓库根目录），**secrets 绝不入库**
2. ✅ `CLAUDE_TOOLS` 默认已收成只读 `Read,Glob,Grep,WebFetch`。**要开 Bash/Write/Edit 必须想清楚=放开 shell**，且要配合下面的真沙箱
3. ⚠️ **`CLAUDE_WORK_DIR` 不是沙箱**：它只是 claude 的初始目录，开了 Bash 仍能 `cd /` 读写整个文件系统、读 `~/.ssh`。真要隔离，在 `~/.claude/settings.json` 配 `sandbox` 块（写限工作目录 + 网络 allowlist），或把 claude 跑进 Docker
4. ✅ `ALLOWED_USERS` **fail-closed**：留空 = 拒绝所有人（不再"空=放行所有人"）。先发一条消息从日志拿 open_id 再填
5. ✅ `FEISHU_VERIFY_TOKEN` 配上 = webhook 的鉴权层（用常量时间比对，防伪造请求）
6. ✅ `FEISHU_ENCRYPT_KEY` 配上 = 消息内容加密传输
7. ✅ server 只绑 `127.0.0.1`（不暴露局域网），公网入口只经 ngrok
8. 🔴 **如果 App Secret 曾明文存在过（如早期 .env），去飞书后台「凭证与基础信息」点重新生成一次**

---

## 下一步可以加

- 多轮对话上下文：用 `claude -c` 续话，按 chat_id 存 session
- 富文本/卡片回复：`msg_type` 改成 `interactive`，能加按钮
- 图片识别：用户发图 → 下载 → 用 vision 模式跑 Claude
- 长任务进度：流式输出 `--output-format stream-json` → 边跑边发"进度"消息

要哪个直接说。
