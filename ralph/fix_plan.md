# fix_plan.md — chat-cc-bot 的 Ralph 任务清单

> Ralph 每轮读这个文件,挑**「待办」里最上面一个 `- [ ]`** 的任务,只做那一个,
> 跑 `ralph/smoke_test.py`,全绿才 commit + 打勾,然后退出。
> 标记:`[ ]` 待办(可动可验) · `[x]` 已完成 · `[skip]` 不在本仓范围(不计入循环)。

## 现状(2026-06-17 实测,smoke 全绿)
v1 后端基本完工且自洽。战略文档 §11 的 5 件:
- [x] #1 protobuf 共存实测 + 根 `requirements.txt`(单解释器打包路线 GREEN)
- [x] #2 `GET /supervisor` + `last_error` 捕获(supervisor.py stderr pipe + deque ring buffer)
- [x] #3 `.env` override footgun(core/config.py supervised-aware `load_env`)
- [x] #4 `daemon/chatccbot.sh` 泛化 LaunchAgent + RunAtLoad ON(主体已做)
- [x] #5 微信禁用行数据模型 —— `macapp/Models.swift` 的 `WECHAT_META` 已落(UI 渲染见 M4)

## 待办(macapp 原生 macOS app —— 上个 session 起了头只剩 Models,本体未做)
> 起点:`macapp/` 仅有 `Package.swift` + `Models.swift`(数据模型齐),`swift build` 过但无 app 本体。
> 目标(战略 §4/§5):菜单栏常驻 + 三 tab 窗口,Channels 读 `/supervisor` 按 4 态显示。
> 每条验收 = `ralph/smoke_test.py` 全绿(已含 `swift build`)。一次只做一条。

- [x] M1 网络层:`Sources/ChatCCBot/Api.swift`,async 拉 `http://127.0.0.1:<hub端口>/supervisor`、`/status`、`/stats`,解码进现成 Models;端口从 config.toml/默认值读。验收:swift build 过。
- [x] M2 App 入口:`@main` + `MenuBarExtra`(菜单栏常驻,LSUIElement 风格)+ 一个主 `Window`。验收:swift build 过 + `swift run` 能起出菜单栏图标。
- [x] M3 三 tab 窗口骨架:`Channels` / `Insights` / `Settings` 三个占位 tab。验收:swift build 过。
- [x] M4 Channels 视图:列 `KNOWN_CHANNELS` + `WECHAT_META` 禁用行;按 4 态(off/needs_setup/connected/error)上色 + 显 `last_error`;数据来自 M1。验收:swift build 过。
- [x] M5 Insights 视图:跑 `/stats`,banner 写 "since launch / resets on restart"(§5.3 诚实降级)。验收:swift build 过。
- [x] M6 轮询刷新:每 3s 拉一次 `/supervisor` 更新 UI(本身就是个小 loop);supervisor 不可用时按 `ok:false` 诚实降级不假装在线。验收:swift build 过。

## 三期(W 系列：交互/面板/引导/打包，全做完，smoke 全绿，未提交)
- [x] W1 开关写回：hub `POST /config/channel` 改 config.toml + reload 标记；supervisor 每 tick 热重载起/停渠道；app toggle 乐观更新接上。运行时验证过(切 wecom)。
- [x] W2 菜单栏 + Settings：model 提到 App 级自启轮询；菜单栏图标随状态变(空闲/忙/没连上)+ 渠道圆点菜单；Settings 信息面板读 /status(引擎/工具/单飞/运行时长/端口/权限/日志)。
- [x] W3 Onboarding：`ClaudeCheck` 非阻塞探 claude 装没装/登录没；Setup tab(Claude 卡 + Mac 别睡 + 逐渠道按状态给步骤)。**实时抓 ID 加白名单 = 后续增强(需跨渠道改 reject 上报)**。
- [x] W4 打包：`macapp/build_app.sh` 产出 ad-hoc 签名、LSUIElement(无 Dock) 的可双击 `ChatCCBot.app`。**公证(发给别人) 需 Apple Developer 证书；Python 后端 sidecar 打进 .app = 后续**。

## v2 暂缓(不计入循环,标 skip 防 loop 抢跑)
- [skip] T2 SQLite stats 持久化,让 `/stats` banner 字面成真(§9)。路线图定 v1=诚实降级,归 v2。
- [skip] T3 语音回归时把 telegram 的 transcribe 懒导入铺到 feishu/wecom(parity 不变量会盯)。语音整体归 v2。

## 提交边界(重要,违反用户铁律会出事)
用户规矩:**从不主动 commit/push,除非明确要求**。Ralph 默认每轮 commit 来跨 context 传状态——冲突。
**本 loop 只在专用分支 `ralph/auto` 上 commit,main/develop 永不碰**;跑完用户 review 分支再决定 merge。
