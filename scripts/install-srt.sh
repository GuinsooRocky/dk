#!/bin/bash
# 装 srt（@anthropic-ai/sandbox-runtime）到一个**跟 node 版本解绑**的固定位置。
# bot 的外层沙箱靠它，见 SANDBOX.md「残留风险」。
#
# 为什么不用 `npm i -g`：
#   本机 node 是 nvm 管的，全局前缀 = ~/.nvm/versions/node/<版本>/。
#   升一次 node，全局包就没了 → 常驻 bot 静默失去沙箱（我们会 fail-closed 停机，但没必要）。
# 为什么不用 npx 缓存：
#   `npm cache clean` 或 npx 自己清理都会抹掉它。
# 为什么先写 package.json：
#   直接在空目录 `npm i` 会让 npm **往上找最近的 package.json**，实测会装进 ~/node_modules
#   并往 ~/package.json 里加依赖。目标目录自带 package.json 才能钉住它。
set -euo pipefail

VERSION="${SRT_VERSION:-0.0.66}"     # srt 是 beta，配置格式会变 → 钉死版本，升级要重跑探针
DEST="${SRT_HOME:-$HOME/.local/lib/srt}"

NODE="$(command -v node || true)"
[ -z "$NODE" ] && [ -x "$HOME/.local/bin/node" ] && NODE="$HOME/.local/bin/node"
if [ -z "$NODE" ]; then echo "✗ 找不到 node"; exit 2; fi
NODE="$(cd "$(dirname "$NODE")" && pwd)/$(basename "$NODE")"

echo "node    = $NODE ($("$NODE" --version))"
echo "装到    = $DEST"
echo "版本    = $VERSION"

mkdir -p "$DEST"
cat > "$DEST/package.json" <<EOF
{
  "name": "dk-srt-host",
  "private": true,
  "description": "跟 node 版本解绑的 srt 安装点，给 dk bot 的外层沙箱用。别在这儿开发。",
  "dependencies": { "@anthropic-ai/sandbox-runtime": "$VERSION" }
}
EOF

(cd "$DEST" && npm i --no-fund --no-audit)

CLI="$DEST/node_modules/@anthropic-ai/sandbox-runtime/dist/cli.js"
[ -f "$CLI" ] || { echo "✗ 装完没找到 cli.js：$CLI"; exit 1; }

# 冒烟：模拟 launchd 的最小 PATH。
# cli.js 的 shebang 是 `#!/usr/bin/env node`，launchd 下 PATH 里没有 node → shim 直接死。
# 所以 runner 必须用「绝对 node + 绝对 cli.js」调，不能调 .bin/srt。这里就按那个姿势验。
SMOKE=$(mktemp /tmp/dk-srt-smoke.XXXXXX)   # macOS 的 mktemp 要求 X 在模板末尾
trap 'rm -f "$SMOKE"' EXIT
cat > "$SMOKE" <<EOF
{"filesystem":{"denyRead":["$HOME/Desktop"],"allowRead":["."],"allowWrite":["/tmp"],"denyWrite":[]},
 "network":{"allowedDomains":[],"deniedDomains":[]}}
EOF
# 先取输出再判断：这条命令**本来就该非零退出**（越界 ls 失败正是我们要的），
# 直接 `... | grep -q` 会被 pipefail 判成失败。
SMOKE_OUT=$(env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin HOME="$HOME" \
              "$NODE" "$CLI" -s "$SMOKE" -c "ls $HOME/Desktop" 2>&1 || true)
if grep -q "Operation not permitted" <<<"$SMOKE_OUT"; then
  echo "✓ 冒烟通过（最小环境下沙箱真的拦住了越界读）"
else
  echo "✗ 冒烟失败：沙箱没拦住越界读，别接线"
  echo "  实际输出：$SMOKE_OUT"
  exit 1
fi

cat <<EOF

装好了。填进 hub/.env（或 config.toml）：

  DK_SRT_CLI=$CLI
  DK_SRT_NODE=$NODE

下一步跑端到端探针：bash scripts/outer-sandbox-probe.sh
EOF
