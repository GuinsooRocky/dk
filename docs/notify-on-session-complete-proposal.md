# "Claude session 完成 → webhook 回调 → 多渠道通知" 的产品链路 + 技术选型方案

> 面向 chat-cc-bot 维护者的调研 + 设计提案。读完你应该能拍板：要不要做、做哪条路径、第一步动哪个文件。

---

## 1. 一句话定位 + 解决什么

**一句话**：现在 chat-cc-bot 是"你在 IM 里发消息 → bot 跑 claude → 回你"（入站）。这个功能是把箭头反过来——**"本机某个 Claude session 跑完了 → 自动把结果推到你的飞书群 / Telegram"（出站）**。

**解决的真实痛点**：你起了一个长任务（让 Claude 重构、跑测试、做调研），然后切走干别的。任务什么时候跑完？现在只能回去盯终端。这个功能让 session 一结束就主动 ping 你，附上"用时多久、几轮、最后一句输出是什么"，你在飞书里就知道该回去验收了。

**它是现有入站 bot 的反向链路**：入站复用的是 `core/hub_client.py` 的 `ask_hub`（壳 → hub）；出站要补的是 hub → 渠道的那条**目前不存在的**反向通道（详见 §3 的核心矛盾）。

---

## 2. 产品逻辑链路（完整 UX）

整个体验分三段：**纳管（把一个 session 标记为"要通知我"）→ 干活 → 收到通知**。

按"通知谁起的 session"分成两条路径，UX 略有差别：

### 路径 A：监听一个独立的本地 Claude session（主场景）

你在某个目录开了一个交互式 `claude` 会话（不是 bot 起的），想让它跑完通知你。

1. **纳管**：在那个 session 里（或用菜单栏点一下），跑一条命令把它纳入监听：
   ```
   python -m hub.watch register            # 用默认渠道
   python -m hub.watch register --channel telegram   # 指定渠道
   ```
   这条命令会**按内容指纹**认出"当前是哪个 session"（见 §5 的并发坑），写一行路由：`session_id → {渠道, 目标}`。
2. **选渠道**：飞书 / Telegram。飞书目标就是 `feishu-claude/.env` 里那个 `FEISHU_WEBHOOK_URL`（群机器人，不需要 chat_id）；Telegram 目标是注册当时抓到的真实 chat_id（**不是**白名单里的 user_id，见 §5 串台坑）。企微暂不支持出站，会明确报错或改投飞书/TG。
3. **干活**：你正常用 Claude，不用管。`~/.claude/settings.json` 里那个全局 hook 早就装好了，对你透明。
4. **触发**：session 结束（`/clear`、退出、超时）时，Claude Code 运行时用 stdin 喂给 hook 脚本一段 JSON（`session_id`、`transcript_path`、`cwd`、`end_reason`）。hook 脚本先查"这个 session 注册了吗"——没注册就**静默 exit 0**（全局 hook 会看到机器上**所有** session，绝大多数是噪声）。
5. **组装消息**：hook 读 `transcript_path`（JSONL）算出状态（ok/error）、最后一条 assistant 输出当摘要、轮数、用时，POST 到 `http://127.0.0.1:8787/notify`。
6. **路由 + 推送**：hub 的 `/notify` 按 `session_id` 查路由，格式化文案，**跨进程推出去**（飞书 = 子进程跑 `feishu_send.py --raw`；Telegram = 新建一次 HTTP 调 Telegram API）。
7. **收到**：你的飞书群/TG 里弹出：
   ```
   ✅ Claude 会话完成 · ~/Desktop/my-code/foo · 用时 4m12s · 8 轮
   最后输出：<摘要…>
   ```
8. **注销**：session 一结束就自动删掉这行路由（一次性）；另有个清扫器删超过 24h 的残留行，注册表不会无限长。

### 路径 B：监听 bot 自己起的 session（hub `/chat` 驱动的跑）

