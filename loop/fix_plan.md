# dk 收尾批次 — fix_plan

来源：dk 执行计划 M1–M5（workflow wqjedr9mo 产出）。
基线：GUARD-1（三档工具选择）已在 HEAD，工作区干净。
执行方式：主 agent **监督式**逐项推进（非无人 Ralph loop）——每项 build/import 真验证 + scoped commit + 里程碑汇报。代码项做完即停，文档判断项留人拍板。

## 验收命令（back-pressure）
- Swift 项：`cd macapp && bash build_app.sh`（编译 complete + codesign satisfies 才算过）
- Python 项：`python3 -c "import ..."` 干净 + `python3 ralph/smoke_test.py` 绿
- **不反复重启线上后端**；Python 改动的运行时验证攒到最后一次性 bounce。

## 代码项（自动推进）

### M5 macOS 无障碍（Swift，build-only，零 bot 影响 → 先做）✅ 完成（除 keyboard 延后）
- [x] M5-contrast   ChannelsView 两处文字改中性色（③青蓝经核为图标非文字，不动）· 994025d
- [x] M5-voiceover  图标/labelsHidden 开关补标签（4 文件）· 0268fa2
- [x] M5-dkswitch   DKSwitch 暴露为标准 Toggle（角色/值）+ Reduce Motion + Increase Contrast · 0268fa2
- [x] M5-keyboard   Cmd+O 打开主窗（NSApp 前置）· 42befbc
- [x] M5-dyntype    文档化「有意不跟随 Dynamic Type + 提上限须先验布局」（保守支，不改行为）· 7824631

### M3 访客 onboarding（Python）✅ 完成
- [x] GUEST-3  共用文案抽进 core/replies.py，三渠道引用 · 624a9ec
- [x] GUEST-2  授权用户 /start /help 回 HELP 简介（三渠道）· 624a9ec

### M2 数据同意 + 清理 ✅ 完成
- [x] GUARD-4  加人授权告知 sheet（按工具档措辞）+ Settings 清除历史 + POST /stats/clear · 2551809
- [x] GUARD-6  授权 sheet 含「消息会留在主机」告知 · 2551809

### M1 沙箱护栏剩余 ✅ 完成（⚠ 运行时验证需重启后端 + 重开 app 眼见）
- [x] GUARD-2  /status.sandbox_verified + SettingsView 警示（非硬锁，理由见 commit）· 2551809
- [x] GUARD-3  core/sandbox.py 判据 + runner acceptEdits→default 降级 · 3e22096

## 文档/产品项 ✅ 完成（全部落到 a8f8935；定位措辞用户可自行调）
- [x] BET-3   README 隐私即架构卖点
- [x] BET-1   README「默认安静」卖点
- [x] BET-2   使用说明 记忆持久化 + 诚实边界
- [x] BET-5   战略 §12 出站限速器 defer
- [x] BET-7   使用说明 菜单栏实时捕获替代手动 grep
- [x] BET-8   战略 §12 MicroClaw 对比（已核实：真竞品、功能更全但开发者跑的 runtime）
- [x] BET-6   战略 §12 + config.py 注释标 .env footgun 已落地
- [x] GUARD-7 docs/数据策略.md 已建

## 规矩
- scoped commit，只 add 本项碰的文件，绝不 `git add -A`
- 删文件走 ~/.Trash（NSWorkspace.recycle），不 rm
- 不碰 .env / 真实凭证；不确定就停，记一行 `⚠ 卡住:原因`
