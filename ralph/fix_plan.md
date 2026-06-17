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
- [skip] #5 微信禁用行 —— SwiftUI 原生 app 的事,不在本(Python 后端)仓

## 待办(本仓可动、可被 smoke 验证)
- [x] T1 给 `run.sh` / `menubar/启动菜单栏.command` / `daemon/feishu-daemon.sh` 各加一行「待退役」注释头(§11#4 尾;no-auto-delete:只标不删) —— 主对话 2026-06-17 手做,smoke 全绿
- [ ] T2 (v2,未到点) SQLite stats 持久化,让 `/stats` 的 banner 字面成真(§9;新增第二个后端 add)。**v1 不做**:路线图定 v1=诚实降级 Insights,SQLite 归 v2。
- [ ] T3 (v2,未到点) 语音回归时把 telegram 的 transcribe 懒导入铺到 feishu/wecom(parity 不变量盯着别漏渠道)。**v1 不做**:语音整体归 v2。

## 提交边界(重要,违反用户铁律会出事)
用户规矩:**从不主动 commit/push,除非明确要求**。Ralph 默认每轮 commit 来跨 context 传状态——冲突。
**本 loop 只在专用分支 `ralph/auto` 上 commit,main/develop 永不碰**;跑完用户 review 分支再决定 merge。
