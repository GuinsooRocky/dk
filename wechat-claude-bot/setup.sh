#!/usr/bin/env bash
# WeChat × Claude Code 一键安装脚本（Mac）
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[x]${NC} $*"; }

cd "$(dirname "$0")"
PROJ_DIR="$(pwd)"

info "项目目录：$PROJ_DIR"

# ============ 1. 检查 Node ============
if ! command -v node &> /dev/null; then
    error "未安装 Node.js。请先：brew install node"
    exit 1
fi
NODE_VER=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VER" -lt 18 ]; then
    error "Node 版本太低（v${NODE_VER}），需要 >= 18。请：brew upgrade node"
    exit 1
fi
info "Node.js: $(node -v)"

# ============ 2. 检查 Python ============
if ! command -v python3 &> /dev/null; then
    error "未安装 Python 3。请先：brew install python"
    exit 1
fi
info "Python: $(python3 --version)"

# ============ 3. 检查 Claude Code ============
if ! command -v claude &> /dev/null; then
    warn "未检测到 claude 命令。准备安装 Claude Code..."
    curl -fsSL https://code.claude.com/install.sh | sh || {
        error "Claude Code 安装失败。请访问 https://docs.claude.com/en/docs/claude-code 手动安装"
        exit 1
    }
    # 重新加载 PATH
    export PATH="$HOME/.claude/local:$PATH"
fi
info "Claude Code: $(claude --version 2>&1 | head -1)"

# ============ 4. 安装 Python 依赖 ============
info "安装 Python 依赖（Flask）..."
python3 -m pip install -r requirements.txt --break-system-packages --quiet || {
    warn "pip 安装失败，尝试用虚拟环境..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt --quiet
    info "已创建 .venv，运行 bridge 时请先 source .venv/bin/activate"
}

# ============ 5. 安装 Node 依赖 ============
info "安装 Node 依赖（wechaty）...（首次较慢）"
npm install --silent || {
    error "npm install 失败，请检查网络"
    exit 1
}

# ============ 6. 创建工作目录 ============
WORK_DIR="$HOME/claude-wechat-workdir"
mkdir -p "$WORK_DIR"
info "Claude 工作目录：$WORK_DIR"

# ============ 7. 创建 .env ============
if [ ! -f .env ]; then
    cp .env.example .env
    warn "已创建 .env，请填入你的 ANTHROPIC_API_KEY"
    warn "  打开：$PROJ_DIR/.env"
else
    info ".env 已存在，跳过"
fi

# ============ 8. 完成 ============
echo ""
info "====== 安装完成 ======"
echo ""
echo "下一步："
echo "  1. 编辑 .env 填入 ANTHROPIC_API_KEY"
echo "  2. 打开两个终端窗口分别运行："
echo "     [终端 1] python3 claude_bridge.py"
echo "     [终端 2] node wechat_bot.js   （首次运行需扫码登录微信）"
echo ""
echo "测试方法："
echo "  - 给微信里的「文件传输助手」发任意消息"
echo "  - 或私聊好友发：/c 你好"
echo "  - 或群里 @机器人"
