import SwiftUI

// 应用状态：拉 /supervisor，合成成展示用的渠道行。
// M4 用一次性 refresh()；M6 在外面套 3s 轮询。
@MainActor
final class HubModel: ObservableObject {
    @Published var supervisor: SupervisorStatus?
    @Published var hubStatus: HubStatus?
    @Published var stats: HubStats?
    @Published var insights: Insights?   // 持久化用量(过去 7 天，跨重启)，B4
    @Published var allowlist: AllowlistResp?
    @Published var reachable = false   // 后端在跑且 ok:true 才为真（诚实降级用）
    @Published var busy = false        // hub 当前在跑 claude（菜单栏图标用）
    @Published var pending: [String: Bool] = [:]   // 开关乐观态：发请求到刷新前先显示目标值
    @Published var lastError: String?              // 最近一次写操作失败（i18n key），不再静默吞

    private var pollTask: Task<Void, Never>?
    private var pendingSeq: [String: Int] = [:]    // per-name 请求序号，防并发清空别人的乐观态

    init() {
        // 自启 3s 轮询，脱离视图生命周期 —— 菜单栏没开窗口也能反映状态。
        pollTask = Task { await startPolling() }
    }

    /// 菜单栏图标：没连上→警告；在忙→省略号；空闲→对话气泡。
    var menuSymbol: String {
        if !reachable { return "exclamationmark.triangle.fill" }
        return busy ? "ellipsis.bubble.fill" : "bubble.left.and.bubble.right.fill"
    }

    /// 点开关：乐观更新 → POST → 给 supervisor 重载时间 → 刷新真实状态。
    func setEnabled(_ name: String, _ on: Bool) async {
        lastError = nil
        let seq = (pendingSeq[name] ?? 0) + 1
        pendingSeq[name] = seq
        pending[name] = on
        do { try await HubApi.setChannelEnabled(name: name, enabled: on) }
        catch { lastError = "err.action_failed" }
        try? await Task.sleep(nanoseconds: 1_800_000_000)
        await refresh()
        if pendingSeq[name] == seq { pending[name] = nil }   // 只有最新点击才清乐观态，防并发闪回
    }

    func isEnabled(_ name: String) -> Bool {
        if let p = pending[name] { return p }
        return supervisor?.channels?.first { $0.name == name }?.enabled ?? false
    }

    /// 是否已接入任一渠道：用来区分空态文案（没接 vs 接了在等消息）。
    var hasEnabledChannel: Bool {
        supervisor?.channels?.contains { $0.enabled } ?? false
    }

    /// 改允许的工具：整体重启，多等一会。
    func setTools(_ tools: String) async {
        lastError = nil
        do { try await HubApi.setTools(tools) } catch { lastError = "err.action_failed" }
        try? await Task.sleep(nanoseconds: 7_000_000_000)
        await refresh()
    }

    /// 设代理端口后端整体重启较久，多等一会再刷新。
    func setProxy(_ on: Bool, port: Int) async {
        lastError = nil
        do { try await HubApi.setProxy(enabled: on, port: port) } catch { lastError = "err.action_failed" }
        try? await Task.sleep(nanoseconds: 7_000_000_000)
        await refresh()
    }

    func refresh() async {
        do {
            let s = try await HubApi.supervisor()
            supervisor = s
            reachable = s.ok        // supervisor 没起时 /supervisor 返回 ok:false → 不假装在线
        } catch {
            supervisor = nil
            reachable = false       // hub 都连不上
        }
        hubStatus = try? await HubApi.status()
        busy = hubStatus?.busy ?? false
        stats = try? await HubApi.stats()   // 用量；拉不到不影响渠道显示
        insights = try? await HubApi.insights()   // 持久化用量(过去 7 天)，B4
        allowlist = try? await HubApi.allowlist()
    }

    /// 加/移除白名单：改 .env + 重启该渠道，等一会再刷新。
    func editAllow(_ channel: String, _ id: String, _ action: String) async {
        lastError = nil
        do { try await HubApi.setAllow(channel: channel, id: id, action: action) }
        catch { lastError = "err.action_failed" }
        try? await Task.sleep(nanoseconds: 1_800_000_000)
        await refresh()
    }

    /// 向导粘贴凭证：写 config.toml [channel].field 后刷新（W2）。
    func setCred(_ channel: String, _ field: String, _ value: String) async {
        lastError = nil
        do { try await HubApi.setCred(channel: channel, field: field, value: value) }
        catch { lastError = "err.action_failed" }
        try? await Task.sleep(nanoseconds: 1_800_000_000)
        await refresh()
    }

    /// 清除历史：清空 hub 内存统计 + 刷新（GUARD-4）。
    func clearHistory() async {
        lastError = nil
        do { try await HubApi.clearStats() } catch { lastError = "err.action_failed" }
        await refresh()
    }

    /// 每 3s 拉一次（小 loop）；视图消失时 .task 被取消，循环自然退出。
    func startPolling(every seconds: UInt64 = 3) async {
        while !Task.isCancelled {
            await refresh()
            try? await Task.sleep(nanoseconds: seconds * 1_000_000_000)
        }
    }

    /// 已知渠道 + 后端返回状态 合成展示行（后端没返回的也列出来，标 unknown）。
    var channelRows: [ChannelDisplay] {
        let byName = Dictionary(
            uniqueKeysWithValues: (supervisor?.channels ?? []).map { ($0.name, $0) }
        )
        return KNOWN_CHANNELS.map { ChannelDisplay(meta: $0, status: byName[$0.key]) }
    }
}

struct ChannelDisplay: Identifiable {
    let meta: ChannelMeta
    let status: ChannelStatus?
    var id: String { meta.key }
    var state: ChannelState {
        guard let s = status else { return .unknown }
        // 进程连得上但鉴权失效（P1）→ 独立态「认证失效」，区别于进程 down
        if s.state == "connected" && s.auth_ok == false { return .authFailed }
        return ChannelState(s.state)
    }
}
