# 真隔离（macOS Sandbox）

`CLAUDE_WORK_DIR` **不是沙箱**——它只是 claude 的初始目录，开了 Bash 仍能 `cd /`、读 `~/.ssh`、写系统路径。

配置文件：[`sandbox-settings.example.json`](./sandbox-settings.example.json)（照它 `cp` 出 `sandbox-settings.json`，本机路径自己改）。

## 两层闸，缺一层就有洞（2026-07-30 实测修正）

以前这份文档只讲了 OS 沙箱一层，那是不够的。实测：

```
settings 里 denyRead 一个目录，然后让 claude 用两种方式读同一个文件
  Read 工具       → OK:TOPSECRET-BANANA-42        ← 读穿了
  bash python3 读  → BLOCKED PermissionError       ← 被挡
```

**`sandbox.*` 只包 Bash 起的子进程，claude 自己的进程不在沙箱里。** 所以 claude 自己的
`Read`/`Grep`/`Glob`/`WebFetch` 完全不受 `sandbox.filesystem.denyRead` 约束。要封住它们，
得另加 `permissions.deny` —— 那是进程内的闸。

| 层 | 配置 | 管谁 | 机制 |
|---|---|---|---|
| OS 层 | `sandbox.filesystem` / `sandbox.network` | Bash 起的子进程（含它自己写个 `.py` 再跑） | Seatbelt，进程外，绕不过 |
| 进程内层 | `permissions.deny` | claude 自己的 Read/Grep/Glob | claude 自己执行，只挡自己的工具调用 |

两层各有各的洞，合起来才闭环：OS 层挡不住 Read 工具，进程内层挡不住"写个脚本再跑"。

`permissions` 的路径写法跟 `sandbox` 段不一样：**`//` 开头表示绝对路径，不吃 `~` 展开**；
`sandbox` 段那边可以直接用 `~`。写混了规则会静默不生效。

## 必须跑探针，不能靠看配置

规则名/路径写错，claude **静默忽略**，配置看起来滴水不漏、其实一点没生效。所以：

```bash
bash scripts/sandbox-probe.sh          # 退出码 0 = 两层闸都在（现状）
bash scripts/outer-sandbox-probe.sh    # 退出码 0 = allow-list 外层包裹可用（还没接线，见「残留风险」）
```

它跑 5 个探针：Read 读 `~/.zshrc`、Read 读本仓 `telegram/.env`、Grep 搜 `~/.ssh`、
bash 里 python3 读 `~/.zshrc`（前 4 个必须全 BLOCKED），外加一个工作目录里的
控制组文件（必须 OK——否则"全挡"可能只是把正常活也掐死了）。

改 `sandbox-settings.json` 之后一定重跑。

## 各字段作用

| 配置 | 作用 |
|------|------|
| `enabled: true` | 开启沙箱 |
| `failIfUnavailable: true` | 沙箱拉不起来就**报错退出**，绝不静默裸跑（防 fail-open） |
| `autoAllowBashIfSandboxed: false` | **必须 false**：它的意思是"在沙箱里就免提示跑"，正好把审批链路旁路掉（实测 true 时 `--permission-prompt-tool` 压根不被调用）。见 [APPROVALS.md](./APPROVALS.md) |
| `filesystem.allowWrite` | **写**只允许工作目录（`~/claude-*-workdir`）；其余全盘只读 |
| `filesystem.denyRead` | 禁**子进程**读 `~/.ssh`、Keychains 等（不管 Read 工具，见上） |
| `network.allowedDomains` + `allowManagedDomainsOnly` | **子进程**只能访问白名单域名（不管 WebFetch，它是 claude 自己的工具） |
| `permissions.deny` | 禁 claude 自己的 Read/Grep 碰敏感路径 |

## 怎么挂上去（只作用于 bot 起的 claude，不碰你日常 claude）

**不要**塞进全局 `~/.claude/settings.json`（会影响你平时所有 claude）。走 `--settings` 透传：

