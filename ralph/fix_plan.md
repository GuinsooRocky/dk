# fix_plan.md — DK 自主 loop 任务清单（批次：语音自动下载 + 出站完成通知）

> Ralph 每轮读这个文件，挑**「待办」里最上面一个 `- [ ]`** 的任务，**只做那一个**，
> 跑 `python ralph/smoke_test.py`，全绿才 commit + 把该行打勾 `- [x]`，然后退出。下一轮全新 context 接着干。
> 标记：`- [ ]` 待办 · `- [x]` 已完成 · `- [⚠]` 卡住跳过（见行下原因；loop 不重试它，继续做别的，最后留给人）。
> 「待办」里再没有 `- [ ]` → PROMPT 打印 `ALL DONE` 收工（`- [⚠]` 不算待办）。

## 验收命令（back-pressure）
- 唯一硬判据：`python ralph/smoke_test.py` 全绿（结构契约：编译 / 渠道 parity / 懒导入 / hub endpoint / swift build）。
- **每个任务做完，把它的结构不变量补进 `ralph/smoke_test.py`**（feature 先做、check 后加，同一轮内 → smoke 始终绿，loop 自己长出 back-pressure）。
- 运行时验证（curl /notify、真发通知、真下模型）**不在 loop 内做**（headless 起不了 hub）——见文末「跑完人工验收」，用户最后一次性验。

## 规矩（铁律，违反会出事）
- **只在 `ralph/auto` 分支 commit**（loop.sh 已自动切），绝不碰 main/develop/feature 分支。
- scoped commit：逐个 `git add <本轮碰的文件>` + `ralph/fix_plan.md`，**绝不 `git add -A` / `git add .`**。
- 不动 `.env` / 真实凭证；验证打 mock / 测试端点，绝不发真实用户。
- 删文件走 `~/.Trash`（不 rm）；退役代码只加注释标记不删。
- **不确定就停跳过**：把该任务 `- [ ]` 改成 `- [⚠]`，行下加一句 `⚠ 卡住:<原因>`，`git checkout -- .` 回滚本轮其它改动（只保留 fix_plan 这处标记并提交），退出。重复 ≠ 进步。

## 上下文（每轮先读）
- 本文件 + `docs/产品化战略-06.17.md`（§9 路线图 / §12 落地进度）建立全局。
- 做 **N-*（出站通知）** 任务时**必读** `docs/notify-on-session-complete-proposal.md`（已拍板方案一 hook-push；§3.2 架构图 / §5 安全 P0/P1 / §6 里程碑 / §8 决策）。
- 关键既有文件：`hub/app.py`（/chat /pending 的 FastAPI+Pydantic 范式）、`core/config.py`（runtime_dir）、`core/hub_client.py`（httpx trust_env=False 躲代理）、`feishu-claude/feishu_send.py`（--raw 独立发送器）、`supervisor.py`（_venv_py 按渠道跑 venv / CHATCC_SUPERVISED=1）。

---

## 待办

- [x] **V1 · 语音模型缺失时自动下载**（`core/transcribe/sensevoice.py`）
  - 做什么：现在模型缺失直接 `raise FileNotFoundError`（sensevoice.py:28）。改成「**有就用、缺才下**」：按顺序找，全找不到才从 HuggingFace 懒下载一次。本机有 MK 模型 → 永不触发下载。
  - 怎么做：① 新增 `_resolve_dir()` 查找顺序，命中即用不下载：`SENSEVOICE_DIR` 环境变量 → MK 目录 `~/.mk/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17` → DK 目录 `~/.dk/models/<同名>`。② 三处都缺 `model.int8.onnx`/`tokens.txt` → 新增 `_ensure_model()` 从 HuggingFace 下载到 **DK 目录**（不写 MK 地盘，DK/MK 解耦）；用 stdlib `urllib`，**不新增重依赖**；失败给清晰报错（保留现有手动设 SENSEVOICE_DIR 兜底文案）。③ `_recognizer()` 缺模型分支从 raise 改成「先 `_ensure_model()` 再加载」。④ 删源码里「分发到没 MK… 或后续加自动下载」那句注释（已兑现）。
  - 验收：smoke 绿 + 在 `smoke_test.py` 加 `check_voice_autodownload`：断言 sensevoice.py 含 `_ensure_model`（或等价下载函数）且 `_recognizer` 缺模型分支不再是裸 raise。**不真跑下载**（228MB，留人工验收）。

