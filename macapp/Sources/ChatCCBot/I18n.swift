import SwiftUI

// 自建轻量 i18n：key → 字串，两份 JSON（zh / en），可切换、持久化。
// 不是完整 i18n 框架，但够维护：所有界面文案集中在 Resources/{zh,en}.json。
@MainActor
final class I18n: ObservableObject {
    @Published private(set) var lang: String
    private var dict: [String: String] = [:]
    private static let prefKey = "DK.lang"

    init() {
        let saved = UserDefaults.standard.string(forKey: Self.prefKey)
        let sysZh = Locale.preferredLanguages.first?.hasPrefix("zh") ?? false
        lang = saved ?? (sysZh ? "zh" : "en")
        dict = Self.loadDict(lang) ?? Self.loadDict("en") ?? [:]
    }

    func setLang(_ l: String) {
        guard l != lang, let d = Self.loadDict(l) else { return }
        dict = d
        UserDefaults.standard.set(l, forKey: Self.prefKey)
        lang = l   // @Published → 触发界面刷新（此时 dict 已更新）
    }

    /// 查 key；查不到回退到 key 本身（方便发现漏翻）。
    func t(_ key: String) -> String { dict[key] ?? key }

    /// 带格式化参数（如 "%d"）。
    func t(_ key: String, _ args: CVarArg...) -> String {
        String(format: dict[key] ?? key, arguments: args)
    }

    private static func loadDict(_ lang: String) -> [String: String]? {
        guard let url = Bundle.module.url(forResource: lang, withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let d = try? JSONDecoder().decode([String: String].self, from: data)
        else { return nil }
        return d
    }
}
