#!/bin/bash
# 给 bot 建一个独立的 CLAUDE_CONFIG_DIR。
#
# 为什么要独立：外层包裹一旦生效，claude 自己的 Read 工具就受 OS 边界管 —— 反过来说，
# allowRead 放进去的东西它**全都读得到**。共用 owner 的 ~/.claude 等于把
# ~/.claude/projects/ 里你**所有项目的完整会话记录**交给 bot（以及远程用它的人）。
#
# 换目录会掉登录态，因为认证是拆开的两半（实测）：
#   账号关联 → ~/.claude.json 的 oauthAccount 等字段
#   凭证本体 → macOS Keychain，服务名 "Claude Code-credentials"
# 只换目录、或只补账号字段，都会 `Not logged in`。两半都搬过去才行。
#
# 搬完的额外好处：凭证在 bot 自己目录里，沙箱**连 Keychain 都不用放行**。
set -euo pipefail

DEST="${1:-$HOME/.local/share/dk-botcfg}"
DEST="${DEST/#\~/$HOME}"

echo "bot 配置目录 = $DEST"
mkdir -p "$DEST"
chmod 700 "$DEST"

# 1) 账号关联：只搬这几个字段，不搬你的 MCP 配置、项目历史、onboarding 状态等
python3 - "$DEST/.claude.json" <<'PY'
import json, os, sys
src_path = os.path.expanduser("~/.claude.json")
if not os.path.exists(src_path):
    sys.exit(f"✗ 找不到 {src_path} —— owner 这台机器登录过 claude 吗？")
src = json.load(open(src_path))
KEEP = ("userID", "oauthAccount", "hasAvailableSubscription", "claudeCodeFirstTokenDate")
out = {k: src[k] for k in KEEP if k in src}
if "oauthAccount" not in out:
    sys.exit("✗ owner 的 ~/.claude.json 里没有 oauthAccount —— 先在 owner 侧登录一次")
out["hasCompletedOnboarding"] = True
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=2)
print("✓ 账号字段已播种:", ", ".join(out))
PY

# 2) 凭证本体：从 Keychain 取出落盘。直接重定向，别经 stdout（免得进日志/终端回滚）
if ! security find-generic-password -s "Claude Code-credentials" -w \
       > "$DEST/.credentials.json" 2>/dev/null; then
  rm -f "$DEST/.credentials.json"
  echo "✗ 取不到 Keychain 凭证（授权框被拒？或 owner 没登录过）"
  exit 1
fi
chmod 600 "$DEST/.credentials.json"
python3 -c "
import json,sys
d=json.load(open('$DEST/.credentials.json'))
assert 'claudeAiOauth' in d, '凭证结构不对，没有 claudeAiOauth'
print('✓ 凭证已落盘（过期时间字段:', 'expiresAt' in d['claudeAiOauth'], '）')"

cat <<EOF

建好了。填进 hub/.env（或 config.toml）：

  DK_BOT_CONFIG_DIR=$DEST

⚠ 两件必须一起做的事：

1. srt 配置的 allowRead / allowWrite 都要包含 ${DEST}，
   否则 bot 起不来（沙箱把它自己的配置目录挡在外面了）。

2. claude 的 --settings 里加一条 permissions.deny，挡住 bot 用 Read 工具读自己的凭证：

     "permissions": { "deny": ["Read(//$DEST/**)"] }

   实测这条**不影响认证**（claude 读凭证走内部路径，不经 Read 工具）。
   凭证从 Keychain 挪到明文文件是这套方案的代价，这条 + 网络白名单是两层缓解。

验一遍：bash scripts/outer-sandbox-probe.sh
EOF
