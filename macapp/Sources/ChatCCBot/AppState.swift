import SwiftUI

// 全局 UI 状态：字体缩放比例（按比例算字号，macOS 上可靠生效）。
// Cmd +/-/0 调它；设置里滑杆也调它。默认 1.15 = 比基准大一点。
@MainActor
final class AppState: ObservableObject {
    static let minScale: CGFloat = 0.85
    static let maxScale: CGFloat = 1.6
    private static let prefKey = "DK.fontScale"

    private static let awakeKey = "DK.keepAwake"

    @Published var scale: CGFloat {
        didSet {
            let c = min(max(scale, Self.minScale), Self.maxScale)
            if c != scale { scale = c; return }      // 夹紧后会再触发一次 didSet，避免越界
            UserDefaults.standard.set(Double(scale), forKey: Self.prefKey)
        }
    }

    // 运行时保持 Mac 唤醒（默认开）。
    @Published var keepAwake: Bool {
        didSet {
            UserDefaults.standard.set(keepAwake, forKey: Self.awakeKey)
            applyAwake()
        }
    }

    // 后台常驻：默认关——退出 DK 时停后端；开了则退出后 bot 仍在线。
    @Published var persistBackground: Bool {
        didSet { UserDefaults.standard.set(persistBackground, forKey: "DK.persistBackground") }
    }

    private let sleepGuard = SleepGuard()

    init() {
        persistBackground = UserDefaults.standard.bool(forKey: "DK.persistBackground")
        let saved = UserDefaults.standard.object(forKey: Self.prefKey) as? Double
        scale = saved.map { CGFloat($0) } ?? 1.15
        keepAwake = (UserDefaults.standard.object(forKey: Self.awakeKey) as? Bool) ?? true
        applyAwake()   // init 里 didSet 不触发，手动应用一次
    }

    private func applyAwake() {
        keepAwake ? sleepGuard.enable() : sleepGuard.disable()
    }

    func bumpUp() { scale = min(scale + 0.1, Self.maxScale) }
    func bumpDown() { scale = max(scale - 0.1, Self.minScale) }
    func reset() { scale = 1.15 }
}
