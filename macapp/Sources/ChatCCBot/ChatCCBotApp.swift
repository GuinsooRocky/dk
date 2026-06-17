import SwiftUI
import AppKit

// DK —— 原生控制面板入口。菜单栏常驻 + 主窗口；Info.plist 设 LSUIElement=1 隐藏 Dock。
@main
struct ChatCCBotApp: App {
    @StateObject private var model = HubModel()
    @StateObject private var i18n = I18n()
    @StateObject private var appState = AppState()

    var body: some Scene {
        Window("DK", id: "main") {
            MainView()
                .environmentObject(model)
                .environmentObject(i18n)
                .environmentObject(appState)
                .frame(minWidth: 680, minHeight: 520)
        }
        .windowResizability(.contentSize)
        .defaultLaunchBehavior(.presented)
        .commands {
            CommandGroup(after: .toolbar) {
                Button("放大字体") { appState.bumpUp() }
                    .keyboardShortcut("+", modifiers: .command)
                Button("放大字体 ") { appState.bumpUp() }
                    .keyboardShortcut("=", modifiers: .command)   // 多数键盘上 Cmd+= 即放大
                Button("缩小字体") { appState.bumpDown() }
                    .keyboardShortcut("-", modifiers: .command)
                Button("默认字体") { appState.reset() }
                    .keyboardShortcut("0", modifiers: .command)
            }
        }

        MenuBarExtra {
            MenuBarContent()
                .environmentObject(model)
                .environmentObject(i18n)
        } label: {
            Image(systemName: model.menuSymbol)
        }
    }
}
