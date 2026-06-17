import SwiftUI
import AppKit

// 菜单栏下拉：一眼看总状态 + 各渠道圆点 + 打开窗口 / 退出。
struct MenuBarContent: View {
    @EnvironmentObject var model: HubModel
    @EnvironmentObject var i18n: I18n
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        if model.reachable {
            Text(model.busy ? i18n.t("status.busy") : i18n.t("status.online_idle"))
        } else {
            Text(i18n.t("status.offline"))
        }

        Divider()

        ForEach(model.channelRows) { row in
            Text("\(row.state.glyph) \(i18n.t(row.meta.nameKey)) · \(i18n.t(row.state.labelKey))")
        }

        Divider()

        Button(i18n.t("app.open")) { openWindow(id: "main") }
        Button(i18n.t("app.quit")) { NSApplication.shared.terminate(nil) }
    }
}