bot 收到 IM 消息后，是用 `core/runner.py` 的 `_run_cli` 起 `claude -p` 子进程（runner.py:56-72）。这种"自己起的跑"**有现成的退出状态**（runner 返回 `{ok, text, session_id}`），不需要靠 hook 去猜。

所以路径 B 更简单也更准：在 `core/runner.py` 跑完那一刻直接回调一次 `/notify`（约 10 行）。但它**只能**通知 bot 自己起的跑，看不到你手敲的交互式 session——所以它是路径 A 的补充，不是替代。

**两条路径的分工铁律**：同一个 `session_id` 只能由一条路径负责通知（runner 回调管 hub 自己的跑，hook 管交互式跑），否则会双触发。靠"hub 自己起的 claude 都打了 `CHATCC_SUPERVISED=1` 环境标记"（supervisor.py:256）来区分——见 §5 的死循环坑。

---

## 3. 技术选型

### 3.1 触发机制：社区/官方三种方案对比

| 方案 | 怎么触发 | 能看到非 bot 起的 session？ | 准确性（"跑完"语义） | 崩溃时还能通知吗 | 改动量 | 评价 |
|---|---|---|---|---|---|---|
| **CC 原生 hook（SessionEnd）** | `~/.claude/settings.json` 配全局 hook，session 结束时 CC 运行时用 stdin 喂 JSON 调脚本 | ✅ 全局 hook 看到所有本机 session | 高——一个 session 只触发一次，干净的"完成"语义 | ❌ `kill -9`/硬崩溃不触发（只在优雅退出时） | M | **推荐主触发**。唯一能观测"你没让 bot 起的任意本地 session"的官方机制 |
| **CC 原生 hook（Stop）** | 同上，但每轮 Claude 回复完都触发 | ✅ | 低——**每一轮**都触发，刷屏；CC 不给 `is_final` 标志，要自己过滤"最后一轮"很脆 | ❌ 同上 | M | ❌ 别用作完成通知，噪声太大 |
| **tail JSONL watcher（守护进程）** | supervisor 起个常驻进程 tail `~/.claude/projects/**/*.jsonl`，从文本变化推断"跑完" | ✅ 而且 transcript 在磁盘上，**硬崩溃也能补通知** | 低——从"还在追加写"的 JSONL 里判"这轮完了 vs 整个 session 完了"天生易误判（空闲间隔会误触发，长 tool call 看着像跑完一轮） | ✅ 比 hook 强 | L | 想要"崩溃也通知"才值得；否则代码最多、最容易悄悄写坏 |
| **Agent SDK / runner 后置回调** | 在 `core/runner.py` 跑完那刻直接回调 | ❌ 只能看 bot 自己 `/chat` 起的跑 | 高——有真实退出状态，不靠启发式 | n/a | S | 只能覆盖路径 B，作为 bonus 路径，不能单独成事 |

**官方文档参考**：Claude Code Hooks — <https://docs.claude.com/en/docs/claude-code/hooks>（SessionEnd / Stop / SubagentStop / Notification 等生命周期事件，支持 `type: "command"` 与 `type: "http"`，后者可直接 POST webhook 带 `$ENV_VAR` 注入的 Authorization 头）。

> 关于 `type: "http"`：理论上 hook 能不经脚本直接 POST `/notify`。但我们仍走 `type: "command"` + 一个小脚本，因为**注册表过滤（没注册就静默 exit）和 bot 自身 work_dir 排除**这两步必须在 POST 之前做，纯 http hook 做不了这个门控。

### 3.2 推荐的端到端架构

**主触发 = 全局 SessionEnd hook**，**bonus = runner 后置回调**，路由存本地 JSON 文件。

