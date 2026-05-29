#!/usr/bin/env bash
# 一键启动：检查环境 → 装依赖 → 启动 server → 显示 ngrok 用法
set -e
cd "$(dirname "$0")"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[x]${NC} $*"; }

# 1. 检查 .env
if [ ! -f .env ]; then
    warn "没有 .env 文件，从 .env.example 创建"
    cp .env.example .env
    error "请先编辑 .env 填入 FEISHU_APP_ID / FEISHU_APP_SECRET / ANTHROPIC_API_KEY"
    error "  打开：$(pwd)/.env"
    exit 1
fi

# 2. 检查 claude
if ! command -v claude &> /dev/null; then
    warn "未检测到 claude 命令，准备安装..."
    curl -fsSL https://code.claude.com/install.sh | sh
    export PATH="$HOME/.claude/local:$PATH"
fi

# 3. 装依赖
info "装 Python 依赖..."
python3 -m pip install -r requirements.txt --break-system-packages --quiet 2>/dev/null || {
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt --quiet
}

# 4. 检查 ngrok（不强制，只提示）
if ! command -v ngrok &> /dev/null; then
    warn "未检测到 ngrok。安装命令：brew install ngrok"
    warn "或下载：https://ngrok.com/download"
    echo ""
fi

# 5. 提示 ngrok 用法
PORT=$(grep -E '^APP_PORT=' .env | cut -d= -f2 | tr -d ' ')
PORT=${PORT:-5858}

cat <<EOF

==============================================
  下一步操作（开两个终端）
==============================================

[终端 1]  现在跑这个：
  python3 feishu_app_server.py

[终端 2]  另开一个，跑 ngrok：
  ngrok http $PORT

  ngrok 启动后会显示一个 https URL，长这样：
    Forwarding  https://abcd1234.ngrok-free.app -> http://localhost:$PORT

  把 URL 加上 "/event" 路径填到飞书后台：
    https://abcd1234.ngrok-free.app/event
                                    ^^^^^^
                                    注意这个！

[飞书后台]
  开放平台 → 你的应用 → 事件订阅 → 配置请求地址
  粘贴上面的 URL，飞书会立刻发一个验证请求。
  看终端 1 应该打印 "URL 验证 challenge=..." 表示成功。

==============================================

现在准备启动 server，按回车继续，Ctrl+C 取消...
EOF

read -r
exec python3 feishu_app_server.py
