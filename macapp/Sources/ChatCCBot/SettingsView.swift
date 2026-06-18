import SwiftUI
import AppKit

// Settings tab：扁平行（左=名+副标题，右=控件，控件统一右对齐）。
// 无标题（tab 已标"设置"）；可操作项在上，只读信息沉底。
struct SettingsView: View {
    @EnvironmentObject var model: HubModel
    @EnvironmentObject var i18n: I18n
    @EnvironmentObject var appState: AppState
    @StateObject private var claude = ClaudeCheck()

    @State private var proxyOn = false
    @State private var proxyPort = "7897"
    @State private var proxyLoaded = false
    @State private var tools: Set<String> = []
    @State private var toolsLoaded = false
    @State private var autostartOn = false
    @State private var disableSleepOn = false

    private let allTools = ["Read", "Glob", "Grep", "WebFetch", "Bash", "Write", "Edit"]
    private let writeTools = ["Bash", "Write", "Edit"]

    // 字体档 → 原生控件尺寸（macOS 控件无视 .font，只能用 controlSize 整体放大）
    private var dkControlSize: ControlSize {
        switch appState.scale {
        case ..<0.95: return .small
        case ..<1.15: return .regular
        case ..<1.35: return .large
        default: return .extraLarge
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                // 可操作设置
                cardWrap {
                    row(i18n.t("settings.language")) { langPicker }
                    div
                    row(i18n.t("settings.fontsize")) { fontControl }
                    div
                    row(i18n.t("settings.claude_status"), sub: claude.detail.isEmpty ? nil : claude.detail) { claudeControl }
                    div
                    row(i18n.t("settings.tools"), sub: i18n.t("settings.tools_sub")) { toolsMenu }
                    div
                    row(i18n.t("settings.proxy"), sub: i18n.t("settings.proxy_note")) { proxyControl }
                    div
                    row(i18n.t("settings.autostart"), sub: i18n.t("settings.autostart_sub")) { autostartToggle }
                    div
                    row(i18n.t("settings.persist"), sub: i18n.t("settings.persist_sub")) {
                        Toggle("", isOn: $appState.persistBackground).labelsHidden().toggleStyle(DKSwitchStyle())
                    }
                    div
                    row(i18n.t("settings.keepawake"), sub: i18n.t("settings.keepawake_note")) {
                        Toggle("", isOn: $appState.keepAwake).labelsHidden().toggleStyle(DKSwitchStyle())
                    }
                    div
                    row(i18n.t("settings.disablesleep"), sub: i18n.t("settings.disablesleep_note")) { disableSleepToggle }
                }

                Button(i18n.t("settings.open_log")) { openHubLog() }.dkFont(13)

                // 只读信息沉底
                Text(i18n.t("settings.info")).dkFont(12, .semibold)
                    .foregroundStyle(.secondary).padding(.top, 4).padding(.leading, 2)
                cardWrap {
                    row(i18n.t("settings.concurrency"), help: i18n.t("settings.concurrency_help")) {
                        Text(model.hubStatus.map { "\($0.max_concurrency ?? 1)" } ?? "—").dkFont(14, .medium)
                    }
                    div
                    row(i18n.t("settings.port"), help: i18n.t("settings.port_help")) {
                        Text("\(HubApi.port())").dkFont(14, .medium)
                    }
                }
            }
            .padding(.horizontal, 18)
            .padding(.top, 16)
            .padding(.bottom, 18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .controlSize(dkControlSize)   // 按钮/选择器等原生控件随字体档放大（.dkFont 对它们无效）
        }
        .task {
            // 这些读取内部是阻塞式 fork 子进程(PlistBuddy/pmset)，丢后台线程，别卡主线程
            let (a, s) = await Task.detached { (Autostart.isOn(), DisableSleep.isOn()) }.value
            autostartOn = a; disableSleepOn = s
            await claude.quickCheck()
        }
        .onAppear { syncProxyOnce(); syncToolsOnce() }
        .onChange(of: model.hubStatus?.proxy) { _, _ in syncProxyOnce() }
        .onChange(of: model.hubStatus?.tools) { _, _ in syncToolsOnce() }
    }

    // MARK: 控件

    private var langPicker: some View {
        Picker("", selection: Binding(get: { i18n.lang }, set: { i18n.setLang($0) })) {
            Text("中文").tag("zh"); Text("English").tag("en")
        }.pickerStyle(.segmented).labelsHidden().frame(width: 170)
    }

    private var fontControl: some View {
        HStack(spacing: 6) {
            Button { appState.bumpDown() } label: {
                Image(systemName: "minus").dkFont(13).frame(width: 16 * appState.scale, height: 14 * appState.scale)
            }
            .buttonStyle(.bordered).disabled(appState.scale <= AppState.minScale + 0.001)
            Text("\(Int((appState.scale * 100).rounded()))%")
                .dkFont(13).monospacedDigit().lineLimit(1).fixedSize()   // 不换行
            Button { appState.bumpUp() } label: {
                Image(systemName: "plus").dkFont(13).frame(width: 16 * appState.scale, height: 14 * appState.scale)
            }
            .buttonStyle(.bordered).disabled(appState.scale >= AppState.maxScale - 0.001)
            Button(i18n.t("settings.reset")) { appState.reset() }.dkFont(13)
        }
    }

