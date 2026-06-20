import SwiftUI
import Foundation   // sysctlbyname（笔记本检测）

// §4.1 多步交互向导（取代静态 OnboardingView 作引导入口）。
// W1：状态机骨架 + Screen0 资格预检 + Step1 Claude 三态门。
// channel / connect / perms / runmode 四步本任务先占位，W2/W3 实装；视觉/流程留 visual-qa 人工收尾。
enum WizardStep: Int, CaseIterable {
    case eligibility, claude, channel, connect, perms, runmode, done
}

@MainActor
final class WizardModel: ObservableObject {
    @Published var step: WizardStep = .eligibility
    @Published var channel = "telegram"      // Step2 选中的渠道（决策默认 Telegram-only）
    @Published var showAdvanced = false      // 「我已有开发者账号」→ 放出飞书/企微（opt-in）

    func next() {
        let all = WizardStep.allCases
        if let i = all.firstIndex(of: step), i + 1 < all.count { step = all[i + 1] }
    }

    func back() {
        let all = WizardStep.allCases
        if let i = all.firstIndex(of: step), i > 0 { step = all[i - 1] }
    }
}

struct WizardView: View {
    @EnvironmentObject var i18n: I18n
    @EnvironmentObject var model: HubModel
    @Environment(\.openURL) private var openURL
    @StateObject private var wiz = WizardModel()
    @StateObject private var claude = ClaudeCheck()   // Step1 复用：检装没装 / 登没登
    @State private var token = ""                      // Step3 粘贴的凭证
    @State private var selectedTier: ToolTier = .readonly             // Step4 权限档
    @State private var autostart = Autostart.available()             // Step5 开机自启（默认 ON）
    @State private var keepAwake = DisableSleep.isOn()               // Step5 合盖不休眠

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(i18n.t("wizard.step_of", wiz.step.rawValue + 1, WizardStep.allCases.count))
                    .dkFont(12).foregroundStyle(.secondary)
                switch wiz.step {
                case .eligibility: eligibilityScreen
                case .claude: claudeScreen
                case .channel: channelScreen
                case .connect: connectScreen
                case .perms: permsScreen
                case .runmode: runmodeScreen
                case .done: doneScreen
                }
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // 上一步 / 下一步
    private func navButtons(canNext: Bool = true) -> some View {
        HStack(spacing: 10) {
            Button(i18n.t("wizard.back")) { wiz.back() }
            Spacer()
            Button(i18n.t("wizard.next")) { wiz.next() }
                .buttonStyle(.borderedProminent).disabled(!canNext)
        }
    }