```
┌─ 交互式 session 结束 ─┐         ┌─ bot 自己的 /chat 跑完 ─┐
│ ~/.claude/settings.json│         │ core/runner.py _run_cli │
│  SessionEnd hook       │         │  返回 {ok,text,sid} 后  │
│   ↓ stdin JSON         │         │  直接回调（路径 B）      │
│ hub/notify_hook.py     │         └───────────┬─────────────┘
│  1. cwd 在 bot work_dir?→exit0   │            │
│  2. session 注册了吗? →没→exit0   │            │
│  3. 解析 transcript    │          │            │
│  4. POST /notify ──────┼──────────┴──→ POST 127.0.0.1:8787/notify
└────────────────────────┘                       │  带 X-Notify-Token 头
                                                   ↓
                                          hub/app.py  @app.post("/notify")
                                          按 session_id 查 notify_routes.json
                                                   ↓ 线程池里阻塞推送
                          ┌────────────────────────┼────────────────────────┐
                          ↓ 飞书                    ↓ Telegram               ↓ 企微
              subprocess: feishu_send.py    httpx 新建一次 HTTP        ❌ 不支持
              --raw '<text>'                api.telegram.org/...        报错/改投
              （复用现成 standalone 发送器）  sendMessage(chat_id=真实目标)
```

**复用 vs 新建清单**：

| 组件 | 文件 | 复用/新建 | 说明 |
|---|---|---|---|
| 全局 hook 配置 | `~/.claude/settings.json` | 新建（配置项） | 用 `update-config` skill 装一次，让 harness 而非 Claude 拥有这个自动行为 |
| hook 脚本 | `hub/notify_hook.py` | 新建（~50 行） | stdin 读 JSON → 门控 → 解析 transcript → POST。**永远 exit 0**，绝不卡崩用户 session。httpx 用 `trust_env=False`（学 `core/hub_client.py:25`，避开 Clash/grpc 污染） |
| 注册 CLI | `hub/watch.py` | 新建（小） | `register`/`unregister`；按内容指纹认 session_id（**不用 mtime**） |
| `/notify` 端点 | `hub/app.py` | 新建路由 + Pydantic 模型 | 机械上跟现有 `/pending`（app.py:182）一模一样：`class NotifyIn(BaseModel){session_id,status,summary,cwd,duration_sec,turns}` |
| 飞书推送 | `feishu-claude/feishu_send.py` | **逐字复用** | 子进程跑 `feishu_send.py --raw '<text>'`（send_to_feishu 在 feishu_send.py:40，webhook + HMAC，已能独立跑）。仓库本来就用 `supervisor._venv_py` 按渠道跑各自 venv（supervisor.py:44） |
| Telegram 推送 | hub 内新 helper | 新建（~10 行） | httpx POST `api.telegram.org/bot<token>/sendMessage`。**没有现成 standalone 发送器可复用**——`telegram_bot.py` 的 `Application` 只活在 `main()` 进程内（telegram_bot.py:204），跨进程够不着，新建一次 HTTP 调用是官方认可的跨进程路径。token 取自 `config.toml [telegram].token` |
| 企微 | — | 仅加 guard | reply 是 frame-bound（`wecom_ws_server.py:145` `client.reply(frame,…)`），没有 by-chatid 的 out-of-band 发送被 import/用到。诚实地拒绝并改投，不编造 SDK 调用 |
| 路由存储 | `notify_routes.json` | 新建小文件 | 放 `config.runtime_dir()`（`~/.chat-cc-bot/`，core/config.py:31-35，本来就是跨进程状态交换目录）。JSON 文件即可，符合仓库 no-Redis 风格 |
| runner 回调 | `core/runner.py` | 新建（~10 行，可选） | 路径 B：`_run_cli` 返回后 POST `/notify` |

**路由数据怎么存**：

- 以 **`session_id` 为唯一路由键**（注册 CLI 和 hook 都能拿到的稳定身份）。个人规模下一个人拥有所有 session，**不需要** user→渠道 表。
- 行结构：`{session_id: {channel: "feishu"|"telegram", target: "<TG 真实 chat_id>"|null, registered_at: ts}}`。飞书 target 为 null（webhook 自带唯一群）；Telegram target 在**注册当时**就抓真实 chat_id 存进去。
- 一次性生命周期：注册时建，SessionEnd 时消费 + 删，>24h 残留行清扫。

