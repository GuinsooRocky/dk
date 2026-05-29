# 守护进程（launchd）

把飞书 WS 长连接服务做成**开机自启 + 崩溃自愈**的后台守护，不用再开终端。

## 前置

1. 装好 WS 依赖：`cd feishu-claude && ./.venv/bin/python -m pip install -r requirements.txt`
2. `.env` 填好 `FEISHU_APP_ID / FEISHU_APP_SECRET / ALLOWED_USERS`
3. **飞书后台**：开发者后台 → 你的应用 → 事件订阅 → 订阅方式改为 **「使用长连接接收事件」**（不再是填 URL）。仍需开启 `im.message.receive_v1` 事件 + 权限。

## 用法

```bash
./daemon/feishu-daemon.sh install     # 生成 plist + 加载（登录自启、崩溃自拉）
./daemon/feishu-daemon.sh status      # 看状态/PID/上次退出码
./daemon/feishu-daemon.sh logs        # 跟踪日志
./daemon/feishu-daemon.sh restart     # 重启
./daemon/feishu-daemon.sh stop        # 停（KeepAlive 服务必须用这个，不能只 kickstart stop）
./daemon/feishu-daemon.sh uninstall   # 彻底移除，不再自启
```

## 常见疑问

**断网会怎样？** 不额外占内存。没消息进来就不会 fork claude，服务只是空转等待；lark SDK 的 `auto_reconnect` 会在网络恢复后自动重连。`KeepAlive=SuccessfulExit:false` 只在进程**异常退出**时才重启，断网不触发重启循环。

**会不会很占内存？** launchd 本身零开销（它是系统进程）。用它跑 vs 手动开终端跑，内存一样：空闲服务很轻，真正占用的是干活时的 claude 任务（已被 `CLAUDE_MAX_CONCURRENCY` 封顶，默认 1）。

**合盖/休眠呢？** launchd 救不了——Mac 睡了就断（物理约束）。要 7×24 在线得在「系统设置 → 电池/锁屏」关掉休眠，或插电夹盖运行。

**怎么彻底关掉？** `uninstall`（停止 + 删 plist + disable，重启也不再起）。临时停用 `stop`。

## 坑（已在脚本里规避）

- launchd 下 PATH 极简，`claude`（在 `~/.local/bin`）默认找不到 → plist 的 `EnvironmentVariables.PATH` 已补上 `~/.local/bin` 和 homebrew 路径。若仍报找不到 claude，在 `.env` 把 `CLAUDE_CMD` 设成绝对路径。
- `start.sh` 里的 `read -r` 交互暂停与 launchd 不兼容——所以守护**不走 start.sh**，直接由 plist 调 `venv/bin/python feishu_ws_server.py`。
