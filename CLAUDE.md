# DK — 项目工作约定

> Telegram/飞书 bot（原 chat-cc-bot）。launchd 常驻 + PyInstaller sidecar + Swift macapp 壳。
> 个人项目：commit + push 可自行判断，不必每次问。

## 后端部署铁律（把 bot 搞停过 1+ 小时的教训，2026-06-21）

**改后端只能整体重建 `bash macapp/build_app.sh`（swift release + build_sidecar.sh + 一次性 deep 签名），绝不 in-place 换 sidecar/swift 二进制 + 零敲碎打 `codesign --force` 重签。**

架构：launchd job `com.lengmo.chatccbot`（plist 在 `~/Library/LaunchAgents/`，带 DK_ROOT + WorkingDirectory=repo 根）→ 启 `dk_sidecar supervisor` → supervisor `subprocess.Popen` 自我 re-exec 出 hub(8787) + 各渠道。

为什么不能 in-place：
- in-place `cp` 新二进制进 `dist/DK.app` + 反复重签会破坏 .app bundle 封印
- 更狠的是：重建的 PyInstaller sidecar 在 **launchd 上下文**下自我 spawn 子进程会被 amfi/Gatekeeper 拦——现象是 `launchctl kickstart` 后 supervisor 在跑但 **0 子进程、8787 永不 bind、out/err.log 空**
- 关键判据：同一个二进制在 shell 里 `DK_ROOT=<repo> ./dk_sidecar supervisor` 直跑完全正常（交互上下文）→ 是 launchd 安全上下文问题，不是二进制坏 / DK_ROOT 缺 / quarantine
- 连 coherent 的 build_app.sh 整体签完，launchd 仍可能 spawn 不出 → 疑似需「从访达双击 DK.app 交互启动一次重新注册」（未确认，待验）

## 验证与应急

- **验 /notify 等后端改动**：优先临时 hub 旁路——`CHATCC_SUPERVISED=1 HUB_PORT=8788 hub/.venv/bin/python -m hub.app`（源码跑、不碰正牌 bot、curl 完即杀）。frozen 二进制旁验要带 `DK_ROOT`，否则 app_root() 走 __file__ 落到 _internal 找不到 config
- **应急恢复 bot**：`DK_ROOT=<repo> PYTHONUNBUFFERED=1 dist/DK.app/Contents/Resources/dk_sidecar/dk_sidecar supervisor &`（bridge 直跑能 spawn；但非 launchd 托管，重启不自启）
- **真要换正牌后端**：build_app.sh 整体重建后，让用户从访达双击 DK.app 一次，再看 launchd 能否拉起——别只 `launchctl kickstart`

## 其他

- 出站通知/监听 tab 代码在 `ralph/auto`
- ralph loop 骨架（loop.sh/guard.sh/fix_plan.md）在 `ralph/`，backlog 已清零处于休眠态
