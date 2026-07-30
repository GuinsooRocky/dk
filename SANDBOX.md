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
bash scripts/sandbox-probe.sh          # 退出码 0 = 两层闸都在
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
| `autoAllowBashIfSandboxed: true` | 既然已被沙箱关住，Bash 可免提示运行——这才让"开 Bash"变得可接受 |
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

### ⚠ 挂沙箱会顺手把 Bash 开了（GUARD-3 联动）

`core/runner._effective_tools` 的逻辑是：**沙箱没验过 → 从工具清单里剥掉 Bash/Write/Edit**。
所以在 `CLAUDE_SETTINGS` 没配的年代，`tools` 里就算写了 `Bash,Write,Edit` 也一直在被剥，
实际生效的一直是只读四件。

一旦沙箱验过，GUARD-3 就不剥了 → **`tools` 那行会真的生效**。补安全配置这个动作本身
会解开危险工具，这是个反直觉的坑。所以 `config.toml` 的 `tools` 现在显式收成只读四件；
真要开 Bash/Write/Edit，先跑探针过，再一件件加回来。

注意权威顺序：supervisor 按 `setdefault` 从 `config.toml` 注入，`hub/.env` 只补缺不覆盖 →
**被 supervisor 托管时 `config.toml` 是权威**，改 `hub/.env` 的 `CLAUDE_TOOLS` 没用。

## 残留风险（P0 没解，等 srt 外层包裹）

- **姿态是 deny-list，不是 allow-list**。`permissions.deny` 只能列举已知敏感物；你整个家目录
  还有多少值钱东西没列，靠人记。真边界要把整个 claude 进程包进 OS 沙箱（allow-list 姿态），
  见 `docs/` 里的 telegram-agent-bot 设计文档。**给第二个人用之前必须先做这个**，deny-list 撑不住。
- **`WebFetch` 是外传通道**，进程内工具、不受 `allowedDomains` 约束。现在靠"Read 封住了就没东西可传"
  间接缓解，不是正面解决。
- `sandbox-exec`（Seatbelt 的 CLI 壳）被 Apple 标 deprecated，底层内核机制仍在用（Chrome、codex 都依赖），
  macOS 26 仍工作。长期留意版本变化。
