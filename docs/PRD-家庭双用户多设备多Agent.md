# DK 家庭双用户、多设备、多 Agent

> 状态：Draft · 待实现  
> 创建：2026-07-22  
> 适用仓库：DK  
> 目标主机：一台常驻 Mac mini（Apple Silicon，16 GB 内存）

## 1. 一句话定义

让两位家庭成员分别从手机和电脑安全调用同一台 Mac mini 上的 AI 能力，同时保持各自的身份、会话、记忆、文件、权限、通知和费用归属互不串线；底层可按人选择 Claude Code、Codex、Hermes 或后续 Agent。

## 2. 背景

当前使用者与设备：

- A（主机所有者）：从自己的手机和电脑调用，主要做软件开发、代码维护、调研和自动化。
- B（家庭成员）：主要从自己的手机调用，处理与 A 不同的个人事务，未来可能使用 Hermes 等带长期记忆的 Agent。
- 两人共用一台常驻 Mac mini 作为执行主机，但不应共享同一份个人记忆或获得相同的文件权限。

DK 当前已有可复用能力：

- Telegram、飞书、企业微信渠道壳。
- 渠道级 fail-closed 白名单。
- Hub 统一入口与 `127.0.0.1` 本地绑定。
- 按 `channel:chat_id` 持久化 Claude 会话。
- 按 `channel:user` 创建工作目录。
- FIFO 等待队列与全局并发限制。
- Claude CLI / SDK 可切换执行引擎。
- launchd 常驻、supervisor 崩溃自愈、菜单栏控制面板。

但现有隔离仍是“路径约定”，不是完整的多租户边界：

- 同一个人从不同渠道进入时会被识别成不同人。
- 同一渠道的群聊和私聊以 `chat_id` 续接会话，身份、对话目标与执行主体没有完整拆开。
- 所有人共用同一个 Claude 登录、同一组全局工具和同一个 macOS 用户权限。
- 开放 Bash / Write / Edit 后，Agent 理论上可以越过自己的工作目录访问主机其他文件。
- 当前只支持一种 Claude 配置，不能按人路由 Codex、Claude、Hermes。
- 通知路由若从白名单反推目标，存在 A/B 串台泄露风险。

## 3. 产品目标

### 3.1 必须达成

1. A 在手机和电脑上是同一个逻辑身份，可连续同一话题。
2. B 是独立身份，默认看不到 A 的会话、记忆、文件、密钥和通知。
3. A/B 可分别绑定不同 Agent、模型提供方、权限档位和工作区。
4. 两人同时发任务时公平排队，不丢消息、不静默等待、不互相抢占会话。
5. 所有回复和完成通知严格返回原始请求者与原始会话目标。
6. 高风险操作执行前必须获得发起人的二次确认。
7. 管理员可以查看运行状态和用量，但默认看不到 B 的消息正文。
8. 单个用户、渠道或 Agent 故障不得拖垮另一个用户。

### 3.2 非目标

- 不把 DK 做成公网 SaaS。
- 不支持未知访客自助注册。
- 不把 `CLAUDE_WORK_DIR` 宣称为安全沙箱。
- 不允许两个人直接共享同一个个人产品账号密码。
- 不在 v1 做复杂组织、角色组、计费结算或多人协作文档。
- 不在 v1 自动让 Agent 之间读取对方完整记忆。
- 不在 v1 追求超过 2 个并发 Agent；16 GB 主机优先保证稳定。

## 4. 核心原则

### 4.1 人、设备、渠道、会话分层

以下概念必须独立建模，禁止继续混用一个字符串：

| 概念 | 含义 | 示例 |
|---|---|---|
| Person | 真实的人 | `a`、`b` |
| Identity | 某渠道上的账号身份 | `telegram:123456` |
| Endpoint | 回复发往哪里 | Telegram 私聊 chat ID、群 ID |
| Device | 可选的来源设备标签 | `a-phone`、`a-macbook` |
| Thread | 一个连续话题 | “MK v0.5 开发” |
| Agent Profile | 使用的 Agent、模型与记忆配置 | `a-dev-claude`、`b-personal-hermes` |
| Workspace | Agent 可操作的文件边界 | `~/AgentHomes/a/dev` |