- [x] **N-M0 · 出站通知链路打通**（/notify + 飞书/TG 推送 + 配置）
  - 做什么：补 hub→渠道反向通道骨架，让一条 `POST /notify` 扇出到飞书和 Telegram（提案 §6 M0，决策①两渠道默认可切）。
  - 怎么做（仿 hub/app.py 现有范式，逐字复用优先）：① 加 `class NotifyIn(BaseModel){session_id,status,summary,cwd,duration_sec,turns}` + `@app.post("/notify")`（仿 /pending；鉴权放下一条 N-M2）。② 飞书 pusher：子进程跑 `feishu_send.py --raw '<text>'`（逐字复用），按 `supervisor._venv_py` 用飞书 venv；webhook 没配 feishu_send.py exit 1 → hub 把 `ok:false` 暴露，别挂住。③ Telegram pusher：hub 内 helper，`httpx(trust_env=False)` POST `api.telegram.org/bot<token>/sendMessage`，token 取 `[telegram].token`；chat_id **只用注册时存的真实 target，绝不从 allowed_users 反推**（§5 P1 串台）。④ `config.toml` 加 `[notify]` 默认渠道键 + `/config/notify` 端点（仿 /config/channel）。⑤ 路由存储 `notify_routes.json` 放 `config.runtime_dir()`，行 `{session_id:{channel,target,registered_at}}`。
  - 验收：smoke 绿 + 加 `check_notify_endpoint`：断言 hub/app.py 含 `/notify` 路由 + `NotifyIn` + `/config/notify`。

- [x] **N-M2 · /notify 鉴权**（P1 不可省，趁 hook 上线前先做）
  - 做什么：给 /notify 加共享密钥，堵「未鉴权开放转发器」（§5 P1：本机任意进程/浏览器都够得着 127.0.0.1）。
  - 怎么做：① hub 启动时若无则生成 token，写 `config.runtime_dir()/.notify_token`（0600）。② /notify 校验 `X-Notify-Token` 头，不匹配 403。③ 按 session_id 简单限流。
  - 验收：smoke 绿 + `check_notify_endpoint` 扩断言 /notify 含 token/403 校验 + `.notify_token` 0600。

- [x] **N-M1 · 全局 SessionEnd hook + 注册 CLI**
  - 做什么：让任意本机 Claude session 跑完触发通知（功能决定性差异点；提案 §6 M1，决策④先只做 CLI）。
  - 怎么做：① `hub/notify_hook.py`（~50 行）：读 stdin JSON → **P0 缓解先行**（cwd 在 CFG.work_dir/`~/claude-*-workdir` 树下 → 立刻 exit 0；带 `CHATCC_SUPERVISED=1` → exit 0，双保险排除 bot 自起进程）→ 查 notify_routes.json 没注册 → exit 0 → 命中才带 `X-Notify-Token` POST /notify。**永远 exit 0**，httpx `trust_env=False`。② `hub/watch.py` register/unregister：**内容指纹认 session_id，绝不用 mtime**（memory 铁律，mtime 会抓到并发的 bot 自己会话）；register 时存真实 target（TG 的 effective_chat.id）。③ 把 SessionEnd hook 装进 `~/.claude/settings.json` **不在 loop 内自动改**（动全局配置该归 harness）——写进文末人工验收；loop 只把 notify_hook.py 备好。
  - 验收：smoke 绿 + 加 `check_notify_hook`：断言 notify_hook.py 含 work_dir 排除 + CHATCC_SUPERVISED 检查 + 始终 exit 0；watch.py 含 register/unregister 且**不含**按 mtime 排序认 session（grep 反向断言）。

