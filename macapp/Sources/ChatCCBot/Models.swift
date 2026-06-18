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

// MARK: - 渠道展示元数据（名称/定位走 i18n key，按 channel.<key>.name / .note 取）

struct ChannelMeta {
    let key: String      // telegram / feishu / wecom / wechat
    let symbol: String   // SF Symbol
    var nameKey: String { "channel.\(key).name" }
    var noteKey: String { "channel.\(key).note" }
}

let KNOWN_CHANNELS: [ChannelMeta] = [
    .init(key: "telegram", symbol: "paperplane.fill"),
    .init(key: "feishu", symbol: "bird.fill"),
    .init(key: "wecom", symbol: "building.2.fill"),
]

// 微信：故意做成禁用信息行（个人微信无安全接法，见战略 §6）
let WECHAT_META = ChannelMeta(key: "wechat", symbol: "bubble.left.fill")