**`ralph/smoke_test.py`**：`REQUIRED_ENDPOINTS` 现在是 `('/chat','/status','/supervisor','/health')`（smoke_test.py:33）。加 `/notify` 不会破现有冒烟测试；想纳入校验可顺手加进去。

---

## 4. 三方案对比与拍板

直接引用评审排名（满分 100）：

### 🥇 方案一 hook-push（82 分）— **拍板选它**
> 全局 SessionEnd hook → POST `/notify` → hub 用 standalone 发送器扇出。

- **契合度 9/10**：`/notify` 跟现有 `/chat`、`/pending`（app.py:75/182）的 FastAPI+Pydantic 模式完全一致；飞书逐字复用 `feishu_send.py:40`；Telegram 新建 HTTP 是唯一诚实的跨进程路径；`trust_env=False` 对齐 `hub_client.py` 和那条 Clash/grpc 污染记忆。
- **能否监听非 bot session 10/10**：全局 `~/.claude/settings.json` SessionEnd hook 是**唯一**能观测你没让 bot 起的任意交互式 session 的机制——这是本功能的决定性差异点。
- **健壮性 6/10**：一个 session 只触发一次（无每轮误报），干净的完成语义；但 `kill -9`/硬崩溃不触发（静默漏），transcript 可能写一半（解析残缺），`end_reason → ok/error` 是启发式。并发 session 没问题（session_id 是路由键）。
- **配置/UX 8/10**：零新增凭证（`FEISHU_WEBHOOK_URL`、`[telegram].token/allowed_users` 都已存在）；纳管一条命令；企微诚实标注不支持。
- **改动量 8/10**：货真价实的 M——大部分发送代码复用，注册表是一个小 JSON，解析器约 30 行。

### 🥈 方案二 watcher-daemon（71 分）
> supervisor 托管一个常驻进程 tail JSONL，从 transcript 推断完成，再调渠道发送原语。

- **优点**：零 settings.json 改动；transcript 在磁盘上，**硬崩溃也能补通知**（比 SessionEnd 强）。
- **致命弱点（健壮性 4/10）**：从"还在追加写"的 JSONL 里推断"这轮完了 vs 整个 session 完了"天生易误报——空闲间隔会误触发，长 tool call 看着像跑完。并发 session = N 个交错写的增长文件，要做 per-file offset + 防抖 + 内容指纹去重才不双触发，**最容易悄悄写坏**，代码量最大（L）。而且它想"用共享 lark Client 发飞书"，但那个 out-of-band Client 根本不存在——只有 webhook 版 `feishu_send.py`，所以实际上它还是收敛到跟方案一同一批发送原语。

### 🥉 方案三 runner 后置回调（48 分）
> 只在 hub 自己 `/chat` 驱动的跑跑完时回调 `/notify`。

- 契合度 8/10、改动量 9/10 都很好，退出状态真实（健壮性 8/10）。
- **硬伤（能否监听非 bot session 1/10）**：只能通知 bot 自己起的跑，永远看不到你的交互式 Claude session——而那恰恰是本功能的全部意义。**只能当方案一的补充路径（路径 B），不能单独成事**。

**最终拍板（评审 synthesis）**：以**方案一为骨架**（干净触发 + 精确复用 `/notify`），嫁接方案二的**内容指纹认 session**（不靠 mtime）；把方案三留作 hub 自起跑的 **bonus 路径**。是否再补 watcher 做"崩溃也通知"——见 §7 开放问题。

---

## 5. 安全与坑（红队 P0/P1 + 缓解）

> 这一节是这份方案最重要的部分。下面四个坑里有两个已被 ground truth 实证。

### 🔴 P0 — bot 自己的 claude 触发自通知（已实证）

