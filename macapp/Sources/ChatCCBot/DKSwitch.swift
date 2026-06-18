import SwiftUI

// 自定义开关：用固定颜色（绿=开/灰=关），不随窗口失焦褪成灰（原生 .switch 会）。
struct DKSwitchStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        DKSwitchBody(configuration: configuration)
    }
}

// 抽成 View 才能拿 @Environment（ToggleStyle 自身拿不到）：减弱动效 / 增强对比 / 无障碍。
private struct DKSwitchBody: View {
    let configuration: ToggleStyleConfiguration
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        Button {
            configuration.isOn.toggle()
        } label: {
            ZStack(alignment: configuration.isOn ? .trailing : .leading) {
                Capsule()
                    .fill(configuration.isOn
                          ? Color(red: 0.20, green: 0.78, blue: 0.35)   // #34C759 绿
                          : Color.gray.opacity(0.45))
                    .frame(width: 42, height: 25)
                    .overlay(   // 增强对比时给关态描边：靠边框区分，不只靠灰度
                        Capsule().strokeBorder(
                            Color.primary.opacity(contrast == .increased && !configuration.isOn ? 0.6 : 0),
                            lineWidth: 1))
                Circle()
                    .fill(.white)
                    .frame(width: 21, height: 21)
                    .shadow(color: .black.opacity(0.18), radius: 1, y: 0.5)
                    .padding(2)
            }
        }
        .buttonStyle(.plain)
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.15), value: configuration.isOn)
        .accessibilityRepresentation {   // 把自绘开关暴露成标准 Toggle：读屏拿到角色+开关值+标签
            Toggle(isOn: configuration.$isOn) { configuration.label }
        }
    }
}
