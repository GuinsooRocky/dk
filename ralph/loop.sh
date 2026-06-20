#!/usr/bin/env bash
# Ralph loop for chat-cc-bot —— 在专用分支上反复唤起 claude,直到 fix_plan 清空。
#
# 用法:  bash ralph/loop.sh        (Ctrl-C 随时停)
# 机理:  每轮 = 全新 context 喂同一个 PROMPT.md;claude 读 fix_plan 自己挑一件活、
#        干完、跑冒烟、绿了 commit。状态全在磁盘(fix_plan + git),不靠上下文记忆。
#
# ⚠ 这会消耗你的 Claude 额度并自动 commit(仅 ralph/auto 分支)。先在干净工作区跑。
set -u
cd "$(dirname "$0")/.." || exit 1

BR=ralph/auto

# 安全闸 0:工作区必须干净。否则首轮 git add 会把你未提交的手改一并裹走,
# Ralph 也假设"已提交基线 + 每轮只产生自己那一笔"。脏树直接拒跑。
if [ -n "$(git status --porcelain)" ]; then
  echo "⛔ 工作区不干净(有未提交/未跟踪改动)。先 commit 或 stash 再跑 Ralph。"
  git status --short
  exit 1
fi

# 安全闸 1:只在专用分支跑,绝不碰 main/develop
git rev-parse --verify "$BR" >/dev/null 2>&1 || git branch "$BR"
git switch "$BR" || { echo "切不到分支 $BR,停"; exit 1; }

MAX=${1:-30}   # 轮数上限,防失控(Ralph 也要熔断)
ITER=0
while [ "$ITER" -lt "$MAX" ]; do
  ITER=$((ITER+1))
  echo "===== Ralph iteration $ITER / $MAX ($(date '+%H:%M:%S')) ====="

  # 全新 context、headless 喂 PROMPT;claude 自己读 fix_plan 挑活
  cat ralph/PROMPT.md | claude -p --dangerously-skip-permissions 2>&1 | tee -a ralph/loop.log

  # 收工条件:「待办」里没有未打勾任务了(- [⚠] 跳过项不算待办)
  if ! grep -q '^- \[ \]' ralph/fix_plan.md; then
    SKIPPED=$(grep -c '^- \[⚠\]' ralph/fix_plan.md)
    echo "✅ fix_plan 无待办,Ralph 收工(共 $ITER 轮)"
    [ "$SKIPPED" -gt 0 ] && echo "⚠ 有 $SKIPPED 个任务被跳过(- [⚠]),搜 '⚠ 卡住' 看原因,留给你手动处理。"
    exit 0
  fi
  sleep 2
done
echo "⏹ 到轮数上限 $MAX,停(防失控)。fix_plan 还有待办就再跑一次。"
