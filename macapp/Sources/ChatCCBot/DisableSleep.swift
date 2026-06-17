import Foundation

// 「合盖也不休眠」高级开关：走 `pmset -a disablesleep`（系统级，连合盖都不睡）。
// 改它要管理员权限 → 用 osascript 弹系统密码框。⚠️ 开了务必插电+别塞包（没散热会过热）。
enum DisableSleep {

    /// 当前是否已禁用睡眠（读 pmset -g 的 SleepDisabled）。
    static func isOn() -> Bool {
        let out = shell("/usr/bin/pmset", ["-g"])
        for raw in out.split(separator: "\n") {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.lowercased().hasPrefix("sleepdisabled") {
                return line.split(whereSeparator: { $0 == " " || $0 == "\t" }).last == "1"
            }
        }
        return false
    }

    /// 设置（弹密码授权）。返回 true=成功；false=用户取消或失败。阻塞，调用方丢后台。
    static func set(_ on: Bool) -> Bool {
        let cmd = "/usr/bin/pmset -a disablesleep \(on ? "1" : "0")"
        let script = "do shell script \"\(cmd)\" with administrator privileges"
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        p.arguments = ["-e", script]
        p.standardOutput = Pipe()
        p.standardError = Pipe()
        do { try p.run() } catch { return false }
        p.waitUntilExit()
        return p.terminationStatus == 0
    }

    private static func shell(_ exe: String, _ args: [String]) -> String {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: exe)
        p.arguments = args
        let out = Pipe()
        p.standardOutput = out
        p.standardError = Pipe()
        do { try p.run() } catch { return "" }
        p.waitUntilExit()
        return String(data: out.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    }
}
