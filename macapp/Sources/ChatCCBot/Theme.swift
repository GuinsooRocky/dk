import SwiftUI

// ============================================================
// DK 设计规范（8pt 网格 + macOS HIG）
// 原则：① 所有间距从 DKSpace 取，不写裸数字；
//      ② 越相关越紧（标题↔副标 2-4，功能区之间 16-24）；
//      ③ 层级靠颜色不靠间距：primary 名/标题、secondary 副标/状态/ID/值、tertiary 空态/提示；
//      ④ macOS 15 用"填充+描边"卡片（Liquid Glass 是 macOS 26 Tahoe，本机用不了）。
// ============================================================

enum DKSpace {
    static let xxs: CGFloat = 2     // 标题 ↔ 紧贴副标（最相关）
    static let xs:  CGFloat = 4     // 行内极紧（图标↔字形）
    static let sm:  CGFloat = 8     // 行内常规 / 图标↔文字 / 副标行内
    static let md:  CGFloat = 12    // 列表行垂直 padding / label↔控件
    static let lg:  CGFloat = 16    // 卡片内 padding / 区块之间
    static let xl:  CGFloat = 24    // 不同功能区之间

    static let childIndent: CGFloat = 38   // 主子集缩进（图标 26 + gap 12，对齐渠道名）
    static let cardRadius: CGFloat = 12
}

// 实体卡片：填充 + 描边（暗色下有边界不飘）。
extension View {
    func dkCard(_ radius: CGFloat = DKSpace.cardRadius) -> some View {
        self
            .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: radius))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(Color.primary.opacity(0.10), lineWidth: 1)
            )
    }

    // 紧凑胶囊：用于"值 + 删除"这类标签（仿原生 token/tag）。
    func dkChip() -> some View {
        self
            .padding(.leading, 10).padding(.trailing, 7).padding(.vertical, 4)
            .background(Capsule().fill(Color.primary.opacity(0.06)))
    }

    // 扩大命中区到至少 size（HIG：交互元素别太小，glyph 可小但热区要够）。
    func dkHit(_ size: CGFloat = 22) -> some View {
        self.frame(minWidth: size, minHeight: size).contentShape(Rectangle())
    }
}

// 细分隔线（hairline）。
struct DKHairline: View {
    var inset: CGFloat = 0
    var body: some View {
        Rectangle()
            .fill(Color.primary.opacity(0.08))
            .frame(height: 1)
            .padding(.leading, inset)
    }
}

// 品牌色
extension Color {
    static let dkAccent = Color(red: 0.49, green: 0.36, blue: 1.0)   // #7C5CFF 紫
    static let dkGreen = Color(red: 0.20, green: 0.78, blue: 0.35)   // #34C759
    static let dkRed = Color(red: 1.0, green: 0.23, blue: 0.19)      // #FF3B30
}
