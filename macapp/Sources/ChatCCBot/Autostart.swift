import Foundation

// 开机自启开关：读/写守护 LaunchAgent plist 的 RunAtLoad（改完下次登录生效，不打断当前服务）。
enum Autostart {
    static let plistPath = NSHomeDirectory() + "/Library/LaunchAgents/com.lengmo.chatccbot.plist"

    static func available() -> Bool {
        FileManager.default.fileExists(atPath: plistPath)
    }

    static func isOn() -> Bool {
        run(["-c", "Print :RunAtLoad", plistPath])
            .trimmingCharacters(in: .whitespacesAndNewlines) == "true"
    }

    static func set(_ on: Bool) {
        _ = run(["-c", "Set :RunAtLoad \(on ? "true" : "false")", plistPath])
    }

    @discardableResult
    private static func run(_ args: [String]) -> String {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/libexec/PlistBuddy")
        p.arguments = args
        let out = Pipe()
        p.standardOutput = out
        p.standardError = Pipe()
        do { try p.run() } catch { return "" }
        p.waitUntilExit()
        return String(data: out.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    }
}
