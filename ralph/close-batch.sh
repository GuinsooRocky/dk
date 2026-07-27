#!/usr/bin/env bash
# 一批 loop 跑完之后的「结账」脚本 —— 归档、轮转、对账、列遗产。
#
# 用法:  bash ralph/close-batch.sh [批次ID]
#        批次ID 不传就从 manifest 的 batchId 读,再读不到用当天日期兜底。
#        全程只归档 + 只列举,唯一的「删」是日志轮转,且走 ~/.Trash 不 rm。
#        退出码:0=账对上了(可能有提示) / 1=有对账告警,需要人看一眼。
#
# 变量(都可用同名环境变量覆盖,方便别的项目复用这套骨架):
#   LOOP_DIR     loop 骨架目录(本仓 ralph),下面的默认值都挂在它下面
#   MANIFEST     本批冻结的任务清单 JSON,至少含 taskIds 数组(账本第一公民,原则②)
#   FIX_PLAN     本批工作清单,任务状态的真相(- [x] 完成 / - [⚠] 卡住 / - [ ] 待办)
#   PROGRESS     本批进度快照(每轮追加的那份),没有就跳过
#   LOG_DIR      驱动日志目录,轮转后只留最近一次运行
#   ARCHIVE_DIR  归档落点,按 <批次ID>-<时间戳> 建子目录
#   BACKLOG      任务总台账:manifest 里的任务必须在这有条目
#   DONE         已完成台账:完成的任务必须搬进这里
#   TRASH        删除中转站,绝不 rm
#   PYTHON       解析 manifest JSON 用的解释器(默认 python3)
set -u
cd "$(dirname "$0")/.." || exit 1

LOOP_DIR=${LOOP_DIR:-ralph}
MANIFEST=${MANIFEST:-$LOOP_DIR/batch-manifest.json}
FIX_PLAN=${FIX_PLAN:-$LOOP_DIR/fix_plan.md}
PROGRESS=${PROGRESS:-$LOOP_DIR/PROGRESS.md}
LOG_DIR=${LOG_DIR:-$LOOP_DIR/logs}
ARCHIVE_DIR=${ARCHIVE_DIR:-$LOOP_DIR/archive}
BACKLOG=${BACKLOG:-docs/BACKLOG.md}
DONE=${DONE:-docs/DONE.md}
TRASH=${TRASH:-$HOME/.Trash}
PY=${PYTHON:-python3}

WARN=0
warn() { echo "⚠ $*"; WARN=$((WARN + 1)); }

