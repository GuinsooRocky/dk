#!/usr/bin/env bash
# 把 hub + 四渠道 SDK + core 用 PyInstaller 打成单 sidecar（A1）。
# 产物：build/dist/dk_sidecar/（onedir）。被 macapp/build_app.sh 塞进 .app/Contents/Resources。
#   用法: bash build_sidecar.sh
set -euo pipefail
cd "$(dirname "$0")"
REPO="$PWD"

VENV="$REPO/build/sidecar-venv"
STAGE="$REPO/build/stage"
DIST="$REPO/build/dist"

# 本机系统 CA 坏 → pip 用一个 certifi 干净证书包（与 supervisor/_find_certifi 同款）
CACERT="$(find "$REPO" -path '*/certifi/cacert.pem' -not -path '*/build/*' 2>/dev/null | head -1)"

echo "[1/4] build venv（首次装依赖较久，之后复用）"
if [ ! -x "$VENV/bin/python" ]; then
  python3.12 -m venv "$VENV"
  "$VENV/bin/python" -m pip install -q --cert "$CACERT" --upgrade pip
  "$VENV/bin/python" -m pip install -q --cert "$CACERT" -r "$REPO/requirements.txt" pyinstaller
fi
"$VENV/bin/python" -c "import telegram, lark_oapi, wecom_aibot_sdk, fastapi, uvicorn" \
  && echo "  ✓ 依赖齐"

echo "[2/4] stage 渠道脚本到中性目录（躲 telegram/ 与 PyPI telegram 命名冲突）"
rm -rf "$STAGE"; mkdir -p "$STAGE"
cp "$REPO/telegram/telegram_bot.py" \
   "$REPO/feishu-claude/feishu_ws_server.py" "$REPO/feishu-claude/feishu_common.py" \
   "$REPO/wecom/wecom_ws_server.py" "$STAGE/"

echo "[3/4] PyInstaller 打包"
rm -rf "$DIST" "$REPO/build/pyi"
SSL_CERT_FILE="$CACERT" "$VENV/bin/pyinstaller" --onedir --noconfirm --clean \
  --name dk_sidecar --distpath "$DIST" --workpath "$REPO/build/pyi" \
  --specpath "$REPO/build" \
  --paths "$REPO" --paths "$STAGE" \
  --hidden-import supervisor --hidden-import hub.app \
  --hidden-import telegram_bot --hidden-import feishu_ws_server \
  --hidden-import feishu_common --hidden-import wecom_ws_server \
  --collect-submodules lark_oapi --collect-submodules wecom_aibot_sdk \
  "$REPO/sidecar.py" 2>&1 | tail -4

echo "[4/4] 校验：badmode 能跑"
"$DIST/dk_sidecar/dk_sidecar" badmode 2>&1 | head -1 || true
echo "✅ sidecar 产物：build/dist/dk_sidecar/dk_sidecar（$(du -sh "$DIST/dk_sidecar" | cut -f1)）"
