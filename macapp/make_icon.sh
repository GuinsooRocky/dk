#!/usr/bin/env bash
# 生成 DK 应用图标 AppIcon.icns（紫色 squircle + 白 DK）。用法：bash macapp/make_icon.sh
set -euo pipefail
cd "$(dirname "$0")"

PNG=/tmp/dk_1024.png
swift make_icon.swift "$PNG"

ICONSET=/tmp/DK.iconset
rm -rf "$ICONSET"; mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$PNG" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2))
  sips -z $d $d "$PNG" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o AppIcon.icns
echo "✅ AppIcon.icns 生成完成（$(du -h AppIcon.icns | cut -f1)）"