- [x] **N-M3 · transcript 解析 + 容错**
  - 做什么：从 transcript 解析 状态/摘要/轮数/用时，容忍写一半（提案 §6 M3 / §5 P2）。
  - 怎么做：容忍残读的 JSONL 解析器（被 notify_hook.py 调用）；解析不出 → 降级文案「completed（摘要不可用）」；`end_reason→ok/error` 启发式并标注是启发式。
  - 验收：smoke 绿 + `check_notify_hook` 扩断言解析器存在且有残读降级分支（含降级文案常量）。

- [x] **N-M6 · 收尾**（清扫 + smoke 纳入 + runner 回调）
  - 做什么：提案 §6 M6 收尾三件。
  - 怎么做：① notify_routes.json >24h 残留行清扫（hub 启动或 /notify 时顺扫）。② **把 `/notify` 加进 `ralph/smoke_test.py` 的 `REQUIRED_ENDPOINTS`**（此时已实现，加了不红）。③ 路径 B（决策③）：`core/runner.py` `_run_cli` 返回后回调 /notify，**默认关**（config 开关），避免和 hook 注册表打架（§5 P0 第4点 来源互斥）。
  - 验收：smoke 绿（REQUIRED_ENDPOINTS 已含 /notify）+ runner 回调有「默认关」开关守卫。

- [⚠] **N-M4 · watcher 崩溃兜底**（L，全批最易写坏，谨慎）
  - ⚠ 卡住:M4 误判判据无法机械验收 —— 从 live-append JSONL 在有限时间内无法把「session 真崩了 vs 只是空闲等下一轮」做成可机械断言的不变量（任何静默 debounce 必对空闲会话假阳性刷屏，spec 已预警「空闲间隔会误触发」）。唯一能真消歧的进程级存活信号（session→pid）Claude Code 不暴露，watcher 拿不到；`check_notify_watcher` 只能验结构、验不了「不刷屏」这个真正确性。按任务自带逃生指令 + PROMPT 铁律跳过，留人工：要么接 watchdog 进程级存活信号再做，要么放弃 M4 只靠 SessionEnd（崩溃漏通知可接受）。
  - 做什么：堵 `kill -9`/硬崩溃不触发 SessionEnd 的缺口（提案 §6 M4，决策②）。
  - 怎么做：`supervisor.py` 托管 watcher 进程 tail `~/.claude/projects/**/*.jsonl`；内容指纹 + per-file offset 游标 + debounce；**与 SessionEnd hook 去重**（同 session_id 只发一次）。
  - ⚠ 风险：从 live-append JSONL 推断「整个 session 完了 vs 这轮完了」天生易假阳性。**若一轮内无法把「turn-end vs session-end 误判」做成可机械断言的不变量，就把本任务改 `- [⚠]` 记 `⚠ 卡住:M4 误判判据无法机械验收` 跳过**，别硬写会刷屏的 watcher。
  - 验收：smoke 绿 + `check_notify_watcher`：断言 watcher 模块存在 + offset 游标 + 与 hook 的 session_id 去重。

- [x] **N-M5 · 企微出站调研 + 支持**（调研型，很可能无解→诚实报错也算完成）
  - 📌 调研结论：`wecom_aibot_sdk` **确有** by-chatid 主动发送 API —— `WSClient.send_message(chatid, body)`，docstring 明写「Proactively send message (no callback frame needed)」（body 限 markdown/template_card）。**但**它经渠道进程持有的那条已认证 WS 连接发，**hub 进程够不着**；hub 另开同 bot_id 的第二条 WS 会和在线渠道抢连接（很可能把渠道踢下线）。故当前落**诚实报错改投飞书/TG**（dispatch `channel == "wecom"` 分支），不在 hub fabricate 竞争连接。未来要真支持：经 wecom 渠道进程 IPC 中转 send_message，别在 hub 开第二条 WS。
  - 做什么：查企微 SDK 有没有 by-chatid 主动发送 API（提案 §6 M5，决策⑥）。
  - 怎么做：调研 `wecom_aibot_sdk` 是否有脱离 frame 的 by-chatid 发送（现 `wecom_ws_server.py:145` reply 是 frame-bound）。**有** → 做 wecom pusher + 注册存 chatid；**无（很可能）** → /notify 对企微**明确报错并提示改投飞书/TG**（不编造 SDK 调用）。两条都算完成。调研结论写一行存到本任务行下。
  - 验收：smoke 绿 + /notify 对 channel=wecom 有明确分支（pusher 或诚实报错改投）。

