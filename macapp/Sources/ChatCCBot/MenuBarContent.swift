import SwiftUI
import AppKit

// 菜单栏面板（.window 样式）：总状态 + 各渠道彩色圆点 + 打开/退出。
// 用 .window 而非 .menu —— .menu 会把文字置灰（"在线"却灰着反直觉）；.window 全自控样式。
struct MenuBarContent: View {
    @EnvironmentObject var model: HubModel
    @EnvironmentObject var i18n: I18n
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // 总状态：一眼看 bot 能不能用
            HStack {
                Text(overallText).dkFont(13, .medium)
                Spacer()
            }
            .padding(.horizontal, 14).padding(.top, 12).padding(.bottom, 10)

            Divider()

            // 渠道：彩色圆点 + 正常文字（不置灰）
            VStack(spacing: 0) {
                ForEach(model.channelRows) { row in
                    HStack(spacing: 8) {
                        Text(row.state.glyph).foregroundStyle(row.state.color).dkFont(13)
                        Text(i18n.t(row.meta.nameKey)).dkFont(13)
                        Spacer()
                        Text(i18n.t(row.state.labelKey)).dkFont(12).foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 14).padding(.vertical, 5)
                }
            }
            .padding(.vertical, 4)

            Divider()

            menuRow(i18n.t("app.open")) {
                NSApp.activate(ignoringOtherApps: true)   // 拉到前台，别让用户满屏找
                openWindow(id: "main")
            }
            menuRow(i18n.t("app.quit")) { NSApplication.shared.terminate(nil) }
            Spacer(minLength: 6)
        }
        .frame(width: 248)
        .environment(\.dkScale, 1.0)   // 菜单栏面板不跟随字体缩放
    }

    private var overallText: String {
        if !model.reachable { return i18n.t("status.offline") }
        if model.hubStatus?.claude_reachable == false { return i18n.t("status.brain_down") }
        if model.busy { return i18n.t("status.busy") }
        return i18n.t("status.online_idle")
    }

    private func menuRow(_ title: String, _ action: @escaping () -> Void) -> some View {
        MenuActionRow(title: title, action: action)
    }
}

// 可点行：hover 高亮，整行可点（像菜单项但不置灰）。
private struct MenuActionRow: View {
    let title: String
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            HStack { Text(title).dkFont(13); Spacer() }
                .contentShape(Rectangle())
                .padding(.horizontal, 14).padding(.vertical, 7)
                .background(hover ? Color.primary.opacity(0.10) : Color.clear)
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
    }
}
