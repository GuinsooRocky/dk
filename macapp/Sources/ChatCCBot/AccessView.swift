import SwiftUI

// 「谁能用」：把改 .env 白名单的事搬进 app。
// 别人给 bot 发消息 → 出现在「想加入」→ 点加入（自动抓到 ID，免手填）；也支持手动加/移除。
struct AccessSection: View {
    @EnvironmentObject var model: HubModel
    @EnvironmentObject var i18n: I18n
    @State private var manualChannel = "telegram"
    @State private var manualId = ""
    @State private var showManual = false
    @FocusState private var manualFocused: Bool

    private let channels = ["telegram", "feishu", "wecom"]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(i18n.t("access.title")).dkFont(18, .bold)
            Text(i18n.t("access.hint")).dkFont(13).foregroundStyle(.secondary)

            if let pend = model.allowlist?.pending, !pend.isEmpty {
                Text(i18n.t("access.pending")).dkFont(14, .semibold).foregroundStyle(.secondary)
                ForEach(pend) { p in
                    HStack(spacing: 8) {
                        Circle().fill(Color(red: 0.35, green: 0.78, blue: 0.98)).frame(width: 7, height: 7)
                        Text("\(chanName(p.channel)) · \(p.user)").dkFont(13).lineLimit(1)
                        Text(i18n.t("access.just_messaged")).dkFont(12).foregroundStyle(.secondary)
                        Spacer()
                        Button(i18n.t("access.join")) {
                            Task { await model.editAllow(p.channel, p.user, "add") }
                        }.dkFont(13)
                    }
                }
            }

            Text(i18n.t("access.allowed")).dkFont(14, .semibold).foregroundStyle(.secondary)
            let pairs = allowedPairs()
            if pairs.isEmpty {
                Text(i18n.t("access.empty")).dkFont(13).foregroundStyle(.secondary)
            } else {
                ForEach(pairs) { item in
                    HStack(spacing: 8) {
                        Circle().fill(Color(red: 0.20, green: 0.78, blue: 0.35)).frame(width: 7, height: 7)
                        Text("\(chanName(item.channel)) · \(item.uid)").dkFont(13).lineLimit(1)
                        Spacer()
                        Button(i18n.t("access.remove")) {
                            Task { await model.editAllow(item.channel, item.uid, "remove") }
                        }.dkFont(13)
                    }
                }
            }

            // 手动添加：默认折叠成按钮，点了才展开输入框（平时无文本框→不抢焦点）
            if showManual {
                HStack(spacing: 8) {
                    Picker("", selection: $manualChannel) {
                        ForEach(channels, id: \.self) { Text(chanName($0)).tag($0) }
                    }
                    .labelsHidden().frame(width: 130)
                    TextField(i18n.t("access.manual"), text: $manualId)
                        .textFieldStyle(.roundedBorder)
                        .focused($manualFocused)
                    Button(i18n.t("access.add")) {
                        let id = manualId.trimmingCharacters(in: .whitespaces)
                        guard !id.isEmpty else { return }
                        Task { await model.editAllow(manualChannel, id, "add"); manualId = ""; showManual = false }
                    }
                    .disabled(manualId.trimmingCharacters(in: .whitespaces).isEmpty)
                    .dkFont(13)
                    Button(i18n.t("access.cancel")) { showManual = false; manualId = "" }.dkFont(13)
                }
                .padding(.top, 4)
            } else {
                Button {
                    showManual = true
                    DispatchQueue.main.async { manualFocused = true }
                } label: {
                    Label(i18n.t("access.manual"), systemImage: "plus")
                }
                .buttonStyle(.link)
                .dkFont(13)
                .padding(.top, 4)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func chanName(_ c: String) -> String { i18n.t("channel.\(c).name") }

    private struct Pair: Identifiable {
        let channel: String
        let uid: String
        var id: String { "\(channel):\(uid)" }
    }

    private func allowedPairs() -> [Pair] {
        guard let chans = model.allowlist?.channels else { return [] }
        var out: [Pair] = []
        for c in channels {
            for u in (chans[c] ?? []) { out.append(Pair(channel: c, uid: u)) }
        }
        return out
    }
}
