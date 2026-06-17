import SwiftUI

// 自定义开关：用固定颜色（绿=开/灰=关），不随窗口失焦褪成灰（原生 .switch 会）。
struct DKSwitchStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button {
            configuration.isOn.toggle()
        } label: {
            ZStack(alignment: configuration.isOn ? .trailing : .leading) {
                Capsule()
                    .fill(configuration.isOn
                          ? Color(red: 0.20, green: 0.78, blue: 0.35)   // #34C759 绿
                          : Color.gray.opacity(0.45))
                    .frame(width: 42, height: 25)
                Circle()
                    .fill(.white)
                    .frame(width: 21, height: 21)
                    .shadow(color: .black.opacity(0.18), radius: 1, y: 0.5)
                    .padding(2)
            }
        }
        .buttonStyle(.plain)
        .animation(.easeInOut(duration: 0.15), value: configuration.isOn)
    }
}
