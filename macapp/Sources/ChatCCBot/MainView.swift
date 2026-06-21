import SwiftUI

// 主窗口：顶部等宽分段 tab + 内容区。
// tab 顺序：渠道 → 监听 → 设置 → 说明（向导）。等宽避免中英切换时宽度跳动。
struct MainView: View {
    @EnvironmentObject var i18n: I18n
    @EnvironmentObject var appState: AppState
    @State private var tab = 0

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                SegTabs(selection: $tab, titles: [
                    i18n.t("tab.channels"),
                    i18n.t("tab.monitor"),
                    i18n.t("tab.settings"),
                    i18n.t("tab.setup"),
                ])
                Spacer()
            }
            .padding(.vertical, 12)

            Divider()

            Group {
                switch tab {
                case 0: ChannelsView()
                case 1: MonitorView()   // 监听：出站通知监听的会话（决策④推翻，UI 不能砍）
                case 2: SettingsView()
                default: WizardView()   // §4.1 多步向导取代静态 OnboardingView（W1 起）
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .environment(\.dkScale, appState.scale)   // 字体缩放作用整个 app（含顶部 tab 栏）
    }
}

// 等宽分段控件：每段固定宽度（中英一致），文字与宽度都跟随字体缩放。
private struct SegTabs: View {
    @Environment(\.dkScale) private var scale
    @Binding var selection: Int
    let titles: [String]

    var body: some View {
        HStack(spacing: 2) {
            ForEach(titles.indices, id: \.self) { i in
                Text(titles[i])
                    .dkFont(13, selection == i ? .semibold : .regular)
                    .foregroundStyle(selection == i ? Color.primary : Color.secondary)
                    .frame(width: 96 * scale, height: 30 * scale)
                    .background(
                        RoundedRectangle(cornerRadius: 7)
                            .fill(selection == i ? AnyShapeStyle(.regularMaterial) : AnyShapeStyle(Color.clear))
                    )
                    .contentShape(Rectangle())
                    .onTapGesture { selection = i }
            }
        }
        .padding(3)
        .background(RoundedRectangle(cornerRadius: 9).fill(Color.primary.opacity(0.08)))
    }
}
