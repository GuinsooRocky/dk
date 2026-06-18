import SwiftUI
import AppKit

// DK —— 原生控制面板入口。菜单栏常驻 + 主窗口；Info.plist 设 LSUIElement=1 隐藏 Dock。
// DK 是后端的总开关：启动拉起后端，退出停掉（除非「后台常驻」开着）。
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ note: Notification) {
        BackendControl.start()
    }
    func applicationWillTerminate(_ note: Notification) {
        if !UserDefaults.standard.bool(forKey: "DK.persistBackground") {
            BackendControl.stop()
        }
    }
}

@main
struct ChatCCBotApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
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
            CommandGroup(after: .windowList) {
                Button("打开 DK") {   // Cmd+O 把主窗拉到前台（窗口存在时；菜单栏「打开」走 openWindow 可重建）
                    NSApp.activate(ignoringOtherApps: true)
                    NSApp.windows.first(where: { $0.canBecomeMain })?.makeKeyAndOrderFront(nil)
                }
                .keyboardShortcut("o", modifiers: .command)
            }
        }

        MenuBarExtra {
            MenuBarContent()
                .environmentObject(model)
                .environmentObject(i18n)
        } label: {
            Image(systemName: model.menuSymbol).accessibilityLabel(i18n.t("a11y.menubar"))
        }
        .menuBarExtraStyle(.window)   // 自控样式：彩色状态点 + 不置灰
    }
}
