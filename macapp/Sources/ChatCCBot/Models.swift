import SwiftUI

// MARK: - 后端 /supervisor /status /stats 的数据模型（对应 hub 的 JSON）

// 注：以下结构是后端 /supervisor /status /stats 的 JSON 契约镜像，
// 部分字段(ts/stale/reason、pid/last_rc/backoff、engine、busy/last_at/last_text、at)暂未在 UI 用，保留以兼容解码。
struct SupervisorStatus: Codable {
    var ok: Bool
    var ts: Double?
    var channels: [ChannelStatus]?
    var stale: Bool?
    var reason: String?
}

struct ChannelStatus: Codable, Identifiable {
    var name: String
    var enabled: Bool
    var state: String
    var pid: Int?
    var last_rc: Int?
    var restarts: Int?
    var backoff: Int?
    var last_error: String?
    var id: String { name }
}

struct HubStatus: Codable {
    var ok: Bool
    var uptime_sec: Int?
    var busy: Bool?
    var engine: String?
    var tools: String?
    var max_concurrency: Int?
    var proxy: String?
    var claude_reachable: Bool?   // 大脑可达：渠道连着也得这环通才答得了（nil=未知）
    var sandbox_verified: Bool?   // 沙箱是否真验证(GUARD-2)：写/全权工具安全的前提
}

struct AllowlistResp: Codable {
    var channels: [String: [String]]
    var pending: [PendingItem]
}

struct PendingItem: Codable, Identifiable {
    var channel: String
    var user: String
    var at: Double?
    var id: String { "\(channel):\(user)" }
}

struct HubStats: Codable {
    var total: Int
    var ok: Int
    var busy: Int
    var err: Int
    var by_user: [String: Int]
    var last_at: Double
    var last_text: String
}

// /stats/insights 的持久化用量（SQLite，过去 N 天，跨重启存活）。B4。
struct Insights: Codable {
    var days: Int
    var total: Int
    var ok: Int
    var err: Int
    var by_user: [String: Int]
    var by_channel: [String: Int]
    var per_day: [String: Int]
}

// MARK: - 渠道展示元数据（名称/定位走 i18n key，按 channel.<key>.name / .note 取）

struct ChannelMeta {
    let key: String      // telegram / feishu / wecom / wechat
    let symbol: String   // SF Symbol
    // 信任分级（T1，战略 §6.3 第三方插件生态预留）：safe / experimental。
    // v1 现有三渠道全 safe、不发任何 experimental。
    // ②ChannelsView 实验性分组 UI + ③config 段 trust_tier 透传：等真有 experimental 渠道再做
    //   （现无 experimental → 现状即「不显」，已满足；现在造分组 UI 是给不存在的态建设，故延期）。
    // 用 var 才能在 memberwise init 里显式传值（let+默认值会被排除在 init 外）；实例仍只读用。
    var trustTier: String = "safe"
    var nameKey: String { "channel.\(key).name" }
    var noteKey: String { "channel.\(key).note" }
}

let KNOWN_CHANNELS: [ChannelMeta] = [
    .init(key: "telegram", symbol: "paperplane.fill", trustTier: "safe"),
    .init(key: "feishu", symbol: "bird.fill", trustTier: "safe"),
    .init(key: "wecom", symbol: "building.2.fill", trustTier: "safe"),
]

// 微信：故意做成禁用信息行（个人微信无安全接法，见战略 §6）
let WECHAT_META = ChannelMeta(key: "wechat", symbol: "bubble.left.fill")
