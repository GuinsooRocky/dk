import SwiftUI

// 4 态一色一义（战略 §5.1）：connected / error / off / needs_setup（+ unknown 兜底）。
enum ChannelState {
    case connected, error, off, needsSetup, unknown

    init(_ raw: String) {
        switch raw {
        case "connected": self = .connected
        case "error": self = .error
        case "off": self = .off
        case "needs_setup": self = .needsSetup
        default: self = .unknown
        }
    }

    var color: Color {
        switch self {
        case .connected: return Color(red: 0.20, green: 0.78, blue: 0.35) // #34C759
        case .error: return Color(red: 1.00, green: 0.23, blue: 0.19)     // #FF3B30
        case .off: return Color(red: 0.56, green: 0.56, blue: 0.58)       // #8E8E93
        case .needsSetup: return Color(red: 0.35, green: 0.78, blue: 0.98) // #5AC8FA 青蓝
        case .unknown: return Color(red: 0.56, green: 0.56, blue: 0.58)
        }
    }

    var glyph: String {
        switch self {
        case .connected, .error: return "●"
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
        case .unknown: return "state.unknown"
        }
    }
}
