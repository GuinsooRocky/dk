import SwiftUI

// 渠道面板（主子集）：用量摘要 + 各渠道，每个渠道下挂自己的「谁能用」ID。
// 合并了原「用量」tab 和独立的「渠道 ID 配置」段——渠道与 ID 本就是主子集关系。
struct ChannelsView: View {
    @EnvironmentObject var model: HubModel
    @EnvironmentObject var i18n: I18n
    @Environment(\.dkScale) private var scale

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DKSpace.lg) {
                header
                brainBanner
                usageCard
                channelList
            }
            .padding(.horizontal, DKSpace.lg).padding(.vertical, DKSpace.lg)
            .controlSize(dkControlSize(scale))   // 渠道里的按钮也随字体档放大
        }
    }

    private var header: some View {
        HStack {
            Text(i18n.t("channels.header")).dkFont(20, .bold)
            Spacer()
            Text(model.lastError != nil
                 ? i18n.t(model.lastError!)
                 : (model.reachable ? i18n.t("channels.readonly_safe") : i18n.t("channels.backend_down")))
                .dkFont(13)
                .foregroundStyle((model.lastError != nil || !model.reachable) ? Color.primary : Color.secondary)   // 错误态文字用 primary 提对比；菜单栏警告图标+文案本身仍标错
        }
    }

    // 大脑离线：真诊断（看代理配没配），不猜
    @ViewBuilder private var brainBanner: some View {
        if model.hubStatus?.claude_reachable == false {
            let proxied = !(model.hubStatus?.proxy ?? "").isEmpty
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.red)
                Text(i18n.t(proxied ? "brain.offline_proxy" : "brain.offline_direct"))
                    .dkFont(13).foregroundStyle(.primary)   // 文字改中性色提对比；红图标+红底仍标警示，颜色不单独承载语义
                Spacer()
            }
            .padding(.vertical, 8).padding(.horizontal, 10)
            .background(RoundedRectangle(cornerRadius: 8).fill(Color.red.opacity(0.10)))
        }
    }

    // 用量摘要：过去 7 天持久化数据（SQLite，跨重启存活）。B4。
    private var usageCard: some View {
        let ins = model.insights
        let up = model.hubStatus?.uptime_sec ?? 0
        let top = ins?.by_user.max { $0.value < $1.value }
        return VStack(alignment: .leading, spacing: DKSpace.sm) {
            HStack(spacing: DKSpace.xl) {
                usageMetric("\(ins?.total ?? 0)", i18n.t("insights.total_label"))
                usageMetric(uptimeStr(up), i18n.t("insights.uptime_label"))
                Spacer()
                HStack(spacing: DKSpace.sm) {
                    usagePill(.dkGreen, i18n.t("insights.ok", ins?.ok ?? 0))
                    usagePill(.dkRed, i18n.t("insights.err", ins?.err ?? 0))
                }
            }
            if let top, top.value > 0 {
                Text("\(i18n.t("insights.most_active")) · \(shortId(top.key)) · \(top.value)")
                    .dkFont(11).foregroundStyle(.tertiary)
            }
        }
        .padding(DKSpace.lg)
        .frame(maxWidth: .infinity, alignment: .leading)
        .dkCard()
    }

    private func shortId(_ s: String) -> String {
        s.count > 10 ? "…" + s.suffix(6) : s
    }

    private func usageMetric(_ v: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(v).dkFont(20, .bold).monospacedDigit()
            Text(label).dkFont(11).foregroundStyle(.secondary)
        }
    }

    private func usagePill(_ c: Color, _ t: String) -> some View {
        HStack(spacing: 4) {
            Circle().fill(c).frame(width: 6, height: 6)
            Text(t).dkFont(12)
        }
        .padding(.horizontal, 8).padding(.vertical, 3).background(c.opacity(0.14), in: Capsule())
    }

    private func uptimeStr(_ sec: Int) -> String {
        if sec < 60 { return i18n.t("insights.just_started") }
        if sec >= 3600 { return "\(sec / 3600)h\(sec % 3600 / 60)m" }
        return "\(sec / 60)m"
    }

    // 每个渠道独立成卡片（填充+描边，与用量卡一致），卡片间留间距
    private var channelList: some View {
        VStack(spacing: DKSpace.md) {
            ForEach(model.channelRows) { row in
                ChannelBlock(row: row)
                    .padding(DKSpace.lg)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .dkCard()
            }
            weChatRow
                .padding(DKSpace.lg)
                .frame(maxWidth: .infinity, alignment: .leading)
                .dkCard()
        }
    }

    private var weChatRow: some View {
        HStack(spacing: DKSpace.md) {
            Image(systemName: WECHAT_META.symbol).font(.title3).frame(width: 26)
            VStack(alignment: .leading, spacing: DKSpace.xxs) {
                Text(i18n.t(WECHAT_META.nameKey)).dkFont(14, .medium)
                Text(i18n.t(WECHAT_META.noteKey)).dkFont(13).foregroundStyle(.secondary)
            }
            Spacer()
            Text(i18n.t("channels.wechat_unavailable")).dkFont(13).foregroundStyle(.secondary)
        }
        .opacity(0.55)
    }
}