### 设计批次（§9 later + §4 向导，2026-06-21 补设计；决策默认见各任务，可改）

- [x] **T1 · trust_tier 渠道信任分级字段**
  - 做什么：给渠道加 `trust_tier`（safe / experimental），UI 按层分组；为第三方插件生态预留（战略 §6.3）。v1 现有三渠道全 = safe，不发任何 experimental。
  - 怎么做：① `macapp/.../Models.swift` 的 `ChannelMeta` 加 `trustTier: String`（默认 "safe"），`KNOWN_CHANNELS` 三条都填 "safe"。② `ChannelsView` 若存在 experimental 渠道则分组到「实验性」区带警示副标，无则不显（现状即不显）。③ config 渠道段可选 `trust_tier`（缺省 safe），hub 透传。
  - 验收：smoke 绿 + 加 `check_trust_tier`：断言 `ChannelMeta` 含 `trustTier` 且 `KNOWN_CHANNELS` 每条有值。
  - 决策默认：v1 全 safe（无 experimental 渠道发货）。

- [x] **P1 · 渠道健康探针（proactive auth 有效性）**
  - 做什么：主动定期验证各渠道鉴权是否还有效，把「进程活着但认证失效」从「连得上」里分出来（战略 later）。
  - 怎么做：① hub 起后台周期探针（默认 5min）：feishu = `get_tenant_token()` 拿到非空 token（feishu_common.py:56）；telegram = httpx(trust_env=False) GET `getMe` 200；wecom = 复用 client `is_authenticated`（wecom_ws_server.py:184，让壳上报）。② 结果存 hub `_HEALTH` dict，经 `/supervisor` 每行加 `auth_ok` 字段。③ `macapp` Channels 把 auth_ok=false 显成独立态「认证失效」（区别于进程 down），提示去 Settings 重填凭证。
  - 验收：smoke 绿 + 加 `check_health_probe`：断言 hub 有周期探针 + `/supervisor` 输出含 auth_ok + 三渠道各有探针分支。
  - 决策默认：探针间隔 5min；wecom 走 is_authenticated 上报（无独立 API）。

- [x] **R1 · 出站限速器（token-bucket）**
  - 做什么：给所有出站发送加限速，防刷屏/撞平台频控。战略 §12 说当前规模用不上——按你要求做，默认宽松不挡正常用量。
  - 怎么做：① 新增 `core/ratelimit.py`：per-channel token-bucket，`try_acquire(channel)→bool`，超限排队不静默吞。② 应用到出站点：各渠道分块回复循环（wecom_ws_server.py:122 等）+ N-M0 的飞书/TG notify pusher。
  - 验收：smoke 绿 + 加 `check_ratelimit`：断言 `core/ratelimit.py` 存在含 token-bucket + 被 notify pusher 和分块回复引用。
  - 决策默认：20 条/分钟/渠道。

- [x] **Q1 · per-guest 公平队列（"你排第 N"）**
  - 📌 落地说明：请求/响应模型下「回你排第N」+「答案稍后送达」二者只能取一（决策④不主动推送=无回推通道）。故落「持连接 FIFO 排队」：占线请求按序等串行闸、轮到再返回真答案（替代旧的直接拒）；位次已算+记日志（`chat 排队第N位轮到`），但不单独推给用户（持连接不能中途插话）。深 5/超时 10min/满则真 busy 均按决策默认。
  - 做什么：把现在「忙→回稍后再发」(runner.py Slots 非阻塞 acquire 拒绝) 升级成排队：占线时入队、回「你排第 N」、按序处理，concurrency 仍 1。
  - 怎么做：① hub `/chat`：SLOTS.acquire() 失败时不直接回 busy，改入 FIFO 队列（deque + 锁），回复带位次「你排第 N，前面还有 M 个」。② 单飞槽释放后按 FIFO 取下一个跑。③ 队列上限满了才回真 busy；入队项超时丢弃并告知。④ **不动 runner Slots 的 concurrency=1 语义**，只在 hub 层加排队。
  - 验收：smoke 绿 + 加 `check_fair_queue`：断言 hub 有队列结构 + 位次计算 + FIFO 取出；runner Slots 单飞语义未变。
  - 决策默认：队列深 5、入队超时 10min、不主动「轮到你了」推送（入队给位次即可）。