```
# hub/.env
CLAUDE_SETTINGS=/Users/你/Desktop/my-code/dk/sandbox-settings.json
```

`core/runner.run_claude` 会带 `--settings <该文件>` 起 claude，只对 bot 生效。

### ⚠ 老 GUARD-3 是无效的（2026-07-30 实测推翻）

`core/runner` 原来的 GUARD-3 是「沙箱没验过 → 从 `--allowedTools` 里剥掉 Bash/Write/Edit」。
**这个机制不成立**：`--allowedTools` 是免提示放行清单，不是能力白名单。实测拿
`--allowedTools "Read,Glob,Grep,WebFetch"` 跑 `echo` 照样成功、`permission_denials` 为空。

也就是说 dk 一直宣称的"只读四件"是假的 —— bot 从来都能跑任意 shell 命令。

现在改成：
- **`--disallowedTools`** 才真摘工具（`_disallowed_tools`），而且按**能力**列全（只 deny Bash
  会被 Monitor 绕过，实测）
- 给不给危险工具，判据是**有没有人在回路里**（`DK_APPROVALS`），不是沙箱验没验过。
  沙箱管"跑起来能碰到什么"，管不了"该不该跑"
- 详见 [APPROVALS.md](./APPROVALS.md)

注意权威顺序：supervisor 按 `setdefault` 从 `config.toml` 注入，`hub/.env` 只补缺不覆盖 →
**被 supervisor 托管时 `config.toml` 是权威**，改 `hub/.env` 的 `CLAUDE_TOOLS` 没用。

## 残留风险（P0 方案已验通，代码还没接）

> **2026-07-30 更新**：下面前两条的解法已经全链路实测跑通，但 **`core/runner.py` 还没接**，
> 所以现状仍是本文档上半部分描述的两层闸。方案与实测数据在
> `~/Desktop/my-code/telegram-agent-bot-设计.md` §3（不在本仓 `docs/` 里，别找错地方）。

- **姿态是 deny-list，不是 allow-list**。`permissions.deny` 只能列举已知敏感物；你整个家目录
  还有多少值钱东西没列，靠人记。**给第二个人用之前必须先解掉**，deny-list 撑不住。
  → **解法已验通**：外层 `srt` 把整个 claude 进程包住，claude 自己的 Read 也吃 OS 边界
  （实测：包裹前读穿 `OK:TOPSECRET-BANANA-42`，包裹后 `BLOCKED:EPERM`）。
  配合独立 `CLAUDE_CONFIG_DIR`，连 owner 的 `~/.claude/projects/` 会话记录都读不到。
- **`WebFetch` 是外传通道**，进程内工具、不受 `sandbox.network.allowedDomains` 约束。
  → **解法已验通**：外层包裹下 WebFetch 也进 OS 网络边界，非白名单域名拿到 `Socket is closed`。
- `sandbox-exec`（Seatbelt 的 CLI 壳）被 Apple 标 deprecated，底层内核机制仍在用（Chrome、codex 都依赖），
  macOS 26 仍工作。长期留意版本变化。

### 接线时会踩的两脚（已实测）

1. **`srt` 抢 `--settings`**。srt 自己有 `-s, --settings`，commander 不认命令边界，
   `srt -s a.json claude --settings b.json` 会把 `b.json` 当 srt 配置、报
   `network: Required / filesystem: Required` 拒绝启动。**必须 `srt -s a.json -- claude …`**。
   `runner._run_cli` 本来就在传 `--settings`，这脚跑不掉。
2. **srt 只在 npx 缓存里**（`~/.npm/_npx/76bebc5af50919ba/`，0.0.66，全局没装）。
   launchd 常驻服务不能指着一个 `npm cache clean` 就没的路径 —— 要么全局装、要么 vendor 进仓，
   并且**找不到就 fail-closed 不启动**，绝不静默降级成裸跑（同 `failIfUnavailable` 的道理）。