**问题**：hub 每个 IM 轮次都用 `claude -p` 子进程跑（`core/runner.py` `_run_cli`），**这些 headless 跑也会往 `~/.claude/projects` 写 transcript**——已核实：`~/.claude/projects/-Users-lengmo-claude-hub-workdir-feishu-ou-a3853aff.../` 下已经躺着 8 个 session jsonl，一个 hub 跑一个。全局 SessionEnd hook 会在**每一个** bot 起的 claude 进程上触发。当前唯一的闸是"注册表查找"（没注册就不通知），它防住了刷屏；但如果你哪天**真把一个 hub-workdir 的 session 注册了**，或者菜单栏"watch this session"点到了一个 hub 跑上，就会触发——更危险的是若推送动作本身又会调 claude（今天不会，但 `feishu_send.py` 去掉 `--raw` 就会调 claude，见 feishu_send.py:87），就会**循环**。注册表这个闸是唯一的断环器，且没文档化。

**缓解**：
1. **在注册表查找之前就硬排除 bot 自己的 work_dir 树**：`notify_hook.py` 从 stdin 读 `cwd`，只要在 `~/claude-hub-workdir` / `~/claude-feishu-workdir`（`CFG.work_dir` 根）下就立刻 `exit 0`。
2. **环境标记兜底**：hub 起的 claude 已经带 `CHATCC_SUPERVISED=1`（supervisor.py:256）。让 hook 检查这个标记自识别 bot 起的进程，双保险。
3. **永远禁止把 hub 起的 session 纳入注册**。
4. **runner 回调和 hook 对同一 session_id 必须互斥**：runner 路径管 hub 跑、hook 管交互式跑，加一条显式的来源优先级规则（两边产生的内容 hash 不会相同——一个是启发式摘要、一个是真实退出状态——所以光靠 hash 去重不够）。

### 🔴 P1 — 未鉴权的 `/notify` 变成开放转发器（伪造/钓鱼）

**问题**：现有所有 hub 端点（`/chat`、`/config/*`、`/allowlist`）都没鉴权，但它们只改本地状态或在本地跑 claude。`/notify` **性质不同**：它把 hub 变成一个开放中继，能把**攻击者控制的文本**推到你的飞书群/Telegram。本机任意进程、任意浏览器标签页（DNS-rebinding 到 127.0.0.1，或一个普通 CSRF POST——FastAPI 没有 CORS/Origin 检查，简单 JSON body 不触发预检）、任意恶意 npm/pip postinstall，都能 `POST 127.0.0.1:8787/notify` 来刷屏或钓鱼你的 IM，消息看着就像你自己 bot 发的。**"绑 127.0.0.1"不等于"只有可信调用方"**——机器上每个进程和浏览器都够得着它。

**缓解**：
1. **`/notify` 要共享密钥**：hub 启动时生成一个 token，写到 `CFG.work_dir/.notify_token`（0600），`notify_hook.py` 和 runner 回调读它，放进 `X-Notify-Token` 头；不匹配返回 403。
2. 自定义头要求顺带防 CSRF/DNS-rebinding（跨源简单请求设不了自定义头，除非走 CORS 预检）。
3. 按 `session_id` 限流。
4. **别把"127.0.0.1 上不鉴权没事"这个先例当许可**——出站推送是一类全新的能力。

### 🟠 P1 — Telegram 串台/发错人（已实证）

**问题**：方案里把 Telegram 的 `sendMessage` chat_id 设成 `[telegram].allowed_users`。但 `telegram_bot.py` 里真正的投递目标是 `str(update.effective_chat.id)`（line 113）——消息来自哪个 chat（群的话是负数群 ID，**不是** user ID）。`ALLOWED_USERS` 是**发送者白名单**（user ID），不是 chat 列表。后果：(a) 若 session 是从群里驱动的，通知发去错的目标或 400（chat not found）；(b) 若白名单里有多个用户，方案任意挑一个 → 用户 A 的 session 摘要（**可能含 claude 读到的文件路径、代码、密钥**）被推给用户 B。