- [ ] **W1 · §4 向导 骨架 + Screen0 资格预检 + Step1 Claude 三态门**
  - 做什么：把静态 `OnboardingView` 升级成多步交互向导（战略 §4.1）。本任务建状态机骨架 + 前两屏。
  - 怎么做：① 新建向导状态机（`enum WizardStep`：eligibility/claude/channel/connect/perms/runmode/done）+ 容器视图包裹/替换现有 `OnboardingView`（旧静态内容退役只加注释不删）。② Screen0 资格预检：明示「需付费 Claude 订阅 + 常醒 Mac」，给「有/帮我开通」不卡转圈。③ Step1：复用 `ClaudeCheck.swift` 检装没装/登没登，未过不放行，每探针 60s 超时 + 兜底文案。
  - 验收：swift build 过 + 加 `check_wizard_skeleton`：断言存在 WizardStep 状态机 + 复用 ClaudeCheck。**视觉/流程对不对留 visual-qa 人工收尾**（见文末）。

- [ ] **W2 · 向导 Step2 渠道选择 + Step3 连接 sheet（实时抓 ID）**
  - 做什么：§4.1 Step2/3——选渠道 + 逐渠道连接（粘 token + 实时抓 ID 加白名单）。
  - 怎么做：① Step2：默认只给 Telegram（~60s 可过），飞书/企微藏「我已有开发者账号」勾选后（opt-in，工作路径）。② Step3：token 表单粘贴写 config/.env；**实时抓 ID** 复用后端 `/pending`+`/allowlist`（已通）——提示「现在从手机发一条」，把捕获的 sender 渲染成「把【你】加白名单」一点即加（替代手 grep 回填）。
  - 验收：swift build 过 + `check_wizard_skeleton` 扩断言 Step2/3 存在且 Step3 调 /pending+/allowlist。视觉留 visual-qa。
  - 决策默认：默认渠道 = Telegram-only，飞书/企微 opt-in（战略 §4.1）。

- [ ] **W3 · 向导 Step4 权限 + Step5 运行模式 + 收尾**
  - 做什么：§4.1 Step4/5——权限三档+沙箱 / 开机自启+笔记本警告，跑完进主窗。
  - 怎么做：① Step4：三档权限预设复用 `SettingsView` ToolTier；读+写/全权必须沙箱验证才可选（GUARD-3 判据已有），加人措辞每次显示。② Step5：开机自启默认 ON 复用 `Autostart.swift`；笔记本检测警告「合盖即离线」复用 `SleepGuard/DisableSleep`。③ Done → 进 Channels/Insights/Settings 主窗。
  - 验收：swift build 过 + `check_wizard_skeleton` 扩断言 Step4 接 ToolTier、Step5 接 Autostart。视觉留 visual-qa。

---

## 跑完人工验收（loop 不做，用户最后一次性验，纯文字非任务）
- §4 向导：跑完用 visual-qa 四象限走查向导每一屏（PC/mobile × dark/light），确认流程顺、组件渲染对（loop 只保证编译过 + 结构在，看不了渲染）。
- 语音：临时把 `SENSEVOICE_DIR` 指向空目录首用语音，确认会下载并转写；本机有 MK 时确认**不**下载。
- 出站通知：用 update-config skill 把 SessionEnd hook 装进 `~/.claude/settings.json`；`watch register` 一个真实 session；跑完确认飞书/TG 收到，且**群里注册必投回群、不串私聊**。
- curl 手测 /notify（带/不带 X-Notify-Token 验 403）。
- 确认 bot 自己的 hub-workdir session 跑完**不会**触发自通知（P0）。

## 已完成历史批次（归档，详情见 git log）
v1 后端 + macapp（M1–M6）+ W1–W4 + 收尾批次（GUARD/GUEST/BET/无障碍）+ A1/B4/B5/B6，全部已交付。
