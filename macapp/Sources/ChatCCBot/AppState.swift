import SwiftUI

// 全局 UI 状态：字体缩放比例（按比例算字号，macOS 上可靠生效）。
// Cmd +/-/0 调它；设置里滑杆也调它。默认 1.15 = 比基准大一点。
@MainActor
final class AppState: ObservableObject {
    // DK 有意不跟随系统 Dynamic Type，改提供 app 内等价缩放（Cmd +/- / 设置）。
    // 弱视常需 ≥200%：要提 maxScale 须先验证 680×520 主窗在该档下不溢出/截断，故暂守 150%。
    static let minScale: CGFloat = 0.8    // 80%
    static let maxScale: CGFloat = 1.5    // 150%（提上限前需做布局回归，见上）
    private static let prefKey = "DK.fontScale2"   // 换 key：忽略旧 slider 时代的非整值

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
        let raw = saved.map { CGFloat($0) } ?? 1.0   // 默认 100%
        scale = min(max((raw * 10).rounded() / 10, Self.minScale), Self.maxScale)
        keepAwake = (UserDefaults.standard.object(forKey: Self.awakeKey) as? Bool) ?? true
        applyAwake()   // init 里 didSet 不触发，手动应用一次
    }

    private func applyAwake() {
        keepAwake ? sleepGuard.enable() : sleepGuard.disable()
    }

    // 对齐到 10% 网格，永远落在整十百分比（90/100/110…）
    func bumpUp() { scale = min(((scale * 10).rounded() + 1) / 10, Self.maxScale) }
    func bumpDown() { scale = max(((scale * 10).rounded() - 1) / 10, Self.minScale) }
    func reset() { scale = 1.0 }
}
