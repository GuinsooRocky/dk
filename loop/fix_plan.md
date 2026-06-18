# dk 收尾批次 — fix_plan

来源：dk 执行计划 M1–M5（workflow wqjedr9mo 产出）。
基线：GUARD-1（三档工具选择）已在 HEAD，工作区干净。
执行方式：主 agent **监督式**逐项推进（非无人 Ralph loop）——每项 build/import 真验证 + scoped commit + 里程碑汇报。代码项做完即停，文档判断项留人拍板。

## 验收命令（back-pressure）
- Swift 项：`cd macapp && bash build_app.sh`（编译 complete + codesign satisfies 才算过）
- Python 项：`python3 -c "import ..."` 干净 + `python3 ralph/smoke_test.py` 绿
- **不反复重启线上后端**；Python 改动的运行时验证攒到最后一次性 bounce。

## 代码项（自动推进）

### M5 macOS 无障碍（Swift，build-only，零 bot 影响 → 先做）
- [ ] M5-contrast   ChannelsView 三处彩色语义文字改中性色（brainBanner 红字 / header 错误态 /「刚发过」青蓝）→ .primary/.secondary，圆点保持上色 · verify: build_app.sh
- [ ] M5-voiceover  图标/labelsHidden 开关补 .accessibilityLabel（MenuBarContent/ChannelsView/SettingsView）· verify: build_app.sh
- [ ] M5-dkswitch   DKSwitch 补 .isToggle trait + Reduce Motion + Increase Contrast · verify: build_app.sh
- [ ] M5-keyboard   ChatCCBotApp .commands 补「打开 DK」Cmd+O · verify: build_app.sh
- [ ] M5-dyntype    核 minScale/maxScale 覆盖 ≥200% + 文档化（保守支，最小代码）· verify: build_app.sh

### M3 访客 onboarding（Python）
- [ ] GUEST-3  THINKING/SERVICE_DOWN/NO_REPLY 抽进 core 共享常量，三渠道引用 · verify: import + smoke
- [ ] GUEST-2  授权用户 /start /help 回能力简介（telegram/feishu/wecom）· verify: import + smoke

### M2 数据同意 + 清理（Swift + 后端只读 endpoint）
- [ ] GUARD-4  加人入口插授权告知 sheet（按工具档措辞）+ Settings 加 Clear history（走废纸篓）+ 后端 POST /stats/clear · verify: build_app.sh + import
- [ ] GUARD-6  在 GUARD-4 sheet 补「消息会留在主机」告知文案 · verify: build_app.sh

### M1 沙箱护栏剩余（动 live 后端，最后做，运行时验证单独留）
- [ ] GUARD-2  后端 GET /sandbox + SettingsView 危险档锁态 · verify: build_app.sh + import；⚠ 运行时验证留人
- [ ] GUARD-3  runner.py acceptEdits 按沙箱验证降级 default · verify: import；⚠ 运行时验证留人

## 文档/产品判断项（不自动，留人拍板）
- [ ] BET-3   README 隐私=数据在本机卖点（依赖 M2 落地后才不空头）
- [ ] BET-1   README「@才应答」卖点（剔除 MicroClaw 噪音 bot 措辞）
- [ ] BET-2   使用说明.md 记忆持久化 + 诚实边界
- [ ] BET-5   战略 §9/§10 出站限速器 defer
- [ ] BET-7   使用说明.md setup seam 已就绪一行
- [ ] BET-8   战略 §6 MicroClaw 对比（⚠ 落笔前 last30days/WebSearch 核实现状）
- [ ] BET-6   战略 §11 .env footgun 标「已落地」+ config.py 注释
- [ ] GUARD-7 新建 docs/数据策略.md 写 v1 不落盘消息约束

## 规矩
- scoped commit，只 add 本项碰的文件，绝不 `git add -A`
- 删文件走 ~/.Trash（NSWorkspace.recycle），不 rm
- 不碰 .env / 真实凭证；不确定就停，记一行 `⚠ 卡住:原因`