### 4.2 默认隔离，显式共享

- A/B 默认零共享。
- 共享必须落到明确资源，例如一个仓库、一个只读资料目录或一个交换箱。
- 禁止用“共享整个 Home 目录”实现协作。
- 撤销共享后，新任务立即失去访问权；历史产物按数据策略处理。

### 4.3 发送者决定权限，端点只决定回信位置

- 权限依据 `person_id`，不能依据群聊 `chat_id`。
- 回复与通知依据请求时捕获的 `endpoint_id`，不能从 allowed users 猜测。
- 群聊中必须同时验证发送者白名单与触发方式。

## 5. 用户故事

### 5.1 A：跨设备开发

- A 在手机 Telegram 私聊 Bot A：“继续 MK 的上一个修复”。
- DK 将其路由到 A 的开发 Agent 与对应 thread。
- A 回到电脑，可通过同一 Telegram 账号继续对话；若从 DK 桌面控制台进入，也可显式选择同一个 thread。
- 任务完成后通知回到本次请求对应的 Telegram 私聊，而不是默认群。

### 5.2 B：独立个人助手

- B 在自己的手机私聊 Bot B。
- DK 将消息路由到 `b-personal-hermes`，只加载 B 的记忆和 Skills。
- B 无法通过提示词让 Agent 读取 A 的开发目录或密钥。
- B 可以建立自己的定时任务，结果只发给 B。

### 5.3 并发

- A 正在运行 8 分钟的代码任务时，B 发来请求。
- B 立即收到“已排队，第 1 位，预计等待约 X 分钟”。
- B 可以取消自己的排队任务，但不能取消 A 的任务。
- A 的任务完成后自动调度 B；通知不串台。

### 5.4 显式共享

- A 创建共享目录 `family-trip`，授权 A 可写、B 可写。
- 两人的 Agent 只能通过该共享目录交换结果。
- DK 审计记录“谁在何时通过哪个 Agent 修改了哪个共享资源”，不记录无关消息正文。

## 6. 产品形态

### 6.1 推荐入口

v1 推荐使用两个 Telegram Bot：

- Bot A：开发用途，仅绑定 A。
- Bot B：个人用途，仅绑定 B。

理由：名字、头像、命令、权限提示和通知天然分开，配置错误时爆炸半径更小。技术上可支持一个 Bot 绑定两人，但不作为默认 onboarding 路径。

### 6.2 A 的电脑入口

优先级：

1. Telegram Desktop：与手机天然使用同一 Telegram identity。
2. DK 菜单栏 App：管理员控制面，不默认作为聊天入口。
3. 本地 CLI：通过显式 `--person a --thread <id>` 进入，不以当前 macOS 用户自动猜身份。

### 6.3 B 的入口

- v1：Telegram 私聊 Bot B。
- later：Web / PWA 或其他渠道，但必须先完成稳定身份绑定。

## 7. 身份与绑定

### 7.1 Person

每个人拥有稳定内部 ID：

```text
person_id: a | b | UUID
display_name: Alice
role: owner | member
status: active | disabled
```

`owner` 仅代表可以管理 DK，不代表默认能读取 member 的消息正文或记忆。

### 7.2 Identity Binding

一位 Person 可绑定多个渠道身份：

```text
telegram:123456 -> person:a
local-cli:a-macbook -> person:a
telegram:987654 -> person:b
```

绑定流程必须：

1. 管理员在本机发起“添加成员”。
2. 系统生成一次性验证码，10 分钟失效。
3. 新用户从目标渠道发送验证码。
4. 本机显示渠道、昵称、不可变 sender ID，管理员确认。
5. 写入绑定并删除验证码。

禁止通过昵称、手机号显示名或消息内容自动绑定。

### 7.3 一个渠道身份只能属于一个 Person

- 重复绑定必须拒绝并给出明确错误。
- 迁移归属需要管理员本机确认，并使旧 session token 失效。
- 禁用 Person 后，其所有 identities 立即失效。

