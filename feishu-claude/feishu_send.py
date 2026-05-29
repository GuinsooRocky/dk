#!/usr/bin/env python3
"""Feishu × Claude 一键发送（方案 A：终端 → 群，单向）。

  python feishu_send.py "帮我总结今天的科技新闻"
  echo "今天的待办" | python feishu_send.py
  python feishu_send.py --ping        # 只测 webhook
  python feishu_send.py --raw "文本"  # 不调 claude，直接发

.env 需要：FEISHU_WEBHOOK_URL（群自定义机器人）、可选 FEISHU_SECRET（签名）。
跑 claude 复用 core.runner（与双向版同一份实现）。
"""
import os
import sys
import json
import time
import hmac
import base64
import hashlib
import argparse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config, runner  # noqa: E402

config.load_env(Path(__file__).parent / ".env")
CFG = config.load(str(Path.home() / "claude-feishu-workdir"))
CFG.work_dir.mkdir(parents=True, exist_ok=True)

WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
SECRET = os.getenv("FEISHU_SECRET", "").strip()


def gen_sign(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_to_feishu(text: str) -> dict:
    if not WEBHOOK_URL:
        print("错误：.env 里没有配 FEISHU_WEBHOOK_URL", file=sys.stderr)
        sys.exit(1)
    payload = {"msg_type": "text", "content": {"text": text}}
    if SECRET:
        ts = int(time.time())
        payload["timestamp"] = str(ts)
        payload["sign"] = gen_sign(SECRET, ts)
    req = urllib.request.Request(
        WEBHOOK_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"code": -1, "msg": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Claude → 飞书群")
    parser.add_argument("prompt", nargs="*", help="给 Claude 的指令")
    parser.add_argument("--ping", action="store_true", help="只测试 webhook，不调 Claude")
    parser.add_argument("--raw", action="store_true", help="不调 Claude，直接把 prompt 当消息发")
    args = parser.parse_args()

    if args.ping:
        result = send_to_feishu("[ping] 飞书机器人测试 ✅")
        print("飞书返回:", result)
        sys.exit(0 if result.get("code") == 0 or result.get("StatusCode") == 0 else 1)

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

    if args.raw:
        message = prompt
    else:
        print(f"[Claude] 思考中...（工具: {CFG.allowed_tools}, 引擎: {CFG.engine}, 目录: {CFG.work_dir}）")
        result = runner.run_claude(CFG, prompt, CFG.work_dir)
        message = f"问：{prompt}\n\n{result['text']}"

    print(f"[飞书] 发送 {len(message)} 字...")
    print("飞书返回:", send_to_feishu(message))


if __name__ == "__main__":
    main()
