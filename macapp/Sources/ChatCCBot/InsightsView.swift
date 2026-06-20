import SwiftUI

// 用量 tab（B4）：过去 7 天持久化数据（SQLite，跨重启存活）——
// 总览 + 最活跃的人(条形) + 按渠道 + 每日趋势。数据来自 /stats/insights。
struct InsightsView: View {
    @EnvironmentObject var model: HubModel
    @EnvironmentObject var i18n: I18n

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DKSpace.lg) {
                summaryCard
                if let ins = model.insights, ins.total > 0 {
                    barsCard(i18n.t("insights.most_active"), ins.by_user, .dkAccent, topN: 5, shorten: true)
                    barsCard(i18n.t("insights.by_channel"), ins.by_channel, .dkGreen, topN: 4, shorten: false)
                    trendCard(ins.per_day)
                } else {
                    emptyCard
                }
            }
            .padding(.horizontal, DKSpace.lg).padding(.vertical, DKSpace.lg)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var summaryCard: some View {
        let ins = model.insights
        let up = model.hubStatus?.uptime_sec ?? 0
        return HStack(spacing: DKSpace.xl) {
            metric("\(ins?.total ?? 0)", i18n.t("insights.total_label"))
            metric(uptimeStr(up), i18n.t("insights.uptime_label"))
            Spacer()
            HStack(spacing: DKSpace.sm) {
                pill(.dkGreen, i18n.t("insights.ok", ins?.ok ?? 0))
                pill(.dkRed, i18n.t("insights.err", ins?.err ?? 0))
            }
        }
        .padding(DKSpace.lg).frame(maxWidth: .infinity, alignment: .leading).dkCard()
    }

    private func barsCard(_ title: String, _ data: [String: Int], _ color: Color, topN: Int, shorten: Bool) -> some View {
        let items = Array(data.sorted { $0.value > $1.value }.prefix(topN))
        let maxV = items.map(\.value).max() ?? 1
        return VStack(alignment: .leading, spacing: DKSpace.sm) {
            Text(title).dkFont(12, .semibold).foregroundStyle(.secondary)
            ForEach(items, id: \.key) { k, v in
                bar(shorten ? shortId(k) : channelName(k), v, maxV, color)
            }
        }
        .padding(DKSpace.lg).frame(maxWidth: .infinity, alignment: .leading).dkCard()
    }

    private func trendCard(_ perDay: [String: Int]) -> some View {
        let days = Array(perDay.sorted { $0.key < $1.key })
        let maxV = days.map(\.value).max() ?? 1
        return VStack(alignment: .leading, spacing: DKSpace.sm) {
            Text(i18n.t("insights.by_day")).dkFont(12, .semibold).foregroundStyle(.secondary)
            HStack(alignment: .bottom, spacing: 6) {
                ForEach(days, id: \.key) { k, v in
                    VStack(spacing: 3) {
                        Text("\(v)").dkFont(9).foregroundStyle(.tertiary).monospacedDigit()
                        RoundedRectangle(cornerRadius: 3).fill(Color.dkAccent.opacity(0.7))
                            .frame(width: 24, height: max(3, 46 * CGFloat(v) / CGFloat(maxV)))
                        Text(String(k.suffix(5))).dkFont(9).foregroundStyle(.tertiary)   // MM-DD
                    }
                }
                Spacer(minLength: 0)
            }
        }
        .padding(DKSpace.lg).frame(maxWidth: .infinity, alignment: .leading).dkCard()
    }

    private var emptyCard: some View {
        VStack(alignment: .leading, spacing: DKSpace.xs) {
            Text(i18n.t("insights.empty_title")).dkFont(15, .semibold)
            Text(model.hasEnabledChannel ? i18n.t("insights.empty_sub_waiting") : i18n.t("insights.empty_sub"))
                .dkFont(13).foregroundStyle(.secondary)
        }
        .padding(DKSpace.lg).frame(maxWidth: .infinity, alignment: .leading).dkCard()
    }

    // MARK: 小件
    private func metric(_ v: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(v).dkFont(20, .bold).monospacedDigit()
            Text(label).dkFont(11).foregroundStyle(.secondary)
        }
    }
    private func pill(_ c: Color, _ t: String) -> some View {
        HStack(spacing: 4) { Circle().fill(c).frame(width: 6, height: 6); Text(t).dkFont(12) }
            .padding(.horizontal, 8).padding(.vertical, 3).background(c.opacity(0.14), in: Capsule())
    }
    private func bar(_ label: String, _ value: Int, _ maxV: Int, _ color: Color) -> some View {
        HStack(spacing: DKSpace.sm) {
            Text(label).dkFont(12).foregroundStyle(.secondary)
                .frame(width: 100, alignment: .leading).lineLimit(1).truncationMode(.middle)
            GeometryReader { geo in
                RoundedRectangle(cornerRadius: 4).fill(color.opacity(0.7))
                    .frame(width: max(4, geo.size.width * CGFloat(value) / CGFloat(max(1, maxV))), height: 14)
            }.frame(height: 14)
            Text("\(value)").dkFont(12, .medium).monospacedDigit().frame(width: 34, alignment: .trailing)
        }
    }
    private func uptimeStr(_ sec: Int) -> String {
        if sec < 60 { return i18n.t("insights.just_started") }
        if sec >= 3600 { return "\(sec / 3600)h\(sec % 3600 / 60)m" }
        return "\(sec / 60)m"
    }
    private func shortId(_ s: String) -> String { s.count > 12 ? "…" + s.suffix(8) : s }
    private func channelName(_ key: String) -> String { i18n.t("channel.\(key).name") }
}