## 8. Agent Profile

### 8.1 数据结构

每个 Profile 至少包含：

```yaml
id: a-dev-claude
owner: a
adapter: claude-code       # claude-code | codex | hermes
credential_ref: claude-a
workspace_id: a-dev
permission_policy: developer-sandboxed
memory_scope: profile
max_concurrency: 1
timeout_sec: 900
```

### 8.2 建议默认配置

| 用户 | Profile | 用途 | 权限 |
|---|---|---|---|
| A | `a-dev-claude` | 复杂开发、代码修改 | 沙箱内读写与命令 |
| A | `a-review-codex` | 代码审查、第二意见 | 项目只读或 worktree 写入 |
| B | `b-personal-hermes` | 个人事务、长期记忆、定时任务 | B 工作区内有限工具 |

Profile 不等于模型。一个 Profile 可以切模型，但身份、记忆与权限边界不可随模型切换而消失。

### 8.3 Adapter 合约

DK Hub 不直接耦合具体 CLI。所有 adapter 实现统一接口：

```text
run(request, profile, thread, workspace) -> result
cancel(run_id) -> result
health(profile) -> status
```

统一结果至少包含：

- `run_id`
- `ok`
- `text`
- `provider_session_id`
- `usage`
- `error_code`
- `artifacts`

### 8.4 Hermes

- A/B 不得共用同一个 Hermes home。
- 每个 Hermes Profile 使用独立 `HERMES_HOME`、配置、API keys、memory、sessions、skills 和 gateway 状态。
- Hermes 的 profile 隔离不替代操作系统或沙箱隔离。
- Hermes 自我生成/更新 Skill 时，只能写入自己的 Profile；进入共享 Skill 库需要管理员审核。

## 9. 工作区与操作系统隔离

### 9.1 目标目录

逻辑示例：

```text
~/AgentHomes/a/private/
~/AgentHomes/a/dev/
~/AgentHomes/b/private/
~/AgentHomes/shared/<share-id>/
```

实际部署推荐使用两个 macOS 标准用户或专用服务用户，使 A/B 的私有目录由文件系统权限隔离。若 v1 暂时仍运行在同一 macOS 用户下，产品必须标注为“逻辑隔离”，且 B 不得启用不受控 Bash。

### 9.2 权限档位

| 档位 | 能力 | 默认对象 |
|---|---|---|
| Read-only | 读白名单目录、搜索、总结 | 新成员 |
| Personal limited | B 工作区内读写、无任意 shell | B |
| Developer sandboxed | 指定仓库内读写、测试、构建 | A |
| Host admin | 主机级维护 | 仅 A，本机确认 |

“Host admin”不得从聊天渠道直接常开。每次进入应有时效授权，例如 15 分钟后自动降级。

### 9.3 路径检查

- 所有输入路径先 canonicalize，拒绝 `..`、符号链接逃逸和挂载点越界。
- 附件保存到请求者自己的 inbox。
- 共享路径必须通过 `share_id` 查授权，不能接受用户直接声明“这是共享目录”。
- Agent 产物默认进入 Profile 的 outputs，不直接覆盖来源文件，开发 Profile 除外。

## 10. 凭证与模型账号

### 10.1 原则

- 不在 Bot 消息、配置 UI、日志或 SQLite 中存明文密钥。
- 使用 macOS Keychain 或权限为 `0600` 的独立 secrets 文件。
- `credential_ref` 只引用凭证，不包含凭证值。
- A/B 使用不同 provider credential；公共 API 组织也应使用独立 project key 和预算。
- 禁止把个人 Claude/Codex OAuth token 复制给另一人的 Profile。

### 10.2 费用策略

每个 Profile 配置：

- 每日软预算。
- 每月硬预算。
- 单次最大 token / 时长。
- 预算达到 80% 时通知本人；达到 100% 后拒绝新任务。
- 管理员只看到金额与用量汇总，默认不看 prompt 正文。

订阅 CLI 若无法提供准确 token 成本，至少记录调用次数、运行时长和限流错误，明确标注为估算。

## 11. 会话与记忆

### 11.1 Thread Owner Key

