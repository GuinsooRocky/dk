import SwiftUI

// 退役中：被 WizardView 多步向导取代作引导入口（§4.1，W1 起）。暂留不删——
// GuideBlock 的三渠道加机器人说明 W2 的连接步会复用，删了可惜（no-auto-delete）。
// 说明 tab：真文档。简介 + 三个渠道各自的加机器人步骤（整块可点展开）。
struct OnboardingView: View {
    @EnvironmentObject var i18n: I18n

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                card {
                    Text(i18n.t("guide.intro_title")).dkFont(20, .bold)
                    Text(i18n.t("guide.intro")).dkFont(14).foregroundStyle(.secondary)
                }

                GuideBlock(titleKey: "guide.telegram_title", stepsKey: "guide.telegram_steps")
                GuideBlock(titleKey: "guide.feishu_title", stepsKey: "guide.feishu_steps")
                GuideBlock(titleKey: "guide.wecom_title", stepsKey: "guide.wecom_steps")
            }
            .padding(.horizontal, 18)
            .padding(.top, 14)
            .padding(.bottom, 18)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func card(@ViewBuilder _ content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: 8) { content() }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
            .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
    }
}

// 整块可点展开/收起的指南块。
private struct GuideBlock: View {
    @EnvironmentObject var i18n: I18n
    let titleKey: String
    let stepsKey: String
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.18)) { expanded.toggle() }
            } label: {
                HStack {
                    Text(i18n.t(titleKey)).dkFont(16, .bold)
                    Spacer()
                    Image(systemName: "chevron.right")
                        .foregroundStyle(.secondary)
                        .rotationEffect(.degrees(expanded ? 90 : 0))
                }
                .contentShape(Rectangle())   // 整行可点
            }
            .buttonStyle(.plain)

            if expanded {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(steps.enumerated()), id: \.offset) { _, line in
                        stepRow(line)
                    }
                }
                .padding(.top, 10)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
    }

    // 把 "1. …\n2. …" 拆成清单：编号行带紫色徽章，注释行(注：/提示)带 ⓘ —— 软化多步骤(B6)
    private var steps: [String] {
        i18n.t(stepsKey).split(separator: "\n", omittingEmptySubsequences: true).map(String.init)
    }

    @ViewBuilder
    private func stepRow(_ raw: String) -> some View {
        let line = raw.trimmingCharacters(in: .whitespaces)
        if let dot = line.firstIndex(of: "."), let n = Int(line[line.startIndex..<dot]) {
            HStack(alignment: .top, spacing: 8) {
                Text("\(n)").dkFont(11, .bold)
                    .frame(width: 18, height: 18)
                    .background(Circle().fill(Color.dkAccent.opacity(0.15)))
                    .foregroundStyle(Color.dkAccent)
                Text(line[line.index(after: dot)...].trimmingCharacters(in: .whitespaces))
                    .dkFont(14).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        } else {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "info.circle").dkFont(12).foregroundStyle(.tertiary).frame(width: 18)
                Text(line).dkFont(13).foregroundStyle(.tertiary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}
