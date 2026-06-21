import SwiftUI

// 「监听」tab：被出站通知监听的 Claude 会话——看监听了哪些、各投哪个渠道、注销，
// 以及「纳管新 session」(浏览本机最近会话→选渠道→注册，替代命令行 watch register)。
struct MonitorView: View {
    @EnvironmentObject var model: HubModel
    @EnvironmentObject var i18n: I18n
    @Environment(\.dkScale) private var scale
    @State private var showAdd = false

    private var rows: [(String, NotifyRoute)] {
        model.notifyRoutes
            .sorted { ($0.value.registered_at ?? 0) > ($1.value.registered_at ?? 0) }
            .map { ($0.key, $0.value) }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DKSpace.lg) {
                header
                if rows.isEmpty {
                    emptyState
                } else {
                    ForEach(rows, id: \.0) { sid, route in
                        routeCard(sid, route)
                            .padding(DKSpace.lg)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .dkCard()
                    }
                }
            }
            .padding(.horizontal, DKSpace.lg).padding(.vertical, DKSpace.lg)
            .controlSize(dkControlSize(scale))
        }
        .task { await model.refresh() }
        .sheet(isPresented: $showAdd) { AddSessionSheet() }
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(i18n.t("monitor.header")).dkFont(20, .bold)
                Text(i18n.t("monitor.sub")).dkFont(12).foregroundStyle(.secondary)
            }
            Spacer()
            Button { showAdd = true } label: {
                Label(i18n.t("monitor.add"), systemImage: "plus")
            }.disabled(!model.reachable)
        }
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: DKSpace.sm) {
            Text(i18n.t("monitor.empty")).dkFont(14, .medium)
            Text(i18n.t("monitor.empty_hint")).dkFont(13).foregroundStyle(.secondary)
        }
        .padding(DKSpace.lg).frame(maxWidth: .infinity, alignment: .leading).dkCard()
    }

    private func routeCard(_ sid: String, _ route: NotifyRoute) -> some View {
        HStack(spacing: DKSpace.md) {
            Image(systemName: channelSymbol(route.channel)).font(.title3).frame(width: 26)
            VStack(alignment: .leading, spacing: DKSpace.xxs) {
                Text(route.cwd ?? sid).dkFont(14, .medium).lineLimit(1).truncationMode(.middle)
                HStack(spacing: 6) {
                    Text("●").foregroundStyle(Color.dkGreen)
                    Text(statusLine(route)).foregroundStyle(.secondary)
                }.dkFont(13)
            }
            Spacer()
            Button(i18n.t("monitor.unregister")) {
                Task { await model.unregisterNotify(sid) }
            }.controlSize(.small).disabled(!model.reachable)
        }
    }

    private func statusLine(_ r: NotifyRoute) -> String {
        let chan = r.channel == "telegram" ? "Telegram" : (r.channel == "feishu" ? i18n.t("channel.feishu.name") : r.channel)
        if let n = r.notified_count, n > 0 {
            return chan + " · " + i18n.t("monitor.notified", n)
        }
        return chan + " · " + i18n.t("monitor.watching")
    }

    private func channelSymbol(_ c: String) -> String {
        KNOWN_CHANNELS.first { $0.key == c }?.symbol ?? "bell.fill"
    }
}

// 纳管新 session：浏览本机最近会话 → 选一个 → 选渠道（TG 填 chat_id）→ 注册。
private struct AddSessionSheet: View {
    @EnvironmentObject var model: HubModel
    @EnvironmentObject var i18n: I18n
    @Environment(\.dismiss) private var dismiss
    @State private var sessions: [RecentSession] = []
    @State private var loading = true
    @State private var picked: RecentSession?
    @State private var channel = "feishu"
    @State private var target = ""

    var body: some View {
        VStack(alignment: .leading, spacing: DKSpace.md) {
            Text(i18n.t("monitor.add_title")).dkFont(16, .bold)
            Text(i18n.t("monitor.pick_hint")).dkFont(12).foregroundStyle(.secondary)

            if loading {
                ProgressView().frame(maxWidth: .infinity)
            } else if sessions.isEmpty {
                Text(i18n.t("monitor.no_sessions")).dkFont(13).foregroundStyle(.secondary)
            } else {
                ScrollView {
                    VStack(spacing: 4) {
                        ForEach(sessions) { s in sessionRow(s) }
                    }
                }.frame(maxHeight: 220)
            }

            if picked != nil {
                Divider()
                Picker(i18n.t("monitor.channel"), selection: $channel) {
                    Text(i18n.t("channel.feishu.name")).tag("feishu")
                    Text("Telegram").tag("telegram")
                }.pickerStyle(.segmented)
                if channel == "telegram" {
                    TextField(i18n.t("monitor.tg_target"), text: $target).textFieldStyle(.roundedBorder)
                }
            }

            HStack {
                Button(i18n.t("monitor.cancel")) { dismiss() }
                Spacer()
                Button(i18n.t("monitor.confirm_add")) {
                    guard let p = picked else { return }
                    let ch = channel, tg = target
                    Task { await model.registerNotify(p.session_id, p.cwd, ch, tg); dismiss() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(picked == nil || (channel == "telegram" && target.trimmingCharacters(in: .whitespaces).isEmpty))
            }
        }
        .padding(DKSpace.lg).frame(width: 440)
        .task {
            sessions = await model.recentSessions(30).filter { !$0.registered }   // 已纳管的不再列
            loading = false
        }
    }

    private func sessionRow(_ s: RecentSession) -> some View {
        Button {
            picked = (picked?.session_id == s.session_id) ? nil : s
        } label: {
            HStack(spacing: 8) {
                Image(systemName: picked?.session_id == s.session_id ? "largecircle.fill.circle" : "circle")
                    .foregroundStyle(picked?.session_id == s.session_id ? Color.dkAccent : .secondary)
                Text(s.cwd.isEmpty ? s.session_id : s.cwd).dkFont(13).lineLimit(1).truncationMode(.middle)
                Spacer()
                Text(String(s.last_activity.prefix(16)).replacingOccurrences(of: "T", with: " "))
                    .dkFont(11).foregroundStyle(.tertiary)
            }
            .contentShape(Rectangle())
            .padding(.horizontal, DKSpace.sm).padding(.vertical, DKSpace.xs)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(picked?.session_id == s.session_id ? [.isSelected] : [])
    }
}
