#!/usr/bin/env bash
# ⚠️ 待退役（仅供前台调试）：这是在 Terminal 里前台跑 supervisor，关窗口 = 全断，
#    且窗口退出会留"进程已完成"残骸。日常请用守护进程（无 Terminal、崩溃自愈、开机自启）：
#        ./daemon/chatccbot.sh install
#    本脚本保留只为开发时看实时日志。
# 一键启动：起 hub + config.toml 里 enabled 的渠道（崩溃自愈）。
set -e
cd "$(dirname "$0")"

if [ ! -f config.toml ]; then
  cp config.example.toml config.toml
  echo "已生成 config.toml —— 填好（至少一个渠道 enabled + token + allowed_users）再跑 ./run.sh"
  exit 0
fi

exec python3 supervisor.py