// 单个渠道块：主行（图标·名·状态·开关）+ 子集（这个渠道下「谁能用」的 ID）。
private struct ChannelBlock: View {
    @EnvironmentObject var model: HubModel
    @EnvironmentObject var i18n: I18n
    let row: ChannelDisplay
    @State private var showAdd = false
    @State private var newId = ""
    @State private var pendingAddId: String?
    @FocusState private var addFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: DKSpace.sm) {
            HStack(spacing: DKSpace.md) {
                Image(systemName: row.meta.symbol).font(.title3).frame(width: 26)
                VStack(alignment: .leading, spacing: DKSpace.xs) {
                    Text(i18n.t(row.meta.nameKey)).dkFont(14, .medium)
                    HStack(spacing: 6) {
                        Text(row.state.glyph).foregroundStyle(row.state.color)
                        Text(subLabel).foregroundStyle(.secondary)
                    }.dkFont(13)
                    if let err = row.status?.last_error, !err.isEmpty {
                        Text(err).dkFont(12).foregroundStyle(.red).lineLimit(2)
                    }
                }
                Spacer()
                Toggle(i18n.t(row.meta.nameKey), isOn: Binding(
                    get: { model.isEnabled(row.meta.key) },
                    set: { v in Task { await model.setEnabled(row.meta.key, v) } }
                ))
                .labelsHidden().toggleStyle(DKSwitchStyle()).disabled(!model.reachable)
            }

            childIds   // 子集：这个渠道下的 ID（缩进，主子集关系）
        }
        .alert(i18n.t("access.confirm_title"),
               isPresented: Binding(get: { pendingAddId != nil },
                                    set: { if !$0 { pendingAddId = nil } })) {
            Button(i18n.t("access.cancel"), role: .cancel) { pendingAddId = nil }
            Button(i18n.t("access.join")) {
                if let id = pendingAddId {
                    Task { await model.editAllow(row.meta.key, id, "add") }
                }
                pendingAddId = nil
            }
        } message: {
            Text(consentMessage)
        }
    }

    // 加人前的授权告知：按当前工具档动态措辞 + 数据留存知情(GUARD-4/6)。
    private var consentMessage: String {
        let tools = model.hubStatus?.tools ?? ""
        var msg = i18n.t("access.confirm_read")
        if tools.contains("Bash") || tools.contains("Write") || tools.contains("Edit") {
            msg += i18n.t("access.confirm_write")
        }
        msg += "\n" + i18n.t("access.confirm_data")
        return msg
    }

    private var childIds: some View {
        VStack(alignment: .leading, spacing: DKSpace.sm) {
            // 已允许：成员行（user 图标 + ID + ×），不是 tag
            ForEach(allowedHere, id: \.self) { uid in
                idRow(uid)
            }
            // 想加入（发过消息但还没放行）：等待图标 + ID + 加入
            ForEach(pendingHere) { p in
                HStack(spacing: DKSpace.sm) {
                    Image(systemName: "person.crop.circle.badge.clock").dkFont(13)
                        .foregroundStyle(Color(red: 0.35, green: 0.78, blue: 0.98))
                    Text(p.user).dkFont(12).lineLimit(1).truncationMode(.middle)
                    Spacer(minLength: DKSpace.sm)
                    Button(i18n.t("access.join")) {
                        pendingAddId = p.user   // 先弹授权告知，确认后才加(GUARD-4)
                    }.controlSize(.small)
                }
                .padding(.horizontal, DKSpace.md).padding(.vertical, DKSpace.xs)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 8)
                    .fill(Color(red: 0.35, green: 0.78, blue: 0.98).opacity(0.10)))
            }
            if allowedHere.isEmpty && pendingHere.isEmpty {
                Text(i18n.t("access.empty_channel")).dkFont(12).foregroundStyle(.tertiary)
            }
            // 添加 ID
            if showAdd {
                HStack(spacing: 6) {
                    TextField(i18n.t("access.manual"), text: $newId)
                        .textFieldStyle(.roundedBorder).focused($addFocused).frame(maxWidth: 240)
                    Button(i18n.t("access.add")) {
                        let id = newId.trimmingCharacters(in: .whitespaces)
                        guard !id.isEmpty else { return }
                        newId = ""; showAdd = false
                        pendingAddId = id   // 先弹授权告知，确认后才加(GUARD-4)
                    }.disabled(newId.trimmingCharacters(in: .whitespaces).isEmpty)
                    Button(i18n.t("access.cancel")) { showAdd = false; newId = "" }
                }
            } else {
                Button {
                    showAdd = true
                    DispatchQueue.main.async { addFocused = true }
                } label: {
                    Label(i18n.t("access.add_person"), systemImage: "plus")
                }.buttonStyle(.link)
            }
        }
        .padding(.leading, DKSpace.childIndent)
        .overlay(alignment: .leading) {   // 树形连接线，体现"渠道→ID"主子集
            Rectangle().fill(Color.primary.opacity(0.10))
                .frame(width: 1).padding(.leading, 13).padding(.vertical, 1)
        }
    }

    // 成员行：整行列表项（铺满宽度 + 行底色 + 内边距），一眼是渠道的子项，不是 tag
    private func idRow(_ uid: String) -> some View {
        HStack(spacing: DKSpace.sm) {
            Image(systemName: "person.crop.circle.fill").dkFont(13).foregroundStyle(.tertiary)
            Text(uid).dkFont(12).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
            Spacer(minLength: DKSpace.sm)
            Button {
                Task { await model.editAllow(row.meta.key, uid, "remove") }
            } label: {
                Image(systemName: "xmark").dkFont(10).foregroundStyle(.secondary).dkHit(22)
            }
            .buttonStyle(.plain).help(i18n.t("access.remove")).accessibilityLabel(i18n.t("access.remove"))
        }
        .padding(.horizontal, DKSpace.md).padding(.vertical, DKSpace.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.primary.opacity(0.06)))
    }

    private var subLabel: String {
        var parts = [i18n.t(row.state.labelKey)]
        if let r = row.status?.restarts, r > 0 { parts.append(i18n.t("channels.restarts", r)) }
        parts.append(i18n.t(row.meta.noteKey))
        return parts.joined(separator: " · ")
    }

    private var allowedHere: [String] { model.allowlist?.channels[row.meta.key] ?? [] }
    private var pendingHere: [PendingItem] {
        (model.allowlist?.pending ?? []).filter { $0.channel == row.meta.key }
    }
}
