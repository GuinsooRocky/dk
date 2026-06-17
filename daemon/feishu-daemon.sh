#!/usr/bin/env bash
# ⚠️ 待退役：这是只管「飞书单渠道」的旧守护。现在用 daemon/chatccbot.sh（一把起
#    hub + 所有 enabled 渠道，崩溃自愈，开机自启）。本脚本保留作单渠道 fallback，不 rm。
# =============================================================================
# launchd 控制器 —— 把飞书 WS 长连接服务做成「开机自启 + 崩溃自愈」的守护
#
#   ./daemon/feishu-daemon.sh install    生成 plist 并加载（登录自启、崩溃自拉）
#   ./daemon/feishu-daemon.sh status     看运行状态
#   ./daemon/feishu-daemon.sh logs       跟踪日志
#   ./daemon/feishu-daemon.sh restart    重启
#   ./daemon/feishu-daemon.sh uninstall  停止并彻底移除（不再自启）
#
# 设计要点：
#   - KeepAlive 只在「异常退出」时重启（SuccessfulExit=false），避免正常退出被反复拉起
#   - ThrottleInterval=10 给崩溃重启留间隔，防紧密重启风暴
#   - 关键坑：launchd 下 PATH 极简，claude 在 ~/.local/bin 会找不到 → 在 plist 里补 PATH
#   - 守护的是 WS 长连接版（单进程、无 ngrok）。若还在用 webhook 版，把 SCRIPT 改回 feishu_app_server.py
#     但 webhook 版还需另外守护 ngrok，远不如 WS 版干净。
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.lengmo.chatccbot.feishu"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

PY="$REPO/feishu-claude/.venv/bin/python"
SCRIPT="$REPO/feishu-claude/feishu_ws_server.py"
WORKDIR="$REPO/feishu-claude"
LOGDIR="$HOME/claude-feishu-workdir/.logs"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[x]${NC} $*"; }

gen_plist() {
  [ -x "$PY" ] || { error "找不到可用的 python：$PY（先在 feishu-claude 装好 .venv 和依赖）"; exit 1; }
  [ -f "$SCRIPT" ] || { error "找不到脚本：$SCRIPT"; exit 1; }
  mkdir -p "$LOGDIR" "$(dirname "$PLIST")"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>$SCRIPT</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$WORKDIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>$LOGDIR/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>$LOGDIR/launchd.err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF
  info "已生成 plist：$PLIST"
}

case "${1:-}" in
  install)
    gen_plist
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    launchctl enable "$DOMAIN/$LABEL"
    info "已加载并设为开机自启。看日志：$0 logs"
    warn "别忘了：飞书后台「事件订阅」要切到「使用长连接接收事件」，否则收不到消息。"
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl disable "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    info "已停止并移除（不再自启）。"
    ;;
  restart)
    launchctl kickstart -k "$DOMAIN/$LABEL"
    info "已重启。"
    ;;
  start)
    launchctl kickstart "$DOMAIN/$LABEL"
    info "已启动。"
    ;;
  stop)
    # KeepAlive 服务用 bootout 才停得住（光 stop 会被自动拉回）
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    info "已停止（重新 install 或 start 可恢复）。"
    ;;
  status)
    launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E '^\s*(state|pid|last exit|program) ' || warn "未加载（先 install）"
    ;;
  logs)
    info "跟踪 $LOGDIR （Ctrl+C 退出）"
    touch "$LOGDIR/feishu_app.log" "$LOGDIR/launchd.err.log"
    tail -f "$LOGDIR/feishu_app.log" "$LOGDIR/launchd.err.log"
    ;;
  *)
    echo "用法: $0 {install|uninstall|start|stop|restart|status|logs}"
    exit 1
    ;;
esac
