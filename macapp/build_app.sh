#!/usr/bin/env bash
# 把 SwiftPM 可执行打成可双击的 ChatCCBot.app（菜单栏 accessory，无 Dock 图标），ad-hoc 签名。
# 本机自用够了。要「发给别人不被 Gatekeeper 拦」需 Apple Developer 证书做公证，见末尾 TODO。
#   用法: bash macapp/build_app.sh
set -euo pipefail
cd "$(dirname "$0")"

APP="dist/DK.app"
BIN_NAME="ChatCCBot"          # SwiftPM 产物名（不外露）
BUNDLE_ID="com.lengmo.dk"

echo "[1/4] release 编译"
swift build -c release
BINDIR="$(swift build -c release --show-bin-path)"
BIN="$BINDIR/$BIN_NAME"
[ -x "$BIN" ] || { echo "没编出 $BIN"; exit 1; }

echo "[2/4] 组装 .app bundle"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/$BIN_NAME"
# i18n 资源 bundle 放 Contents/Resources（Bundle.module 会在这找；放 MacOS 会让 codesign 当成代码 bundle 报错）
RESBUNDLE="$BINDIR/${BIN_NAME}_${BIN_NAME}.bundle"
[ -d "$RESBUNDLE" ] && cp -R "$RESBUNDLE" "$APP/Contents/Resources/" && echo "  + 已塞入 i18n 资源 bundle"
# 应用图标（没有就先跑 bash macapp/make_icon.sh 生成）
[ -f AppIcon.icns ] && cp AppIcon.icns "$APP/Contents/Resources/AppIcon.icns" && echo "  + 已塞入 DK 图标"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>DK</string>
  <key>CFBundleDisplayName</key><string>DK</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleExecutable</key><string>$BIN_NAME</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <!-- 菜单栏 accessory：隐藏 Dock 图标，无 Terminal、无僵尸窗口（战略 §4.2） -->
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

echo "[2.5/4] 打包并塞入 Python sidecar（hub+四渠道，A1）"
bash ../build_sidecar.sh
rm -rf "$APP/Contents/Resources/dk_sidecar"
cp -R ../build/dist/dk_sidecar "$APP/Contents/Resources/dk_sidecar"
# 嵌套二进制先内向外 ad-hoc 签（全是 code，可 --deep；不碰主 .app 的 i18n data bundle）
codesign --force --deep --sign - "$APP/Contents/Resources/dk_sidecar"
echo "  + 已塞入 sidecar（$(du -sh "$APP/Contents/Resources/dk_sidecar" | cut -f1)）"

echo "[3/4] ad-hoc 签名"
# 不用 --deep：资源 bundle 是数据不是代码，--deep 会误当代码 bundle 签名报错；
# 主 bundle 签名会把 Resources/ 一并封装校验。
codesign --force --sign - --options runtime "$APP"

echo "[4/4] 校验"
codesign --verify --verbose=1 "$APP"
echo "✅ 已生成并签名：macapp/$APP"
echo "   双击即可；首次被 Gatekeeper 拦就右键→打开。前提：后端守护在跑（./daemon/chatccbot.sh install）。"

# ── 公证（分发给别人，需 Apple Developer，$99/年）TODO ──
# 1) 换 Developer ID 证书替代 ad-hoc：
#    codesign --force --options runtime --sign "Developer ID Application: 你的名字 (TEAMID)" "$APP"
# 2) 打包提交公证：
#    ditto -c -k --keepParent "$APP" dist/ChatCCBot.zip
#    xcrun notarytool submit dist/ChatCCBot.zip --apple-id <你的AppleID> --team-id <TEAMID> --password <app专用密码> --wait
# 3) 装订票据：xcrun stapler staple "$APP"
# ── 还差：把 Python 后端（hub+渠道）用 PyInstaller 打成 sidecar 塞进 Contents/Resources，
#    并由 app 经 launchd 拉起，实现"只装这一个 .app"。当前 .app 只是控制面板，后端仍走 daemon。