    // Step2 渠道选择：默认只给 Telegram（~60s 可过）；飞书/企微藏「我已有开发者账号」后（opt-in）
    private var channelScreen: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(i18n.t("wizard.channel_title")).dkFont(20, .bold)
            Text(i18n.t("wizard.channel_body")).dkFont(13).foregroundStyle(.secondary)
            channelRadio("telegram", "Telegram")
            Toggle(i18n.t("wizard.advanced"), isOn: $wiz.showAdvanced).toggleStyle(.checkbox)
            if wiz.showAdvanced {
                channelRadio("feishu", i18n.t("channel.feishu.name"))
                channelRadio("wecom", i18n.t("channel.wecom.name"))
            }
            navButtons()
        }
    }

    private func channelRadio(_ key: String, _ label: String) -> some View {
        Button {
            wiz.channel = key
        } label: {
            HStack(spacing: 8) {
                Image(systemName: wiz.channel == key ? "largecircle.fill.circle" : "circle")
                    .foregroundStyle(wiz.channel == key ? Color.dkAccent : .secondary)
                Text(label).dkFont(14)
            }.contentShape(Rectangle())
        }.buttonStyle(.plain)
    }

    // Step3 连接：粘 token 写 config + 实时抓 ID（复用 /pending+/allowlist，替代手 grep 回填）
    private var connectScreen: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(i18n.t("wizard.connect_title")).dkFont(20, .bold)
            Text(i18n.t("wizard.token_label")).dkFont(13).foregroundStyle(.secondary)
            HStack(spacing: 8) {
                SecureField(i18n.t("wizard.token_placeholder"), text: $token)
                    .textFieldStyle(.roundedBorder).frame(maxWidth: 300)
                Button(i18n.t("wizard.save_token")) {
                    let field = wiz.channel == "feishu" ? "app_id"
                              : (wiz.channel == "wecom" ? "bot_id" : "token")
                    let t = token
                    Task {
                        await model.setCred(wiz.channel, field, t)
                        await model.setEnabled(wiz.channel, true)   // 顺手开启该渠道
                    }
                }.disabled(token.isEmpty)
            }
            Divider().padding(.vertical, 4)
            // 实时抓 ID：现在从手机发一条，捕获的发送者渲染成「把【你】加白名单」一点即加
            Text(i18n.t("wizard.capture_hint")).dkFont(13).foregroundStyle(.secondary)
            if capturedHere.isEmpty {
                Text(i18n.t("wizard.no_capture")).dkFont(12).foregroundStyle(.tertiary)
            } else {
                ForEach(capturedHere) { p in
                    HStack(spacing: 8) {
                        Image(systemName: "person.crop.circle.badge.clock")
                            .foregroundStyle(Color.dkAccent)
                        Text(p.user).dkFont(12).lineLimit(1).truncationMode(.middle)
                        Spacer()
                        Button(i18n.t("wizard.add_me")) {
                            Task { await model.editAllow(wiz.channel, p.user, "add") }
                        }.controlSize(.small)
                    }
                }
            }
            navButtons()
        }
        .task { await model.refresh() }   // 拉一次 allowlist+pending（之后靠 model 刷新循环更新）
    }

    // 当前渠道下「想加入(发过消息但还没放行)」的人 = /allowlist 返回的 pending（来自渠道 /pending 上报）
    private var capturedHere: [PendingItem] {
        (model.allowlist?.pending ?? []).filter { $0.channel == wiz.channel }
    }

    // Screen0 资格预检：明示前提（付费 Claude 订阅 + 常醒 Mac），按钮不卡转圈
    private var eligibilityScreen: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(i18n.t("wizard.eligibility_title")).dkFont(20, .bold)
            Text(i18n.t("wizard.eligibility_body")).dkFont(14).foregroundStyle(.secondary)
            HStack(spacing: 10) {
                Button(i18n.t("wizard.have_sub")) { wiz.next() }
                    .buttonStyle(.borderedProminent)
                Button(i18n.t("wizard.help_subscribe")) {
                    if let u = URL(string: "https://claude.com/pricing") { openURL(u) }
                }
            }
        }
    }

    // Step1 Claude 三态门：检装/检登，未过（state != .ok）不放行下一步
    private var claudeScreen: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(i18n.t("wizard.claude_title")).dkFont(20, .bold)
            HStack(spacing: 8) {
                Image(systemName: claude.state.symbol)
                Text(i18n.t(claude.state.titleKey)).dkFont(15, .medium)
            }
            if !claude.detail.isEmpty {
                Text(claude.detail).dkFont(13).foregroundStyle(.secondary)
            }
            HStack(spacing: 10) {
                Button(i18n.t("wizard.verify_login")) { Task { await claude.verifyLogin() } }
                    .disabled(claude.state == .checking)
                Button(i18n.t("wizard.back")) { wiz.back() }
                Spacer()
                Button(i18n.t("wizard.next")) { wiz.next() }
                    .buttonStyle(.borderedProminent)
                    .disabled(claude.state != .ok)   // 三态门：没就绪不放行
            }
        }
        .task { await claude.quickCheck() }   // 进屏先轻检（--version），含超时兜底文案
    }

    // Step4 权限：三档预设复用 ToolTier；读+写/全权必须沙箱已验证才可选（GUARD-3）；措辞每次显示
    private var permsScreen: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(i18n.t("wizard.perms_title")).dkFont(20, .bold)
            Text(i18n.t("wizard.perms_consent")).dkFont(13).foregroundStyle(.secondary)   // 加人措辞每次显示
            ForEach(ToolTier.allCases, id: \.self) { tier in
                let locked = tier != .readonly && !sandboxVerified   // GUARD-3：写/全权要沙箱
                Button {
                    selectedTier = tier
                    let csv = tier.tools.joined(separator: ",")
                    Task { try? await HubApi.setTools(csv) }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: selectedTier == tier ? "largecircle.fill.circle" : "circle")
                            .foregroundStyle(selectedTier == tier ? Color.dkAccent : .secondary)
                        Text(i18n.t(tierKey(tier))).dkFont(14)
                        if locked {
                            Text(i18n.t("wizard.needs_sandbox")).dkFont(11).foregroundStyle(.orange)
                        }
                    }.contentShape(Rectangle())
                }.buttonStyle(.plain).disabled(locked)
            }
            navButtons()
        }
    }

    private var sandboxVerified: Bool { model.hubStatus?.sandbox_verified ?? false }

    private func tierKey(_ t: ToolTier) -> String {
        switch t {
        case .readonly:  return "settings.tools_readonly"
        case .readwrite: return "settings.tools_readwrite"
        case .full:      return "settings.tools_full"
        }
    }

    // Step5 运行模式：开机自启默认 ON（复用 Autostart）；笔记本警告「合盖即离线」+ 合盖不休眠（复用 DisableSleep）
    private var runmodeScreen: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(i18n.t("wizard.runmode_title")).dkFont(20, .bold)
            Toggle(i18n.t("wizard.autostart"), isOn: Binding(
                get: { autostart },
                set: { v in autostart = v; if Autostart.available() { Autostart.set(v) } }
            )).disabled(!Autostart.available())
            if isLaptop {
                Text(i18n.t("wizard.laptop_warn")).dkFont(13).foregroundStyle(.orange)
                Toggle(i18n.t("wizard.keep_awake"), isOn: Binding(
                    get: { keepAwake },
                    set: { v in keepAwake = v; Task.detached { _ = DisableSleep.set(v) } }  // 弹密码，丢后台
                ))
            }
            navButtons()
        }
    }

    // 笔记本检测：hw.model 含 "Book"（MacBook…）。合盖会断网=bot 离线，故警示。
    private var isLaptop: Bool {
        var size = 0
        sysctlbyname("hw.model", nil, &size, nil, 0)
        guard size > 0 else { return false }
        var buf = [CChar](repeating: 0, count: size)
        sysctlbyname("hw.model", &buf, &size, nil, 0)
        return String(cString: buf).contains("Book")
    }

    private var doneScreen: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(i18n.t("wizard.done_title")).dkFont(20, .bold)
            Text(i18n.t("wizard.done_body")).dkFont(14).foregroundStyle(.secondary)
        }
    }
}