    private var claudeControl: some View {
        HStack(spacing: 8) {
            Image(systemName: claude.state.symbol).dkFont(14).foregroundStyle(claudeColor)
            Text(i18n.t(claude.state.titleKey)).dkFont(13)
            Button(i18n.t("setup.recheck")) { Task { await claude.quickCheck() } }.dkFont(13)
            Button(i18n.t("setup.verify_login")) { Task { await claude.verifyLogin() } }.dkFont(13)
        }
    }

    private var claudeColor: Color {
        switch claude.state {
        case .ok: return .dkGreen
        case .notInstalled: return .dkRed
        case .notLoggedIn: return .orange
        case .checking: return Color.secondary
        }
    }

    private var toolsMenu: some View {
        Menu {
            ForEach(allTools, id: \.self) { t in
                Button { toggleTool(t) } label: {
                    Label(t, systemImage: tools.contains(t) ? "checkmark" : "")
                }
            }
        } label: {
            HStack(spacing: 4) {
                Text(toolsSummary).dkFont(13)
                Image(systemName: "chevron.up.chevron.down").font(.caption2).foregroundStyle(.secondary)
            }
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
    }

    private var proxyControl: some View {
        HStack(spacing: 8) {
            TextField("7897", text: $proxyPort)
                .frame(width: 84).textFieldStyle(.roundedBorder).disabled(!proxyOn)
            Button(i18n.t("settings.proxy_apply")) {
                Task { await model.setProxy(proxyOn, port: Int(proxyPort) ?? 7897) }
            }.dkFont(13)
            Toggle("", isOn: $proxyOn).labelsHidden().toggleStyle(DKSwitchStyle())
        }
    }

    private var autostartToggle: some View {
        Toggle("", isOn: Binding(get: { autostartOn }, set: { v in
            autostartOn = v
            Task.detached { Autostart.set(v) }   // 阻塞式写 plist，丢后台
        })).labelsHidden().toggleStyle(DKSwitchStyle()).disabled(!Autostart.available())
    }

    private var disableSleepToggle: some View {
        Toggle("", isOn: Binding(get: { disableSleepOn }, set: { v in
            Task { @MainActor in
                let ok = await Task.detached { DisableSleep.set(v) }.value
                disableSleepOn = ok ? v : DisableSleep.isOn()
            }
        })).labelsHidden().toggleStyle(DKSwitchStyle())
    }

    private var toolsSummary: String {
        let ordered = allTools.filter { tools.contains($0) }
        if ordered.isEmpty { return "—" }
        let hasWrite = ordered.contains { writeTools.contains($0) }
        return "\(i18n.t("settings.tools_count", ordered.count)) · \(hasWrite ? i18n.t("settings.haswrite") : i18n.t("settings.readonly"))"
    }

    private func toggleTool(_ t: String) {
        if tools.contains(t) { tools.remove(t) } else { tools.insert(t) }
        let joined = allTools.filter { tools.contains($0) }.joined(separator: ",")
        Task { await model.setTools(joined) }
    }

    // MARK: 行布局

    private var div: some View { DKHairline() }

    private func cardWrap<C: View>(@ViewBuilder _ content: () -> C) -> some View {
        VStack(spacing: 0) { content() }
            .padding(.horizontal, 14)
            .dkCard()
    }

    private func row<Control: View>(_ title: String, sub: String? = nil, help: String? = nil,
                                    @ViewBuilder control: () -> Control) -> some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text(title).dkFont(14, .medium)
                    if let help {
                        Image(systemName: "questionmark.circle").foregroundStyle(.secondary).help(help)
                    }
                }
                if let sub { Text(sub).dkFont(12).foregroundStyle(.secondary) }
            }
            Spacer(minLength: 12)
            control()
        }
        .padding(.vertical, 10)
    }

    // MARK: 同步

    private func syncProxyOnce() {
        guard !proxyLoaded, let p = model.hubStatus?.proxy else { return }
        proxyOn = !p.isEmpty
        if let port = p.split(separator: ":").last, Int(port) != nil { proxyPort = String(port) }
        proxyLoaded = true
    }

    private func syncToolsOnce() {
        guard !toolsLoaded, let t = model.hubStatus?.tools else { return }
        tools = Set(t.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty })
        toolsLoaded = true
    }

    private func openHubLog() {
        let url = URL(fileURLWithPath: NSHomeDirectory() + "/claude-hub-workdir/.logs/hub.log")
        NSWorkspace.shared.open(url)
    }
}
