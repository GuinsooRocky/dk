import SwiftUI

// Channels tab：渠道列表 + 微信禁用信息行（战略 §5.2 / §6）。
struct ChannelsView: View {
    @EnvironmentObject var model: HubModel
    @EnvironmentObject var i18n: I18n

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                header
                VStack(spacing: 0) {
                    ForEach(Array(model.channelRows.enumerated()), id: \.element.id) { idx, row in
                        if idx > 0 { separator }
                        ChannelRowView(row: row)
                    }
                    separator
                    weChatRow
                }

                Divider().padding(.top, 18).padding(.bottom, 12)
                AccessSection()
            }
            .padding(.horizontal, 18)
            .padding(.top, 14)
            .padding(.bottom, 18)
        }
    }

    private var separator: some View {
        Rectangle()
            .fill(Color.primary.opacity(0.06))
            .frame(height: 0.5)
            .padding(.leading, 36)
    }

    private var header: some View {
        HStack {
            Text(i18n.t("channels.header")).dkFont(20, .bold)
            Spacer()
            Text(model.reachable ? i18n.t("channels.readonly_safe") : i18n.t("channels.backend_down"))
                .dkFont(13)
                .foregroundStyle(model.reachable ? Color.secondary : Color.red)
        }
        .padding(.bottom, 10)
    }

    private var weChatRow: some View {
        HStack(spacing: 12) {
            Image(systemName: WECHAT_META.symbol).font(.title3).frame(width: 26)
            VStack(alignment: .leading, spacing: 2) {
                Text(i18n.t(WECHAT_META.nameKey)).dkFont(14, .medium)
                Text(i18n.t(WECHAT_META.noteKey)).dkFont(13).foregroundStyle(.secondary)
            }
            Spacer()
            Text(i18n.t("channels.wechat_unavailable")).dkFont(13).foregroundStyle(.secondary)
        }
        .padding(.vertical, 12)
        .opacity(0.55)
    }
}

private struct ChannelRowView: View {
    @EnvironmentObject var model: HubModel
    @EnvironmentObject var i18n: I18n
    let row: ChannelDisplay

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: row.meta.symbol).font(.title3).frame(width: 26)
            VStack(alignment: .leading, spacing: 3) {
                Text(i18n.t(row.meta.nameKey)).dkFont(14, .medium)
                HStack(spacing: 6) {
                    Text(row.state.glyph).foregroundStyle(row.state.color)
                    Text(subLabel).foregroundStyle(.secondary)
                }
                .dkFont(13)
                if let err = row.status?.last_error, !err.isEmpty {
                    Text(err).dkFont(12).foregroundStyle(.red).lineLimit(2)
                }
            }
            Spacer()
            Toggle("", isOn: Binding(
                get: { model.isEnabled(row.meta.key) },
                set: { newVal in Task { await model.setEnabled(row.meta.key, newVal) } }
            ))
            .labelsHidden()
            .toggleStyle(DKSwitchStyle())
            .disabled(!model.reachable)
        }
        .padding(.vertical, 12)
    }

    private var subLabel: String {
        var parts = [i18n.t(row.state.labelKey)]
        if let r = row.status?.restarts, r > 0 { parts.append(i18n.t("channels.restarts", r)) }
        parts.append(i18n.t(row.meta.noteKey))
        return parts.joined(separator: " · ")
    }
}
