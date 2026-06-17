// swift-tools-version: 6.0
import PackageDescription

// chat-cc-bot 原生 macOS 控制面板（T2 骨架）。
// 现阶段以 SwiftPM 可执行目标存在，便于 `swift build` 验证编译；
// 后续打成签名 .app（LSUIElement 菜单栏 + 窗口、Sparkle 自更新）。
let package = Package(
    name: "ChatCCBot",
    platforms: [.macOS(.v15)],
    targets: [
        .executableTarget(
            name: "ChatCCBot",
            path: "Sources/ChatCCBot",
            resources: [.process("Resources")]
        )
    ]
)
