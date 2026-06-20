import SwiftUI

// §4.1 多步交互向导（取代静态 OnboardingView 作引导入口）。
// W1：状态机骨架 + Screen0 资格预检 + Step1 Claude 三态门。
// channel / connect / perms / runmode 四步本任务先占位，W2/W3 实装；视觉/流程留 visual-qa 人工收尾。
enum WizardStep: Int, CaseIterable {
    case eligibility, claude, channel, connect, perms, runmode, done
}

@MainActor
final class WizardModel: ObservableObject {
    @Published var step: WizardStep = .eligibility

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
    @Environment(\.openURL) private var openURL
    @StateObject private var wiz = WizardModel()
    @StateObject private var claude = ClaudeCheck()   // Step1 复用：检装没装 / 登没登

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(i18n.t("wizard.step_of", wiz.step.rawValue + 1, WizardStep.allCases.count))
                    .dkFont(12).foregroundStyle(.secondary)
                switch wiz.step {
                case .eligibility: eligibilityScreen
                case .claude: claudeScreen
                case .done: doneScreen
                default: placeholderScreen
                }
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
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

    // channel/connect/perms/runmode 占位（W2/W3 实装），保持向导可编译可导航
    private var placeholderScreen: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(i18n.t("wizard.building_title")).dkFont(18, .bold)
            Text(i18n.t("wizard.building_body")).dkFont(13).foregroundStyle(.secondary)
            HStack(spacing: 10) {
                Button(i18n.t("wizard.back")) { wiz.back() }
                Spacer()
                Button(i18n.t("wizard.next")) { wiz.next() }.buttonStyle(.borderedProminent)
            }
        }
    }

    private var doneScreen: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(i18n.t("wizard.done_title")).dkFont(20, .bold)
            Text(i18n.t("wizard.done_body")).dkFont(14).foregroundStyle(.secondary)
        }
    }
}
