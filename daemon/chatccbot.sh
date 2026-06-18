#!/usr/bin/env bash
# chat-cc-bot 的 launchd 管家：把 supervisor(hub + 各渠道) 托管成后台服务。
#   ✅ 崩溃自愈（崩了自动拉起）   ✅ 无 Terminal 窗口   ✅ 不依赖任何终端/会话
#   ✅ 开机自启：默认【开】（RunAtLoad=true，登录即起、重启电脑后自动拉起）。不想要 → 改下方 plist 的 RunAtLoad 为 <false/> 再重新 install。
#
# 用法：./daemon/chatccbot.sh {install|start|stop|restart|status|logs|uninstall}
set -e

LABEL="com.lengmo.chatccbot"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$(command -v python3)"
DOMAIN="gui/$(id -u)"

write_plist() {
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$ROOT/supervisor.py</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>

  <!-- launchd 的 PATH 极简，必须补上 claude 和 ffmpeg 的目录 -->
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>

  <!-- 崩溃自愈：进程崩了(异常退出)自动拉起 -->
  <key>KeepAlive</key>
  <dict><key>Crashed</key><true/></dict>

  <!-- 开机自启：默认 true（登录即起 + install 即起，重启电脑后服务还在）。
       不想开机自启 → 改成 <false/>，再 ./daemon/chatccbot.sh install，然后手动 start -->
  <key>RunAtLoad</key><true/>

  <key>StandardOutPath</key><string>/tmp/chatccbot.out.log</string>
  <key>StandardErrorPath</key><string>/tmp/chatccbot.err.log</string>
</dict>
</plist>
EOF
}

case "${1:-}" in
  install)
    write_plist
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    echo "✅ 已登记并启动 launchd 服务 $LABEL（开机自启=开，重启电脑后自动拉起，无 Terminal 依赖）。"
    echo "   想确认：'$0 status'；想关开机自启：见脚本里 RunAtLoad 注释。"
    ;;
  start)
    launchctl kickstart -k "$DOMAIN/$LABEL"
    echo "✅ 已启动（崩了会自动拉起，无 Terminal 依赖）"
    ;;
  stop)
    launchctl kill TERM "$DOMAIN/$LABEL" 2>/dev/null || true
    echo "⏹ 已停（服务仍登记，下次 '$0 start' 可拉起）"
    ;;
  restart)
    launchctl kickstart -k "$DOMAIN/$LABEL"
    echo "🔄 已重启"
    ;;
  status)
    launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E "state =|pid =" | head -3 || echo "未安装/未运行"
    ;;
  logs)
    echo "--- /tmp/chatccbot.out.log + err.log（Ctrl+C 退出）---"
    tail -n 30 -f /tmp/chatccbot.out.log /tmp/chatccbot.err.log
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "🗑 已彻底移除（不再登记、不再自启）"
    ;;
  *)
    echo "用法: $0 {install|start|stop|restart|status|logs|uninstall}"
    ;;
esac