现有 `channel:chat_id` 应迁移为：

```text
person_id + profile_id + thread_id
```

渠道 endpoint 仅作为 thread 的一个入口。这样 A 的手机和电脑可以显式进入同一 thread，B 永远不会因 chat ID 碰撞续接 A 的 session。

### 11.2 Thread 操作

v1 命令：

- `/new [名称]`：新建话题。
- `/threads`：列出自己的最近话题。
- `/use <编号>`：切换话题。
- `/reset`：清空当前 Provider session，但不删除审计记录。
- `/agent`：查看当前 Profile。
- `/agent <name>`：切换到本人被授权的 Profile。
- `/cancel`：取消本人当前运行或排队任务。

### 11.3 记忆边界

- 会话记忆默认 `thread` scope。
- 长期记忆默认 `profile` scope。
- Person 可删除自己的 thread、记忆和附件。
- A 作为主机管理员执行备份时可处理密文文件，但产品 UI 不提供直接浏览 B 记忆正文的入口。
- 从一个 Profile 向另一个 Profile 搬运记忆必须显式导出/导入，并展示预览。

## 12. 调度与并发

### 12.1 主机预算

M4 / 16 GB 默认：

- 全局 active runs：1。
- 可配置实验值：2，但必须经过内存压力验证。
- 每位用户最多 1 个 active run。
- 每位用户最多 5 个 queued runs。

### 12.2 公平性

- 使用按 Person 轮转的公平队列，而不是单纯全局 FIFO；防止一人一次塞满队列。
- 同一人的任务保持 FIFO。
- interactive 优先于 scheduled，但 scheduled 不得无限饿死。
- 管理任务不可悄悄插队；紧急插队需本机确认并通知受影响用户。

### 12.3 排队反馈

入队后立即返回：

- 已入队。
- 当前位次。
- 粗略预计等待时间。
- `/cancel` 用法。

状态变化只在“开始、长时间延迟、完成、失败”时通知，避免刷屏。

## 13. 高风险操作确认

以下动作无论 Agent 如何判断都需要用户确认：

- 删除或永久覆盖文件。
- 向外部人员发送消息、邮件或发布内容。
- 购买、转账、订阅或修改付款方式。
- 修改账号权限、密钥、Bot 配置。
- 安装系统软件、修改启动项或网络暴露面。
- 访问另一个 Person 的共享边界之外的数据。

确认 token 必须绑定：`person_id + run_id + action_hash + expiry`。B 不能确认 A 的动作，旧确认不能复用到新命令。

## 14. 通知防串台

每个 run 在入口冻结以下路由信息：

```text
requester_person_id
source_identity_id
reply_endpoint_id
thread_id
profile_id
```

完成通知只能使用冻结的 `reply_endpoint_id`，禁止：

- 从 allowed users 取第一个人。
- 从“默认 Telegram chat”猜目标。
- 以最近活跃用户作为目标。
- 将群 ID 和 sender ID 混用。

失败时宁可不发并进入 dead-letter，也不能尝试发送给另一个候选目标。

## 15. 隐私与数据

### 15.1 默认记录

允许记录：

- 时间、person/profile/thread/run ID。
- 渠道、状态、耗时、错误码、估算用量。
- 文件操作的路径摘要与动作类型。

默认不记录：

- 消息正文预览。
- 模型完整回复。
- 附件内容。
- 密钥与环境变量。

诊断模式如需正文必须由对应 Person 临时开启，并显示到期时间。

### 15.2 保留期

- 运行元数据：30 天。
- 普通日志：7 天，自动轮转。
- dead-letter：7 天。
- Thread 与长期记忆：直到用户删除。
- 一次性绑定码和确认 token：过期立即清理。

“清除数据”走废纸篓或加密归档，提供可恢复窗口；“立即永久删除”需二次确认。

## 16. 管理界面

### 16.1 People

- A/B 状态。
- 已绑定 identities。
- 可用 Profiles。
- 权限档位。
- 用量与预算。
- 禁用、重新绑定、导出/清理数据。

### 16.2 Agents

