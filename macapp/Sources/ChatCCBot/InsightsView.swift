import SwiftUI

// Insights tab：诚实降级（跑现有 /stats）。空态有引导，banner 是 metric 卡，横条带底槽。
struct InsightsView: View {
    @EnvironmentObject var model: HubModel
    @EnvironmentObject var i18n: I18n

    private var hasData: Bool {
        (model.stats?.total ?? 0) > 0 || !(model.stats?.by_user.isEmpty ?? true)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if !hasData {
                    emptyState
                } else {
                    banner
                    if let s = model.stats, !topCallers(s).isEmpty {
                        barsSection(i18n.t("insights.most_active"), bars: topCallers(s))
                    }
                }
            }
            .padding(.horizontal, 18)
            .padding(.top, 16)
            .padding(.bottom, 18)
            .frame(maxWidth: .infinity, alignment: hasData ? .leading : .center)
        }
    }

    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: "tray").font(.system(size: 34)).foregroundStyle(.tertiary)
            Text(i18n.t("insights.empty_title")).dkFont(16, .semibold)
            Text(i18n.t(model.hasEnabledChannel ? "insights.empty_sub_waiting" : "insights.empty_sub"))
                .dkFont(13).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 70)
    }

    private var banner: some View {
        let s = model.stats
        let up = model.hubStatus?.uptime_sec ?? 0
        return VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 32) {
                metric("\(s?.total ?? 0)", i18n.t("insights.total_label"))
                metric(uptimeStr(up), i18n.t("insights.uptime_label"))
                Spacer()
                VStack(alignment: .trailing, spacing: 5) {
                    pill(.dkGreen, i18n.t("insights.ok", s?.ok ?? 0))
                    pill(.dkRed, i18n.t("insights.err", s?.err ?? 0))
                }
            }
            Text(i18n.t("insights.resets")).dkFont(11).foregroundStyle(.tertiary)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .dkCard()
    }

    private func metric(_ value: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value).dkFont(26, .bold).monospacedDigit()
            Text(label).dkFont(11).foregroundStyle(.secondary)
        }
    }

    private func pill(_ color: Color, _ text: String) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text(text).dkFont(12)
        }
        .padding(.horizontal, 8).padding(.vertical, 3)
        .background(color.opacity(0.14), in: Capsule())
    }

    private func topCallers(_ s: HubStats) -> [(String, Int)] {
        s.by_user
            .filter { !$0.key.hasPrefix("curl:") }
            .sorted { $0.value > $1.value }
            .prefix(6)
            .map { (friendlyName($0.key), $0.value) }
    }

    private func friendlyName(_ key: String) -> String {
        let parts = key.split(separator: ":", maxSplits: 1)
        guard parts.count == 2 else { return key }
        let chan = i18n.t("channel.\(parts[0]).name")
        let user = String(parts[1])
        let shortUser = user.count > 12 ? user.prefix(12) + "…" : Substring(user)
        return "\(chan) · \(shortUser)"
    }

    private func barsSection(_ title: String, bars: [(String, Int)]) -> some View {
        let maxV = max(bars.map { $0.1 }.max() ?? 1, 1)
        return VStack(alignment: .leading, spacing: 12) {
            Text(title).dkFont(15, .semibold)
            ForEach(bars, id: \.0) { name, v in
                HStack(spacing: 10) {
                    Text(name).dkFont(13).frame(width: 150, alignment: .leading).lineLimit(1)
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color.primary.opacity(0.06)).frame(height: 8)
                        GeometryReader { geo in
                            Capsule().fill(Color.dkAccent)
                                .frame(width: max(8, geo.size.width * CGFloat(v) / CGFloat(maxV)))
                        }
                        .frame(height: 8)
                    }
                    Text("\(v)").dkFont(13).monospacedDigit().frame(width: 40, alignment: .trailing)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .dkCard()
    }

    private func uptimeStr(_ sec: Int) -> String {
        if sec < 60 { return i18n.t("insights.just_started") }
        if sec >= 3600 { return "\(sec / 3600)h\(sec % 3600 / 60)m" }
        return "\(sec / 60)m"
    }
}
