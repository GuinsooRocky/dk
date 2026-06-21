#!/usr/bin/env python3
"""watch —— 纳管/取消纳管一个交互式 Claude session 的出站通知（提案 N-M1，决策④只做 CLI）。

  # 在你想被通知的那个 session 的工作目录里跑：
  python <仓库>/hub/watch.py register                      # 用默认渠道（config.toml [notify].channel）
  python <仓库>/hub/watch.py register --channel telegram --target <真实chat_id>
  python <仓库>/hub/watch.py unregister [--session <id>]
  python <仓库>/hub/watch.py list

认「当前 session」走**内容指纹，绝不用 file mtime** —— mtime 会抓到并发的另一个会话
（含 bot 自己的 headless 跑）（memory 铁律「认 session 按内容非 mtime」）。做法：
  ① 从当前 cwd 映射到 ~/.claude/projects/<编码cwd>/ —— 这目录**按 cwd 隔离**，bot 跑在
     ~/claude-*-workdir 天然落在别的目录，先天就排除了大半噪声；
  ② 读每个候选 jsonl **内容里的** cwd 字段核对是不是当前目录、排除 bot work_dir；
  ③ 用**内容里最后一条记录的 timestamp**（不是文件 mtime）挑最近活跃的那条，stem 即 session_id。
register 时把渠道实际投递目标（Telegram 的真实 chat_id）存进路由行，绝不从 allowed_users
反推（§5 P1 串台：群是负数 chat id，白名单是 user id）。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # 任意 cwd 下当脚本跑也能 import
from hub import notify  # noqa: E402


def _project_dir_for(cwd: Path) -> Path:
    """cwd → Claude Code transcript 目录。CC 把绝对路径的 / 编码成 -。"""
    enc = str(cwd.resolve()).replace("/", "-")
    return Path.home() / ".claude" / "projects" / enc


def _content_fingerprint(jsonl: Path):
    """读 jsonl **内容**得到（最后一条记录的 timestamp 字符串, 会话 cwd）。

    全程只看文件内容，不碰文件系统修改时间（它会被并发会话/备份/同步搅乱，故弃用）。
    """
    last_ts, cwd_in = "", None
    try:
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("cwd"):
                cwd_in = obj["cwd"]
            if obj.get("timestamp"):
                last_ts = obj["timestamp"]
    except Exception:
        pass
    return last_ts, cwd_in


def detect_current_session(cwd: Path):
    """当前 cwd 对应目录里，按内容时间戳挑最近活跃、cwd 字段匹配、非 bot 的 session id。"""
    pdir = _project_dir_for(cwd)
    if not pdir.is_dir():
        return None
    target = str(cwd.resolve())
    best, best_ts = None, ""
    for jl in pdir.glob("*.jsonl"):
        ts, cwd_in = _content_fingerprint(jl)
        if cwd_in and str(Path(cwd_in).resolve()) != target:
            continue                              # 内容里的 cwd 不是当前目录
        if notify.is_bot_workdir(cwd_in or ""):
            continue                              # bot 自起的跑，绝不纳管（P0）
        if ts > best_ts:                          # ISO8601 同格式可直接字典序比，且来自内容
            best, best_ts = jl.stem, ts           # 文件名 stem = session_id
    return best


def cmd_register(args) -> int:
    cwd = Path.cwd()
    sid = detect_current_session(cwd)
    if not sid:
        print(f"没在 {cwd} 找到活跃的 Claude session transcript。"
              "请在你想纳管的那个 session 的工作目录里跑本命令。", file=sys.stderr)
        return 1
    channel = args.channel or notify.default_channel()
    target = args.target or None
    if channel == "telegram" and not target:
        print("Telegram 需要 --target <真实 chat_id>（群是负数）。"
              "注册时存真实投递目标、绝不从白名单反推（§5 P1 防串台）。", file=sys.stderr)
        return 1
    notify.register_session(sid, str(cwd), channel, target)   # 存 cwd，供「监听」tab 显示
    print(f"已纳管 session {sid} → {channel}" + (f"（target={target}）" if target else ""))
    return 0


def cmd_unregister(args) -> int:
    sid = args.session or detect_current_session(Path.cwd())
    if not sid:
        print("没指定 --session，且当前目录认不出 session。", file=sys.stderr)
        return 1
    routes = notify.load_routes()
    if sid in routes:
        del routes[sid]
        notify.save_routes(routes)
        print(f"已取消纳管 session {sid}")
    else:
        print(f"session {sid} 本就不在注册表里")
    return 0


def cmd_list(_args) -> int:
    routes = notify.load_routes()
    if not routes:
        print("（注册表为空）")
        return 0
    for sid, row in routes.items():
        print(f"{sid}  → {row.get('channel')}  target={row.get('target')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="纳管/取消纳管 Claude session 出站通知")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register", help="把当前 session 纳入完成通知")
    r.add_argument("--channel", choices=["feishu", "telegram"])
    r.add_argument("--target", help="Telegram 真实 chat_id（群为负数）；飞书 webhook 自带目标可不填")
    u = sub.add_parser("unregister", help="取消纳管")
    u.add_argument("--session", help="不传则认当前目录的 session")
    sub.add_parser("list", help="列出已纳管的 session")
    args = ap.parse_args()
    return {"register": cmd_register, "unregister": cmd_unregister, "list": cmd_list}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
