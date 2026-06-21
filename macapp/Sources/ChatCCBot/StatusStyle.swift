import SwiftUI

// 状态一色一义：connected / error / off / needs_setup / connecting（+ unknown 兜底）。
// connecting = 进程在跑但久未收到心跳（连接没确认上），区别于真"在线"。
enum ChannelState {
    case connected, error, off, needsSetup, connecting, authFailed, unknown

    init(_ raw: String) {
        switch raw {
        case "connected": self = .connected
        case "error": self = .error
        case "off": self = .off
        case "needs_setup": self = .needsSetup
        case "connecting": self = .connecting
        default: self = .unknown
        }
    }

    var color: Color {
        switch self {
        case .connected: return Color(red: 0.20, green: 0.78, blue: 0.35) // #34C759
        case .error: return Color(red: 1.00, green: 0.23, blue: 0.19)     // #FF3B30
        case .off: return Color(red: 0.56, green: 0.56, blue: 0.58)       // #8E8E93
        case .needsSetup: return Color(red: 0.35, green: 0.78, blue: 0.98) // #5AC8FA 青蓝
        case .connecting: return Color(red: 1.00, green: 0.58, blue: 0.00) // #FF9500 橙：没确认连上
        case .authFailed: return Color(red: 0.63, green: 0.47, blue: 0.00) // #A07800 暗金：连得上但认证失效（亮/暗底都达标，原 #FFCC00 白底隐形）
        case .unknown: return Color(red: 0.56, green: 0.56, blue: 0.58)
        }
    }

    var glyph: String {
        switch self {
        case .connected, .error: return "●"
        case .connecting: return "◐"
        case .authFailed: return "▲"
        case .off: return "○"
        case .needsSetup: return "◌"
        case .unknown: return "◍"
        }
    }

    var labelKey: String {
        switch self {
        case .connected: return "state.connected"
        case .error: return "state.error"
        case .off: return "state.off"
        case .needsSetup: return "state.needs_setup"
        case .connecting: return "state.connecting"
        case .authFailed: return "state.auth_failed"
        case .unknown: return "state.unknown"
        }
    }
}