- Adapter 与健康状态。
- Credential 是否可用，仅显示引用名。
- 工作区与沙箱状态。
- 当前 active run、队列长度。
- 最近错误码。

### 16.3 Queue

- 只显示任务所有人、Profile、开始/等待时长和状态。
- 管理员默认看不到 B 的 prompt。
- A 可取消系统卡死任务；取消 B 的正常任务前需确认并通知 B。

### 16.4 安全状态

必须明确展示：

- `OS isolated` / `Logical isolation only`。
- 哪个 Profile 拥有 shell。
- 哪些目录正在共享。
- 是否存在过期或失效凭证。
- 是否有公网监听端口。

## 17. 配置草案

以下仅表达产品模型，最终格式由实现阶段决定：

```toml
[runtime]
max_concurrency = 1
queue_per_person = 5

[[people]]
id = "a"
display_name = "A"
role = "owner"

[[people.identities]]
channel = "telegram"
sender_id = "123456"

[[people]]
id = "b"
display_name = "B"
role = "member"

[[people.identities]]
channel = "telegram"
sender_id = "987654"

[[profiles]]
id = "a-dev-claude"
owner = "a"
adapter = "claude-code"
credential_ref = "claude-a"
workspace = "a-dev"
policy = "developer-sandboxed"

[[profiles]]
id = "b-personal-hermes"
owner = "b"
adapter = "hermes"
credential_ref = "hermes-b"
workspace = "b-private"
policy = "personal-limited"
```

真实 sender ID、chat ID 和 secrets 不应提交进 Git。

## 18. 数据模型草案

建议实体：

- `people`
- `identities`
- `endpoints`
- `profiles`
- `workspaces`
- `workspace_grants`
- `threads`
- `provider_sessions`
- `runs`
- `queue_items`
- `notification_routes`
- `consent_tokens`
- `usage_daily`
- `audit_events`

关键唯一约束：

- `(channel, sender_id)` 唯一。
- `profile.owner_person_id` 必须存在。
- `thread(person_id, profile_id, thread_id)` 唯一。
- `run.reply_endpoint_id` 创建后不可被普通更新覆盖。
- grant 必须显式指向 person/profile 与 workspace。

## 19. 迁移方案

### M0：冻结与备份

- 记录当前配置、allowlist、threads DB、work dirs 和通知路由。
- 不自动把未知历史数据归给 A。

### M1：身份层

- 新增 Person / Identity / Endpoint。
- 将当前管理员已验证的渠道身份映射为 A。
- `/chat` 必须先完成 identity resolve，再进入队列。
- 未绑定用户 fail-closed。

### M2：Profile 与 Thread

- 引入 Agent Profile 与 adapter 合约。
- 旧 Claude 配置迁为 `a-default-claude`。
- 旧 `channel:chat_id` thread 仅在映射明确时归入 A，否则留在只读 legacy 区。

### M3：B onboarding

- 创建 B Person、Bot B、独立凭证和工作区。
- 先以 Read-only/Profile 健康检查上线。
- 完成隔离测试后再开放个人写入能力。

### M4：Hermes

- 建立独立 Hermes home 与 gateway。
- 接入 adapter health/run/cancel。
- 验证记忆、Skills、定时任务和通知均不跨 Profile。

### M5：OS 隔离

- 将 B Profile 迁入独立 macOS 服务用户或等价强沙箱。
- 菜单栏安全状态从 `Logical isolation only` 变为 `OS isolated`。

## 20. 分期范围

### v1：可安全给两个人用

- Person / Identity / Endpoint。
- 两个 Telegram Bot。
- A/B 独立工作区和 threads。
- Claude adapter；Hermes 可先作为实验 adapter。
- 每人权限策略。
- 公平队列、取消、进度反馈。
- 冻结通知路由。
- 高风险确认。
- 管理界面 People / Queue / Security 最小版。
- 逻辑隔离必须显著标注。

### v1.1：多 Agent

- Codex adapter。
- Hermes 完整 Profile 接入。
- `/agent` 切换。
- Profile 级预算和健康检查。
- 定时任务进入统一调度。