**缓解**：在 `watch register`/菜单栏纳管那一刻，**捕获并存下渠道实际用的投递目标**——Telegram 就是原始 `/chat` 携带的 `effective_chat.id`（hub 要把 chat_id 透传进路由行，**不要**从白名单反推）。`notify_routes.json` 行里那个 `target` 字段在注册时就填真实 chat_id，Telegram 推送照 `row.target` 原样发，**永远不发给 allowed_users**。加测试：在群里注册然后完成，必须投到群、不是私聊。

### 🟠 其他坑（P2，方案自己列的失败模式）

- **Stop hook 每轮刷屏**：若误用 Stop 而非 SessionEnd，每轮都触发。默认设计只用 SessionEnd 彻底规避。
- **session_id 认错（mtime 陷阱）**：`watch register` 若按 mtime 猜 session_id，会抓到并发的另一个 chat-cc-bot session（用户记忆"认 session 按内容非 mtime"明确警告过）。必须按内容指纹认，且要和 hook 看到的是同一来源。
- **transcript 写一半**：SessionEnd 触发时文件可能还在写/被锁，摘要/用时解析出垃圾。解析器要容忍残读，降级成"已完成（摘要暂不可用）"。
- **硬崩溃不通知**：`kill -9`/进程被杀只有优雅退出才触发 SessionEnd，崩溃的 session 永远不 ping，你会干等。要堵这个缺口得上 watcher（见 §7）。
- **飞书子进程成本**：每次通知 spawn 一个 venv python 偏重，且依赖 `feishu-claude/.venv` 存在 + `FEISHU_WEBHOOK_URL` 已配；webhook 没配时 `feishu_send.py` 会 `sys.exit(1)`，hub 要把 `ok:false` 暴露出来而不是挂住。
- **end_reason 语义模糊**：`clear`/`logout`/`other` 不能干净映射到成功/失败，status 是启发式，可能把失败的 session 误标 ✅。

---

## 6. 落地步骤 / 待做清单（按里程碑 + effort）

> 状态：**全部待做（TODO）**，已按 §8 拍板决策定稿范围。整体 effort = **L**（watcher 崩溃兜底 + 企微出站调研拉高）。建议先把 M0+M1 跑通看一次真实通知，再补 M2 安全、M4 watcher、M5 企微。

- [ ] **M0 链路打通（飞书 + Telegram happy path）** — *S→M* — 决策①：两个渠道都默认、可切
  - [ ] `/notify` 端点 + `NotifyIn` Pydantic 模型（仿 `hub/app.py:182` 的 `/chat`）
  - [ ] 飞书 pusher：子进程跑 `feishu_send.py --raw`（`feishu_send.py:40` 逐字复用）
  - [ ] Telegram pusher：`httpx` 调 `sendMessage`（~10 行，注册时抓**真实 chat_id**）
  - [ ] `config.toml` 新增 `[notify]` 默认渠道键，飞书/TG 可切；`/config/notify` 端点（仿 `app.py:140`）
  - [ ] curl 手测 `/notify`
- [ ] **M1 全局 hook + 注册（CLI）** — *M* — 决策④：纳管入口先只做 CLI，不做菜单栏
  - [ ] `notify_hook.py`：读 stdin JSON → 查注册表 → 命中才 POST；**P0 缓解**：work_dir 硬排除 + `CHATCC_SUPERVISED=1`（`supervisor.py:256`）检查，跳过 bot 自起进程；始终 `exit 0`
  - [ ] `hub/watch.py register`：**内容指纹认 session（非 mtime）** —— 否则会抓到并发的 bot 自己会话（见 memory `认 session 按内容非 mtime`）
  - [ ] 用 `update-config` skill 把 SessionEnd hook 装到 `~/.claude/settings.json`（自动化行为归 harness 不归 Claude）
