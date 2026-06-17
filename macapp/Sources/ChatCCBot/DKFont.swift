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

private struct DKFontModifier: ViewModifier {
    @Environment(\.dkScale) private var scale
    let base: CGFloat
    let weight: Font.Weight
    func body(content: Content) -> some View {
        content.font(.system(size: base * scale, weight: weight))
    }
}

extension View {
    func dkFont(_ base: CGFloat, _ weight: Font.Weight = .regular) -> some View {
        modifier(DKFontModifier(base: base, weight: weight))
    }
}
