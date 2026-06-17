#!/usr/bin/env bash
# 双击我（Finder 里双击）→ 菜单栏右上角出现 🤖。需先起 Hub（./run.sh）。
cd "$(dirname "$0")"
exec .venv/bin/python app.py >> /tmp/chatcc-menubar.log 2>&1
