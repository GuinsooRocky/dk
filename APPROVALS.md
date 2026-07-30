# 审批链路（危险工具走 Telegram 按钮）

让 bot 能真干活（跑命令、改文件），但每个危险动作执行前先问你一句。

```
claude（bot 起的）
  └─ approvals/mcp_server.py（stdio 子进程）
        └─ POST /approval/request ─→ Hub ─→ 冻结的那个 chat 收到按钮
                                      ↑                    │
        ←── allow / deny ─────────────┴─ POST /approval/answer
```

开关：`hub/.env` 的 `DK_APPROVALS=1`（**默认关**）。

| | 关（默认） | 开 |
|---|---|---|
| 危险工具 | 直接不给（`--disallowedTools`） | 给，但每次问 |
| 姿态 | fail-closed，干不了活 | fail-closed，你不点就不动 |

## 三条实测出来的硬约束

这三条都是踩出来的，改配置前先看：

**1. `--allowedTools` 不限权。** 它是"免提示放行清单"，不是能力白名单。从里面剥掉 Bash，
claude 照样能用 Bash（实测 `--allowedTools "Read,Glob,Grep,WebFetch"` 跑 `echo` 成功、
`permission_denials` 为空）。真要摘工具只能用 `--disallowedTools`。
→ 老 GUARD-3 靠"从 allowedTools 剥"来限权，**一直是无效的**。

**2. 按名字 deny 是打地鼠。** `--disallowedTools Bash` 之后 claude 改用 `Monitor` 工具跑了
同一条命令（原话：*this session has no Bash tool exposed, so I ran it via the Monitor tool,
which executes commands in the same shell environment*）。所以危险清单按**能力**列全：
能跑命令的（Bash / BashOutput / KillShell / Monitor）、能派子 agent 的（Task / Agent，
子 agent 自带 Bash）、能改文件的（Write / Edit / MultiEdit / NotebookEdit）。
→ 名单会随 claude 升级长出新成员，所以 `scripts/approval-e2e.sh` 验的是**行为**不是名单。

**3. 两个配置会把审批整条旁路掉：**
- `sandbox.autoAllowBashIfSandboxed: true` —— 字面意思就是"在沙箱里就免提示跑"
- `--permission-mode acceptEdits` —— 自动接受 Write/Edit

两者任一打开，`permission-prompt-tool` **压根不会被调用**，命令直接执行。所以
`sandbox-settings.json` 里它是 `false`，`_permission_mode()` 开审批时强制回 `default`。

## 怎么验

```bash
bash scripts/approval-e2e.sh      # 三个用例，退出码 0 才算行
```

- A 批准 → 命令**执行了**（闸不能把正常活堵死）
- B 拒绝 → 命令**没执行**（闸真挡得住）
- C 没开审批 → 命令**没执行**（fail-closed，不能因为没配审批就无声放行）

C 是最容易退化的一条：任何"沙箱配上了就放开工具"的改法都会把它变成 fail-open。
**沙箱管的是"跑起来能碰到什么"，管不了"该不该跑"。**

## 防串台（PRD §14 / §13）

- 请求进 Hub 那一刻 `open_run()` 冻结 `{channel, chat_id, user}`，审批只推给这个 endpoint。
  不从白名单取第一个人、不拿"最近活跃的人"猜。
- MCP server 只拿到 `run_id`，伪造不出别人的 chat_id —— 串台在结构上不成立。
- 点击带的是 Telegram 真实 `from.id`，跟冻结的请求者比；不是本人 → 拒绝代批。
- 推送失败 = 没人可能批准 → 立刻拒，不让 claude 干等 30 分钟。
- Hub 够不着 / 记录过期 / run_id 未知 → 全部按 deny 处理。**审批链路任何一环断了都是拒，不是放。**

## 各处开关的落点

| 位置 | 干什么 |
|---|---|
| `hub/.env` `DK_APPROVALS=1` | 总开关 |
| `hub/.env` `DK_APPROVAL_BUDGET_SEC` | 等多久没人回就自动拒（默认 1800） |
| `sandbox-settings.json` `permissions.ask` | 哪些工具要问（按能力列全） |
| `core/runner.py` `_DANGEROUS` | 审批关掉时摘哪些工具 |
| `DK_MCP_PYTHON` | 跑 MCP server 的 python（冻结部署时要指到真 python） |
| `DK_APPROVAL_DEBUG_LOG` | MCP server 收到的原始 payload 落哪（排查用） |

## 部署待办（还没做）

**目前只在源码模式验过（`hub/.venv/bin/python -m hub.app`），没进 .app。** 要上正牌 bot：

1. `build_sidecar.sh` 是逐个模块 stage 的，**`approvals/mcp_server.py` 得显式加进去**
   （新目录不会自动进）。缺了会在 `_mcp_config_for_run` 抛 FileNotFoundError → 这条拒跑，
   不会降级成无闸执行（故意的）。
2. 冻结环境里 `sys.executable` 是那个二进制不是 python → 设 `DK_MCP_PYTHON=/usr/bin/python3`。
   `mcp_server.py` 刻意只用 stdlib，系统 python 就能跑。
3. 按 `CLAUDE.md` 的铁律：整体 `bash macapp/build_app.sh` 重建，然后从访达双击一次 DK.app，
   别只 `launchctl kickstart`。
4. 起来之后再把 `DK_APPROVALS=1` 打开，先在 Telegram 上手动点一次确认按钮真的通。

## 还没做的

- SDK 引擎路径（`CLAUDE_ENGINE=sdk`）没接审批，开了审批会**拒跑**并提示改回 cli——
  不静默无闸执行。要接得走 `can_use_tool`。
- 「总是允许」按钮：回调带 `suggestions`，把规则写进 `settings.local.json`。现在只有
  「允许一次 / 拒绝」。
- `defer`（人睡着了先让进程退出、之后从持久化 session 恢复）：claude 有这个决策值且
  **只在 print 模式可用**（二进制里的原话：*permissionDecision=defer in interactive mode;
  ignoring (defer is print-mode only)*），正好对口手机审批场景，但还没接。现在超预算是直接拒。
- 飞书/企微渠道的审批按钮（目前只有 telegram；`curl`/`local` 走日志 + HTTP 批准）。
