import Foundation

// Claude 就绪检测（onboarding 第一道坎）：装没装 + 登录没。
// --version 证明装了；`claude -p ok` 探针证明登录可用（多数流程漏掉这步）。
enum ClaudeReadiness {
    case checking, ok, notInstalled, notLoggedIn

    var titleKey: String {
        switch self {
        case .checking: return "claude.checking"
        case .ok: return "claude.ok"
        case .notInstalled: return "claude.not_installed"
        case .notLoggedIn: return "claude.not_logged_in"
        }
    }

    var symbol: String {
        switch self {
        case .checking: return "circle.dashed"
        case .ok: return "checkmark.circle.fill"
        case .notInstalled: return "xmark.circle.fill"
        case .notLoggedIn: return "exclamationmark.triangle.fill"
        }
    }
}

@MainActor
final class ClaudeCheck: ObservableObject {
    @Published var state: ClaudeReadiness = .checking
    @Published var detail = ""
    @Published var path = ""

    /// 轻检：只 --version（证明装了）。
    func quickCheck() async {
        state = .checking
        guard let p = Self.resolveClaude() else {
            state = .notInstalled
            detail = "在 ~/.local/bin、/opt/homebrew/bin 等处没找到 claude。装：见 claude.com/code"
            return
        }
        path = p
        let r = await Self.run(p, ["--version"], timeout: 10)
        if r.code == 0 {
            state = .ok
            detail = r.out.trimmingCharacters(in: .whitespacesAndNewlines) + "（登录状态点下方按钮验证）"
        } else {
            state = .notInstalled
            detail = "claude --version 失败：\(r.err)"
        }
    }

    /// 重检：真跑一次 `claude -p ok` 探登录（会发一次请求，用户点按钮才跑）。
    func verifyLogin() async {
        guard let p = path.isEmpty ? Self.resolveClaude() : path else {
            state = .notInstalled; return
        }
        state = .checking
        let r = await Self.run(p, ["-p", "ok"], timeout: 40)
        if r.code == 0 {
            state = .ok; detail = "登录可用，能正常应答。"
        } else {
            state = .notLoggedIn
            detail = r.err.isEmpty ? "探针失败：可能未登录或无可用套餐。终端跑 claude 登录后重试。" : r.err
        }
    }

    static func resolveClaude() -> String? {
        let home = NSHomeDirectory()
        let candidates = [
            "\(home)/.local/bin/claude",
            "/opt/homebrew/bin/claude",
            "/usr/local/bin/claude",
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    struct Res { let code: Int32; let out: String; let err: String }

    /// 非阻塞跑子进程（terminationHandler + continuation，不卡主线程）。
    static func run(_ exe: String, _ args: [String], timeout: TimeInterval) async -> Res {
        await withCheckedContinuation { cont in
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: exe)
            proc.arguments = args
            let o = Pipe(), e = Pipe()
            proc.standardOutput = o
            proc.standardError = e
            proc.terminationHandler = { p in
                let out = String(data: o.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                let err = String(data: e.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                cont.resume(returning: Res(code: p.terminationStatus, out: out, err: err))
            }
            do {
                try proc.run()
            } catch {
                cont.resume(returning: Res(code: -1, out: "", err: "\(error)"))
                return
            }
            DispatchQueue.global().asyncAfter(deadline: .now() + timeout) {
                if proc.isRunning { proc.terminate() }
            }
        }
    }
}