# manifest 字段读取:没有 manifest 或 JSON 坏了都不炸,后面按「无账本」降级处理
mf() { [ -f "$MANIFEST" ] || return 0; "$PY" -c '
import json,sys
d=json.load(open(sys.argv[1]))
v=d.get(sys.argv[2],"")
print("\n".join(v) if isinstance(v,list) else v)' "$MANIFEST" "$1" 2>/dev/null; }

BATCH_ID=${1:-$(mf batchId)}
BATCH_ID=${BATCH_ID:-batch-$(date '+%Y%m%d')}
STAMP=$(date '+%Y%m%d-%H%M')
TASK_IDS=$(mf taskIds)

echo "===== 收官 $BATCH_ID ($(date '+%Y-%m-%d %H:%M:%S')) ====="
[ -f "$MANIFEST" ] || warn "没有 manifest($MANIFEST):本批没冻结账本,对账整段跳过。"

# ── 1. 归档本批账本与进度 ────────────────────────────────────────────────
DEST="$ARCHIVE_DIR/$BATCH_ID-$STAMP"
mkdir -p "$DEST"
for f in "$MANIFEST" "$FIX_PLAN" "$PROGRESS"; do
  [ -f "$f" ] || continue
  cp -p "$f" "$DEST/" && echo "  归档 $f"
done
echo "  → $DEST"

# ── 2. 日志轮转:只留最近一次运行,旧的进废纸篓 ──────────────────────────
if [ -d "$LOG_DIR" ]; then
  KEEP=$(ls -t "$LOG_DIR" 2>/dev/null | head -1)
  BIN="$TRASH/$(basename "$PWD")-${LOOP_DIR##*/}-logs-$BATCH_ID-$STAMP"
  MOVED=0
  for f in "$LOG_DIR"/*; do
    [ -e "$f" ] || continue
    [ "$(basename "$f")" = "$KEEP" ] && continue
    mkdir -p "$BIN" && mv "$f" "$BIN/" && MOVED=$((MOVED + 1))
  done
  echo "  日志轮转:保留 ${KEEP:-（空目录）},移走 $MOVED 份${MOVED:+ → $BIN}"
else
  echo "  日志轮转:没有 $LOG_DIR,跳过"
fi

# ── 3. 残留现场:worktree 与 stash 只列不删 ─────────────────────────────
WT=$(git worktree list 2>/dev/null | tail -n +2)
ST=$(git stash list 2>/dev/null)
WT_N=$([ -n "$WT" ] && printf '%s\n' "$WT" | wc -l | tr -d ' ' || echo 0)
ST_N=$([ -n "$ST" ] && printf '%s\n' "$ST" | wc -l | tr -d ' ' || echo 0)
if [ "$WT_N" != 0 ]; then echo "  残留 worktree($WT_N,只列不删):"; printf '%s\n' "$WT" | sed 's/^/    /'; fi
if [ "$ST_N" != 0 ]; then echo "  残留 stash($ST_N,只列不删):"; printf '%s\n' "$ST" | sed 's/^/    /'; fi
[ "$WT_N" = 0 ] && [ "$ST_N" = 0 ] && echo "  现场干净:无残留 worktree / stash"

# ── 4. 跟任务台账对账(原则②:条目只能被完成,不能消失)────────────────────
DONE_N=0
PEND_N=0
STUCK_N=0
MISS_N=0
if [ -n "$TASK_IDS" ]; then
  [ -f "$BACKLOG" ] || warn "台账不存在($BACKLOG):跳过 BACKLOG 对账。"
  [ -f "$DONE" ] || warn "已完成台账不存在($DONE):跳过 DONE 对账。"
  [ -f "$FIX_PLAN" ] || warn "工作清单不存在($FIX_PLAN):任务状态无从判定。"
  while IFS= read -r t; do
    [ -n "$t" ] || continue
    if [ -f "$FIX_PLAN" ] && grep -Eq -- "^- \[[xX]\].*$t" "$FIX_PLAN"; then
      STATE=done; DONE_N=$((DONE_N + 1))
    elif [ -f "$FIX_PLAN" ] && grep -Eq -- "^- \[⚠\].*$t" "$FIX_PLAN"; then
      STATE=stuck; STUCK_N=$((STUCK_N + 1))
    elif [ -f "$FIX_PLAN" ] && grep -Eq -- "^- \[ \].*$t" "$FIX_PLAN"; then
      STATE=pending; PEND_N=$((PEND_N + 1))
    else
      STATE=missing; MISS_N=$((MISS_N + 1))
      warn "任务在清单里消失了:$t 在 $MANIFEST 有,在 $FIX_PLAN 找不到任何状态行。"
    fi
    [ -f "$BACKLOG" ] && ! grep -q -- "$t" "$BACKLOG" && warn "台账缺条目:$t 不在 ${BACKLOG}。"
    [ "$STATE" = done ] && [ -f "$DONE" ] && ! grep -q -- "$t" "$DONE" \
      && warn "完成了但没搬进 DONE:$t 该进 ${DONE}。"
  done <<EOF
$TASK_IDS
EOF
  echo "  对账:manifest $(printf '%s\n' "$TASK_IDS" | wc -l | tr -d ' ') 项 = 完成 $DONE_N / 卡住 $STUCK_N / 待办 $PEND_N / 失踪 $MISS_N"
fi

# ── 5. 本批遗产清单 ─────────────────────────────────────────────────────
echo
echo "───── 本批遗产清单($BATCH_ID)─────"
echo "  归档目录 : $DEST"
echo "  任务状态 : 完成 $DONE_N · 卡住 $STUCK_N · 待办 $PEND_N · 失踪 $MISS_N"
echo "  残留现场 : worktree $WT_N · stash $ST_N (都没动,要清自己来)"
echo "  日志     : $LOG_DIR 只剩 ${KEEP:-（无）},旧的在 ${BIN:-（未产生）}"
echo "  留给人的 : 卡住的任务($LOOP_DIR/fix_plan.md 搜 '⚠ 卡住')+ 上面每条 ⚠"
if [ "$WARN" -gt 0 ]; then
  echo "⛔ $WARN 条对账告警,账没对平——先看告警再开下一批。"
  exit 1
fi
echo "✅ 账对平了,可以开下一批。"
