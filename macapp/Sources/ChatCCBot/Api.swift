import Foundation

// MARK: - Hub 网络层：拉 /supervisor /status /stats（都在 127.0.0.1 本机）。

enum HubApi {

    /// hub 端口：优先 config.toml 的 [hub].port，读不到就默认 8787。
    static func port() -> Int {
        // dev 期 macapp/ 与后端同仓，config.toml 在仓库根（macapp 的上一级）。
        let cwd = FileManager.default.currentDirectoryPath
        let candidates = [
            URL(fileURLWithPath: cwd).appendingPathComponent("config.toml"),
            URL(fileURLWithPath: cwd).deletingLastPathComponent().appendingPathComponent("config.toml"),
            URL(fileURLWithPath: "\(NSHomeDirectory())/Desktop/my-code/dk/config.toml"),
        ]
        for url in candidates {
            if let text = try? String(contentsOf: url, encoding: .utf8),
               let p = parseHubPort(text) {
                return p
            }
        }
        return 8787
    }

    private static func parseHubPort(_ toml: String) -> Int? {
        var inHub = false
        for raw in toml.split(separator: "\n") {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("[") {
                inHub = (line == "[hub]")
                continue
            }
            if inHub, line.hasPrefix("port") {
                let rhs = line.split(separator: "=", maxSplits: 1).last?
                    .trimmingCharacters(in: .whitespaces)
                if let rhs, let p = Int(rhs) { return p }
            }
        }
        return nil
    }

    static func base() -> String { "http://127.0.0.1:\(port())" }

    /// 通用 GET + JSON 解码；3s 超时（本机服务，超时即视为没起）。
    static func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        guard let url = URL(string: base() + path) else { throw URLError(.badURL) }
        var req = URLRequest(url: url)
        req.timeoutInterval = 3
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    static func supervisor() async throws -> SupervisorStatus {
        try await get("/supervisor", as: SupervisorStatus.self)
    }
    static func status() async throws -> HubStatus {
        try await get("/status", as: HubStatus.self)
    }
    static func stats() async throws -> HubStats {
        try await get("/stats", as: HubStats.self)
    }

    struct ChannelToggle: Encodable { let name: String; let enabled: Bool }

    /// 开/关渠道：hub 改 config.toml + 让 supervisor 起/停对应进程。
    static func setChannelEnabled(name: String, enabled: Bool) async throws {
        try await post("/config/channel", ChannelToggle(name: name, enabled: enabled))
    }

    struct ProxyConfig: Encodable { let enabled: Bool; let port: Int }

    /// 设代理端口：勾选+端口走代理，否则直连。改完后端整体重启。
    static func setProxy(enabled: Bool, port: Int) async throws {
        try await post("/config/proxy", ProxyConfig(enabled: enabled, port: port))
    }

    struct ToolsConfig: Encodable { let tools: String }

    static func setTools(_ tools: String) async throws {
        try await post("/config/tools", ToolsConfig(tools: tools))
    }

    static func allowlist() async throws -> AllowlistResp {
        try await get("/allowlist", as: AllowlistResp.self)
    }

    struct AllowEdit: Encodable { let channel: String; let id: String; let action: String }

    static func setAllow(channel: String, id: String, action: String) async throws {
        try await post("/allowlist", AllowEdit(channel: channel, id: id, action: action))
    }

    private static func post<T: Encodable>(_ path: String, _ body: T) async throws {
        guard let url = URL(string: base() + path) else { throw URLError(.badURL) }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        req.timeoutInterval = 6
        let (_, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)   // 非 2xx 不再当成功（与 get() 一致）
        }
    }
}