### v2：强隔离与共享

- 独立 macOS 用户或强沙箱执行器。
- Shared workspace grants。
- 加密备份与用户自助导出/删除。
- 更完整的审计和 dead-letter 管理。

## 21. 验收标准

### 21.1 身份

- A 从手机与电脑的同一 Telegram 账号进入，解析为同一 Person。
- B 的 sender ID 无法访问 A 的 Profile。
- 昵称变化不影响绑定。
- 伪造 `person_id` 字段不能越权。

### 21.2 会话

- A/B 发送相同文本也得到不同 thread/provider session。
- Hub 重启后两人的 thread 分别续接。
- A 切 Agent 不会把 Claude session 当作 Hermes session 恢复。
- 删除 B thread 不影响 A。

### 21.3 文件

- B 读取 A private workspace 被拒绝。
- `..`、symlink、绝对路径与附件路径均不能逃逸。
- 显式共享目录可按 grant 正常读写。
- 撤销 grant 后下一请求立即失败。

### 21.4 通知

- A/B 同时运行 100 轮模拟任务，回复与完成通知零串台。
- 群聊任务回原群，私聊任务回原私聊。
- endpoint 失效时进入 dead-letter，不回退到另一个用户。

### 21.5 队列

- A 连发 5 条后 B 发 1 条，B 不会等待 A 的 5 条全部完成。
- 用户只能取消自己的任务。
- Hub 重启后 queued 状态要么恢复，要么向原请求者明确报告已取消，不能静默丢失。
- 16 GB 主机压力测试无 swap 风暴和 OOM。

### 21.6 凭证

- 日志、数据库、错误回复中搜索不到 token/key 明文。
- B Profile 无法读取 A credential。
- 凭证轮换无需删除用户历史 thread。

### 21.7 风险确认

- A 的确认 token 不能批准 B 的动作，反之亦然。
- token 超时、action hash 改变或 run 改变后确认失效。
- 高风险动作在无确认时绝不执行。

## 22. 上线门槛

以下任一未满足，不向 B 开放写权限：

- 身份绑定 fail-closed 未完成。
- 通知路由仍可能从 allowlist 反推。
- B Profile 可访问 A 私有目录。
- 凭证仍在通用环境变量中对所有 adapter 可见。
- 缺少排队与取消反馈。
- 安全界面没有标注当前是逻辑隔离还是 OS 隔离。
- A/B 串台自动化测试未通过。

## 23. 成功指标

首月关注：

- 身份或通知串台：0。
- 未授权文件访问成功：0。
- 静默丢任务：0。
- B 无需接触 Terminal 即可完成首次绑定与首个任务。
- 两人各自连续使用 7 天，thread/记忆无交叉。
- P95 入队反馈小于 2 秒。
- Agent 不可用时 10 秒内给出明确状态，而非无限“思考中”。

## 24. 开放决策

实现前需最终拍板：

1. B 的 v1 Agent 是 Claude API 还是直接上 Hermes。
2. v1 是否立即使用独立 macOS 用户；推荐是，但工程成本高于逻辑隔离。
3. A 的 Codex/Claude 采用个人 CLI、Team seat 还是独立 API project。
4. 两个 Bot 是否都用 Telegram；若 B 更习惯其他渠道，需要重新验证 sender/endpoint 语义。
5. 定时任务是否允许在无人在线时执行写操作；建议 v1 只允许低风险任务。
6. 共享目录是否需要版本控制；代码类共享建议 Git，普通资料可用显式 exchange 目录。

## 25. 实现时首先阅读

- `README.md`：当前产品与架构。
- `core/security.py`：fail-closed allowlist。
- `hub/app.py`：统一入口、队列、工作目录和通知端点。
- `core/threads.py`：现有持久化会话键。
- `core/runner.py`：Claude adapter 的事实原型。
- `docs/会话上下文架构.md`：thread/session 决策。
- `docs/数据策略.md`：本地数据与清理原则。
- `docs/notify-on-session-complete-proposal.md`：通知串台与 session 路由风险。
- `SANDBOX.md`：工作目录不等于沙箱的安全前提。

