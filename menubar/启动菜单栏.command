#!/usr/bin/env bash
# ⚠️ 待退役：双击它启动菜单栏，但 Terminal 窗口会留"进程已完成"残骸，关窗口=杀菜单栏。
#    这是 T2 原生 .app（菜单栏+窗口同进程、无 Terminal）要替掉的东西。临时用就先忍残骸窗口。
# 双击我（Finder 里双击）→ 菜单栏右上角出现 🤖。需先起 Hub（守护：./daemon/chatccbot.sh install）。
cd "$(dirname "$0")"
exec .venv/bin/python app.py >> /tmp/chatcc-menubar.log 2>&1
