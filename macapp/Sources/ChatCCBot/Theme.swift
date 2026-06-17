import SwiftUI

// 统一视觉：实体卡片（填充 + 描边，暗色下有边界不飘）+ hairline 分隔线。
extension View {
    func dkCard(_ radius: CGFloat = 10) -> some View {
        self
            .background(Color.primary.opacity(0.055), in: RoundedRectangle(cornerRadius: radius))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(Color.primary.opacity(0.12), lineWidth: 1)
            )
    }
}

// 细分隔线（从标题文字左缘起，hairline）。
struct DKHairline: View {
    var inset: CGFloat = 0
    var body: some View {
        Rectangle()
            .fill(Color.primary.opacity(0.09))
            .frame(height: 1)
            .padding(.leading, inset)
    }
}

// 紫色品牌色
extension Color {
    static let dkAccent = Color(red: 0.49, green: 0.36, blue: 1.0)   // #7C5CFF
    static let dkGreen = Color(red: 0.20, green: 0.78, blue: 0.35)   // #34C759
    static let dkRed = Color(red: 1.0, green: 0.23, blue: 0.19)      // #FF3B30
}
