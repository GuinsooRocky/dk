# 真隔离（macOS Sandbox）

`CLAUDE_WORK_DIR` **不是沙箱**——它只是 claude 的初始目录，开了 Bash 仍能 `cd /`、读 `~/.ssh`、写系统路径。
要"开了 Bash 也安全"，得用 Claude Code 内建的 OS 级沙箱（macOS 走 Apple Seatbelt）。

本目录提供 [`sandbox-settings.example.json`](./sandbox-settings.example.json)，基于 Claude Code 2.1.x 的权威 schema。

## 它做了什么

| 配置 | 作用 |
|------|------|
| `enabled: true` | 开启沙箱 |
| `failIfUnavailable: true` | 沙箱拉不起来就**报错退出**，绝不静默裸跑（关键：防 fail-open） |
| `autoAllowBashIfSandboxed: true` | 既然已被沙箱关住，Bash 可免提示运行——这才让"开 Bash"变得可接受 |
| `filesystem.allowWrite` | **写**只允许工作目录（`~/claude-*-workdir`）；其余全盘只读 |
| `filesystem.denyRead` | **禁读** `~/.ssh`、`~/.aws`、`~/.config/gh`、Keychains、本项目 `.env` 等敏感物 |
| `network.allowedDomains` + `allowManagedDomainsOnly: true` | 沙箱内命令**只能访问白名单域名**（claude API + 飞书），其余网络掐断 |

核心收益：即便被 prompt 注入诱导跑 `cat ~/.ssh/id_rsa` 或 `curl 外传`，沙箱会拦住——读不到密钥、连不出去、写不进系统目录。

## 怎么用（只作用于 bot 起的 claude，不碰你日常 claude）

**不要**把它塞进你全局 `~/.claude/settings.json`（那会影响你平时所有 claude 用法）。两种作用域方式：

1. **推荐：`--settings` 透传**（重构后 `core/runner` 已支持）——在 `.env` 设
   ```
   CLAUDE_SETTINGS=/Users/你/Desktop/my-code/dk/sandbox-settings.json
   ```
   run_claude 会带 `--settings <该文件>` 启动 claude，沙箱只对 bot 进程生效。
2. 或放到工作目录的 `.claude/settings.json`（如 `~/claude-feishu-workdir/.claude/settings.json`）。

用前先 `cp sandbox-settings.example.json sandbox-settings.json`，把 `allowWrite` 改成你**实际**的工作目录，按需调 `allowedDomains`。

## 注意

- `sandbox-exec`（Seatbelt 的 CLI 壳）被 Apple 标 deprecated，但底层内核机制仍在用（Chrome、codex 都依赖），macOS 26 仍工作。长期留意未来版本变化。
- 沙箱是"开 Bash 的前置条件"。**不开 Bash（默认只读工具）时其实用不到沙箱**——这是给你以后真要放开写/执行能力时的安全兜底。
- `network.allowedDomains` 配太窄可能让 `WebFetch` 取不到你想要的站点；按需加域名（支持 `*.example.com` 通配）。
