#!/usr/bin/env python3
"""
Feishu × Claude 一键发送工具
============================

用法：
  # 在终端里给 Claude 出题，结果发到飞书群
  python feishu_send.py "帮我总结今天的科技新闻"

  # 也可以从管道接收（适合脚本/cron）
  echo "今天的待办" | python feishu_send.py

  # 测试 webhook 是否通（不调 Claude）
  python feishu_send.py --ping

需要先在 .env 里填：
  FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx
  FEISHU_SECRET=...  (可选，如果你的机器人启用了签名校验)
  ANTHROPIC_API_KEY=sk-ant-...
"""

import os
import sys
import json
import time
import hmac
import base64
import hashlib
import argparse
import subprocess
from pathlib import Path

# 加载 .env
def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            # 直接赋值（.env 权威）：避免 shell 已 export 同名变量时 .env 被静默忽略
            os.environ[k.strip()] = v.strip()

load_env()

WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
SECRET = os.getenv("FEISHU_SECRET", "").strip()
CLAUDE_CMD = os.getenv("CLAUDE_CMD", "claude")
WORK_DIR = Path(os.getenv("CLAUDE_WORK_DIR", str(Path.home() / "claude-feishu-workdir")))
# 安全默认：只读工具。这是你自己在终端跑的单向工具，如需 Bash/Write 可在 .env 显式 opt-in
ALLOWED_TOOLS = os.getenv("CLAUDE_TOOLS", "Read,Glob,Grep,WebFetch")
TIMEOUT = int(os.getenv("CLAUDE_TIMEOUT", "300"))

WORK_DIR.mkdir(parents=True, exist_ok=True)


def gen_sign(secret: str, timestamp: int) -> str:
    """飞书签名校验算法"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_to_feishu(text: str) -> dict:
    """发文本消息到飞书群"""
    if not WEBHOOK_URL:
        print("错误：.env 里没有配 FEISHU_WEBHOOK_URL", file=sys.stderr)
        sys.exit(1)

    # 标准库够用，不引入 requests
    import urllib.request

    payload = {
        "msg_type": "text",
        "content": {"text": text},
    }
    if SECRET:
        ts = int(time.time())
        payload["timestamp"] = str(ts)
        payload["sign"] = gen_sign(SECRET, ts)

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"code": -1, "msg": str(e)}


def run_claude(prompt: str) -> str:
    """调用 claude headless"""
    cmd = [
        CLAUDE_CMD,
        "-p", prompt,
        "--allowedTools", ALLOWED_TOOLS,
        "--output-format", "json",
        "--permission-mode", "acceptEdits",
    ]
    print(f"[Claude] 思考中... (工具: {ALLOWED_TOOLS}, 工作目录: {WORK_DIR})")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(WORK_DIR),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"任务超过 {TIMEOUT} 秒，已中断。"
    except FileNotFoundError:
        return f"找不到 claude 命令（CLAUDE_CMD={CLAUDE_CMD}）。请先安装 Claude Code。"

    if proc.returncode != 0:
        return f"Claude 出错：\n{proc.stderr[:1500]}"

    try:
        data = json.loads(proc.stdout)
        return (data.get("result") or data.get("text") or proc.stdout).strip()
    except json.JSONDecodeError:
        return proc.stdout.strip() or "(Claude 没有返回内容)"


def main():
    parser = argparse.ArgumentParser(description="Claude → 飞书群")
    parser.add_argument("prompt", nargs="*", help="给 Claude 的指令")
    parser.add_argument("--ping", action="store_true", help="只测试 webhook，不调 Claude")
    parser.add_argument("--raw", action="store_true", help="不调 Claude，直接把 prompt 当消息发到群")
    args = parser.parse_args()

    if args.ping:
        result = send_to_feishu("[ping] 飞书机器人测试 ✅\n如果你看到这条消息，说明 webhook 配置正确。")
        print("飞书返回:", result)
        sys.exit(0 if result.get("code") == 0 or result.get("StatusCode") == 0 else 1)

    # 拼 prompt：命令行参数 > stdin
    if args.prompt:
        prompt = " ".join(args.prompt)
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    else:
        parser.print_help()
        sys.exit(1)

    if not prompt:
        print("错误：prompt 为空", file=sys.stderr)
        sys.exit(1)

    # 决定要发到群里的内容
    if args.raw:
        message = prompt
    else:
        answer = run_claude(prompt)
        # 给消息加个头部，方便群里看出是谁问的
        message = f"问：{prompt}\n\n{answer}"

    print(f"[飞书] 发送 {len(message)} 字...")
    result = send_to_feishu(message)
    print("飞书返回:", result)


if __name__ == "__main__":
    main()