- [ ] **M2 鉴权（P1，不可省）** — *S*
  - [ ] `/notify` 加 `X-Notify-Token` 共享密钥 + 403 + 按 `session_id` 限流；`.notify_token` 文件 0600
- [ ] **M3 transcript 解析 + 容错** — *S*
  - [ ] 容忍残读的 JSONL 解析器（状态/摘要/轮数/用时）+ 降级文案「completed（摘要不可用）」
- [ ] **M4 watcher 崩溃兜底** — *L* — 决策②：一起做（并入方案二 watcher-daemon）
  - [ ] `supervisor.py` 托管的 watcher 进程：tail `~/.claude/projects/**/*.jsonl`，堵 `kill -9` / 崩溃不触发 SessionEnd 的缺口
  - [ ] 内容指纹 + per-file offset 游标 + debounce；**与 SessionEnd hook 去重**（同 `session_id` 只发一次）
  - [ ] ⚠️ 重点测 **turn-end vs session-end 误判**（live-append JSONL 推断"完成"易假阳性，是这块最容易写坏的地方）
- [ ] **M5 企微出站调研 + 支持** — *M* — 决策⑥：继续查并尝试支持
  - [ ] 调研 `wecom_aibot_sdk` 是否有 **by-chatid 主动发送** API（当前没被 import/用到）
  - [ ] 有 → 做 wecom pusher + 注册时提前存 chatid；无 → `/notify` 对企微明确报错并提示改投飞书/TG
- [ ] **M6 收尾** — *S*
  - [ ] 注册表 24h 残留行清扫
  - [ ] `ralph/smoke_test.py` 把 `/notify` 纳入校验
  - [ ] 决策③：runner 后置回调（路径 B，bot 自起长任务也通知）——`core/runner.py` 改 ~10 行，**默认关**，避免和 hook 注册表逻辑打架

**不做项**：决策⑤ —— Stop hook 的「每轮 ping」**不做**（CC 不给 `is_final`，过滤最后一轮太脆，且会刷屏）。只做 SessionEnd 的「完成通知」。

---

## 7. 安全前提（落地时必须满足）

- `/notify` 绑 `127.0.0.1` + `X-Notify-Token` 校验（M2），堵未鉴权伪造转发器。
- hook 必须 `exit 0`，绝不阻塞/拖慢用户自己的 session。
- hook → hub 走 `httpx(trust_env=False)`（对齐 `core/hub_client.py:25`，躲 Clash/grpc 代理污染）。
- 路由 key 用 `session_id`，target 用注册时抓的真实 chat_id，防 Telegram 串台发错人。

---

## 8. 已拍板决策（2026-06-18）

| # | 问题 | 决策 | 影响 |
|---|---|---|---|
| ① | 默认渠道 | **飞书 + Telegram 都做，默认可切** | Telegram pusher 从 M3 提前到 M0 |
| ② | 硬崩溃（kill -9）也通知 | **一起做 watcher 兜底** | 并入方案二 watcher-daemon（M4），整体 effort 升 **L** |
| ③ | runner 后置回调（路径 B） | **M6 顺手做，默认关** | 避免和 hook 注册表互斥（P0 第 4 点） |
| ④ | 纳管入口 | **先只做 CLI**（`watch register`） | 菜单栏看用得顺手再加 |
| ⑤ | Stop hook 每轮 ping | **不做** | 只做 SessionEnd 完成通知，避免刷屏 |
| ⑥ | 企微出站 | **继续查并尝试支持** | 新增 M5 调研里程碑 |

---

*参考：Claude Code Hooks 官方文档 <https://docs.claude.com/en/docs/claude-code/hooks>。仓库内关键文件：`hub/app.py`、`core/runner.py`、`core/hub_client.py`、`core/config.py`、`feishu-claude/feishu_send.py`、`telegram/telegram_bot.py`、`wecom/wecom_ws_server.py`、`supervisor.py`、`ralph/smoke_test.py`。*
