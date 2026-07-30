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

## 第三层：外层包裹（allow-list 姿态，2026-07-30 接线，默认关）

上面两层合起来仍是 **deny-list** ——「列举已知敏感物再挡掉」，你家目录里还有多少值钱东西
没列，靠人记。给第二个人开账号撑不住。

这一层从**进程外**用 `srt`（`@anthropic-ai/sandbox-runtime`）把整个 claude 包进 OS 沙箱，
姿态反过来：**默认全挡，只放行列出来的**。claude 自己的 Read/Grep/WebFetch 也一起落进边界。

| | 内置 `sandbox.*` | `permissions.deny` | 外层包裹 |
|---|---|---|---|
| 管 Bash 子进程 | ✅ | ✗ | ✅ |
| 管 claude 自己的 Read/Grep | ✗ | ✅ | ✅ |
| 管 claude 自己的 WebFetch | ✗ | ✗ | ✅ |
| 姿态 | allow-list（写） | deny-list | **allow-list** |
| 绕过成本 | 进程外，绕不过 | 它自己执行，写个脚本就绕开 | 进程外，绕不过 |

### 怎么开

```bash
bash scripts/install-srt.sh                       # 1. 装 srt 到跟 node 版本解绑的位置
bash scripts/init-bot-config-dir.sh               # 2. 给 bot 建独立 CLAUDE_CONFIG_DIR
cp srt-settings.example.json srt-settings.json    # 3. 按注释改路径
bash scripts/outer-sandbox-probe.sh               # 4. 六项探针全过才算数
```

然后 `hub/.env`（跟 `CLAUDE_SETTINGS` / `DK_APPROVALS` 同一条路，supervisor 不注入这几个）：

```
DK_OUTER_SANDBOX=1
DK_SRT_SETTINGS=/Users/你/Desktop/my-code/dk/srt-settings.json
DK_BOT_CONFIG_DIR=/Users/你/.local/share/dk-botcfg
# 可选，不填走默认落点 ~/.local/lib/srt 和 ~/.local/bin/node
# DK_SRT_CLI=... / DK_SRT_NODE=...
```

**只对 cli 引擎有效。** `CLAUDE_ENGINE=sdk` 跑在本进程内、包不进 srt，同时开会**拒跑**
（跟审批一样 fail-closed，免得以为有边界其实没有）。

### fail-closed 在哪几处

开了 `DK_OUTER_SANDBOX=1` 但装不起来，一律**这条消息不执行**，绝不裸跑：

- srt 的 `cli.js` / node 找不到
- 没给 `DK_SRT_SETTINGS`、文件不存在、不是合法 JSON、`allowRead` 是空的
- **`allowRead` 盖不到这次跑必须读的路径**（claude 二进制、bot 配置目录，开审批时还有
  `approvals/mcp_server.py` 和跑它的 python）。这条是提前炸 —— 不然现象会是 claude 起来了
  但报 `command not found` 或「审批链路起不来」，很难查

### 四个实测出来的坑

1. **`srt` 会抢 claude 的 `--settings`**。srt 自己有 `-s, --settings`，它的 commander 不认
   命令边界，`srt -s a.json claude --settings b.json` 会把 `b.json` 当 srt 配置，报
   `network: Required / filesystem: Required` 拒绝启动。**必须 `srt -s a.json -- claude …`**。
2. **不能调 `node_modules/.bin/srt` 那个 shim**。它的 shebang 是 `#!/usr/bin/env node`，
   而 launchd 给的 PATH 只有 `/usr/bin:/bin:/usr/sbin:/sbin`，实测直接
   `env: node: No such file or directory`。所以代码里是「绝对 node + 绝对 cli.js」。
3. **沙箱认字面路径，不认 resolve 后的真身**。实测：allowRead 只有
   `~/.local/share/claude`（真身）却用 `~/.local/bin/claude`（软链）调 → `Operation not
   permitted`；反过来只放行 `~/.local/bin` 就能跑。所以覆盖检查也按字面比。
4. **别用 `npm i -g` 装 srt**。本机 node 是 nvm 管的，全局前缀是
   `~/.nvm/versions/node/<版本>/`，升一次 node 就没了。`scripts/install-srt.sh` 装到
   `~/.local/lib/srt`，跟版本解绑。（顺带：在空目录直接 `npm i` 会让 npm 往上找最近的
   `package.json`，实测会装进 `~/node_modules` 并改 `~/package.json`。脚本里先写好
   `package.json` 就是为了钉住它。）

### 代价：凭证从 Keychain 挪到了明文文件

bot 用独立配置目录就得把凭证搬过去（认证态拆成两半：账号关联在 `~/.claude.json` 的
`oauthAccount`，凭证本体在 Keychain 的 `Claude Code-credentials`；只搬一半都是 `Not logged in`）。
搬完 `refreshToken` 就躺在 `<bot配置目录>/.credentials.json` 里，而那个目录沙箱是放行的。

两层缓解都实测过：

- `permissions.deny` 加 `Read(//<bot配置目录>/**)` → bot 自己的 Read 工具读不到，
  **且不影响认证**（claude 读凭证走内部路径，不经 Read 工具）
- 网络白名单只有 anthropic 三个域名，外传通道封死

想彻底不落明文得走 `claude setup-token`（长效 token 走 `CLAUDE_CODE_OAUTH_TOKEN`），
那是交互式的、要 owner 本人过一遍浏览器，还没验。

## 残留风险

- `sandbox-exec`（Seatbelt 的 CLI 壳）被 Apple 标 deprecated，底层内核机制仍在用（Chrome、codex 都依赖），
  macOS 26 仍工作。长期留意版本变化。
- **srt 是 beta，配置格式可能变**。`install-srt.sh` 钉死了版本（0.0.66）；升级前后都要重跑
  `outer-sandbox-probe.sh`。
- 开审批时 `allowRead` 只能放行整个仓（MCP server 在里面）→ bot 读得到 dk 自己的源码。
  那是它自己的代码，可接受；但别把别的项目塞进同一个目录。
- 外层包裹**默认关**。开之前 bot 仍是上面两层的 deny-list 姿态 —— 自己一个人用够，
  给第二个人开账号前必须先把这层打开并跑过探针。
