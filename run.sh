#!/usr/bin/env bash
# 一键启动：起 hub + config.toml 里 enabled 的渠道（崩溃自愈）。
set -e
cd "$(dirname "$0")"

if [ ! -f config.toml ]; then
  cp config.example.toml config.toml
  echo "已生成 config.toml —— 填好（至少一个渠道 enabled + token + allowed_users）再跑 ./run.sh"
  exit 0
fi

exec python3 supervisor.py
