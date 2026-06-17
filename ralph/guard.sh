#!/usr/bin/env bash
# chat-cc-bot 链路守卫 loop —— 现在就能跑,纯本地,不提交、不调 claude、不烧额度。
#
# 这是"测试型 loop":引擎是 smoke_test,不是任务清单。你一边改代码,它一边盯:
#   源文件一变 → 自动重跑 4 条链路不变量 → 绿了安静心跳,红了响铃+报哪条断了。
# 适合现在(v1 已清空、工作区还脏、没 backlog 可喂 Ralph)边改边守。
#
# 用法:  bash ralph/guard.sh [轮询间隔秒,默认 3]
#         Ctrl-C 停。
set -u
cd "$(dirname "$0")/.." || exit 1

PY="${PYTHON:-python3}"
INTERVAL="${1:-3}"

echo "🛡  chat-cc-bot 链路守卫启动(间隔 ${INTERVAL}s,Ctrl-C 停)"
echo "   改任意 .py → 自动重跑冒烟。绿=链路一致,红=有渠道漏改/契约破。"
echo

# 源文件指纹(排除 venv / pycache / .git / ralph 自身),变了才重跑
fingerprint() {
  find . -name '*.py' \
    -not -path '*/.venv/*' -not -path '*/__pycache__/*' \
    -not -path '*/.git/*' -not -path './ralph/*' \
    -exec stat -f '%m %z %N' {} \; 2>/dev/null | sort | md5
}

last=""
first=1
while :; do
  sig="$(fingerprint)"
  if [ "$sig" != "$last" ]; then
    [ "$first" = 1 ] || echo "── $(date '+%H:%M:%S') 检测到改动,重跑 ──"
    first=0
    if "$PY" ralph/smoke_test.py; then
      :  # 绿:smoke 自己打印了 ✅ 行,不再啰嗦
    else
      printf '\a'   # 响铃提醒
      echo "👆 链路红了。按上面提示修(多半是某渠道没跟上改动);修好这里会自动转绿。"
    fi
    last="$sig"
  fi
  sleep "$INTERVAL"
done
