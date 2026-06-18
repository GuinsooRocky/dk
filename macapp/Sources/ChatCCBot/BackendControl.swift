import Foundation

// 用 launchctl 起/停后端守护（supervisor）。
// 守护 plist 的 KeepAlive 只在崩溃时重启，所以 kill TERM 是干净停止、不会被自动拉起；
// kickstart 把已注册但停着的服务再拉起。要求守护已 install（plist 存在）。
enum BackendControl {
    static let label = "com.lengmo.chatccbot"
    static var domainTarget: String { "gui/\(getuid())/\(label)" }

    static var installed: Bool {
        FileManager.default.fileExists(
            atPath: NSHomeDirectory() + "/Library/LaunchAgents/\(label).plist")
    }

    /// 开 DK 时拉起后端（已在跑则无副作用）。
    static func start() {
        guard installed else { return }
        run(["kickstart", domainTarget])
    }

    /// 退出 DK 时干净停后端。
    static func stop() {
        guard installed else { return }
        run(["kill", "TERM", domainTarget])
    }

    @discardableResult
    private static func run(_ args: [String]) -> Int32 {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        p.arguments = args
        p.standardOutput = Pipe()
        p.standardError = Pipe()
        do { try p.run() } catch { return -1 }
        p.waitUntilExit()
        return p.terminationStatus
    }
}
