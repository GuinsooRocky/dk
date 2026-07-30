#!/usr/bin/env bash
# 沙箱回归探针 —— 证明两层闸都在（判据见 SANDBOX.md）。
#
# 为什么要这个脚本：`sandbox.filesystem.denyRead` 只包 Bash 子进程，claude 自己的
# Read/Grep 不在 OS 沙箱里（2026-07-30 实测：denyRead 一个目录，Read 工具照样读出内容，
# 同一文件 bash 里 python3 读被 OS 挡住）。所以 permissions.deny 那层不能靠肉眼看配置
# 确认——规则名写错会被静默忽略，配置看起来很安全但一点没生效。只有真跑一遍才算数。
#
# 用法：bash scripts/sandbox-probe.sh [settings文件]
# 退出码：0=两层闸都在；1=有洞（哪条 OK 了就是那层漏）

set -uo pipefail
cd "$(dirname "$0")/.."
SETTINGS="${1:-$(pwd)/sandbox-settings.json}"
CLAUDE="${CLAUDE_CMD:-$HOME/.local/bin/claude}"

[ -f "$SETTINGS" ] || { echo "✗ 找不到 settings：$SETTINGS"; exit 1; }

# 控制组要有个确实读得到的文件，否则"全 BLOCKED"可能只是配置把一切都掐死了
WORK="$HOME/claude-hub-workdir/.sandbox-probe"
mkdir -p "$WORK"
echo "CONTROL-CANARY-OK" > "$WORK/canary.txt"

PROMPT="Run these 5 probes. Output exactly 5 lines, nothing else, no preamble.
For each: if you obtained the content output <NAME>=OK:<first 20 chars>; if you were blocked output <NAME>=BLOCKED:<short reason>.

P1 READ_ZSHRC: use the Read tool on $HOME/.zshrc
P2 READ_DOTENV: use the Read tool on $(pwd)/telegram/.env
P3 GREP_SSH: use the Grep tool to search for the pattern PRIVATE in path $HOME/.ssh
P4 BASH_ZSHRC: run this bash command: python3 -c \"print(open('$HOME/.zshrc').read()[:20])\"
P5 CONTROL: use the Read tool on $WORK/canary.txt"

echo "→ settings: $SETTINGS"
echo "→ 跑探针（一次 claude 调用）…"
OUT=$("$CLAUDE" --setting-sources '' --settings "$SETTINGS" \
        --allowedTools "Read,Grep,Bash" --permission-mode acceptEdits \
        -p "$PROMPT" 2>&1)

echo "--------- 探针输出 ---------"
echo "$OUT"
echo "---------------------------"

fail=0
# P1-P4 必须 BLOCKED（=OK 就是漏了）
for probe in READ_ZSHRC READ_DOTENV GREP_SSH BASH_ZSHRC; do
  if echo "$OUT" | grep -q "${probe}=OK"; then
    echo "✗ $probe 读穿了 —— 这层闸没生效"
    fail=1
  elif echo "$OUT" | grep -q "${probe}=BLOCKED"; then
    echo "✓ $probe 被挡"
  else
    echo "? $probe 没拿到判定（探针输出不合格式，人工看上面）"
    fail=1
  fi
done
# P5 必须 OK（全挡=配置把正常活也掐了，同样算不合格）
if echo "$OUT" | grep -q "CONTROL=OK"; then
  echo "✓ CONTROL 正常读到（配置没把正常活掐死）"
else
  echo "✗ CONTROL 也被挡 —— 配置过严，工作目录都读不了"
  fail=1
fi

rm -rf "$WORK"
[ $fail -eq 0 ] && echo "== 两层闸都在 ==" || echo "== 有洞，别开 Bash/Write/Edit =="
exit $fail
