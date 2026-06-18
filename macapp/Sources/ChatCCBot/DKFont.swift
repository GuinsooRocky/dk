import SwiftUI

// 可靠的字体缩放：从环境读 scale，字号 = base × scale。
// 用法：Text("x").dkFont(14) / .dkFont(20, .bold)。根视图设 .environment(\.dkScale, appState.scale)。
private struct DKScaleKey: EnvironmentKey {
    static let defaultValue: CGFloat = 1.0
}

extension EnvironmentValues {
    var dkScale: CGFloat {
        get { self[DKScaleKey.self] }
        set { self[DKScaleKey.self] = newValue }
    }
}

// 渲染字号 = base × 1.12(舒适基准) × scale(用户缩放，默认 1.0 = 100%)。
// 1.12 让 100% 时就比系统默认大一点；scale 100% 即"默认"。
private let dkBaseline: CGFloat = 1.12

private struct DKFontModifier: ViewModifier {
    @Environment(\.dkScale) private var scale
    let base: CGFloat
    let weight: Font.Weight
    func body(content: Content) -> some View {
        content.font(.system(size: base * dkBaseline * scale, weight: weight))
    }
}

extension View {
    func dkFont(_ base: CGFloat, _ weight: Font.Weight = .regular) -> some View {
        modifier(DKFontModifier(base: base, weight: weight))
    }
}

// 字体档 → 原生控件尺寸：macOS 的 Button/Picker 无视 .font，只能用 controlSize 整体放大。
func dkControlSize(_ scale: CGFloat) -> ControlSize {
    switch scale {
    case ..<0.95: return .small
    case ..<1.15: return .regular
    case ..<1.35: return .large
    default: return .extraLarge
    }
}
