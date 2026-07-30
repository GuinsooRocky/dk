"""审批 MCP server —— claude 的 --permission-prompt-tool 落点。

claude 要用工具时会调这里的 permission_prompt，我们把请求转给 Hub（Hub 推给用户的
Telegram 让他点按钮），挂着等决策，再把 allow/deny 回给 claude。

设计要点：
- **纯 stdlib**，不依赖 mcp SDK / httpx —— 它要能在 PyInstaller 冻结的 sidecar 里跑，
  也要能在任意渠道 venv 里跑，多一个依赖就多一处装不上。
- **薄**：不自己决定任何事，只做 claude ←→ Hub 的翻译。谁能批、推给谁、超时怎么办
  全在 Hub（同 telegram_bot「薄客户端」的分工）。
- **run_id 从环境变量来**，由 runner 每跑一次生成、写进 mcp-config 的 env。Hub 用它查
  「这次跑的请求者是谁、回哪个 chat」——冻结在入口，MCP server 无从伪造，
  结构上就串不了台（PRD §14）。
- **轮询而非无限挂**：Hub 每轮最多挂 25 秒就返回 pending，这边再问。无限期挂一个 HTTP
  连接跨不过代理/超时，轮询更耐操；对用户来说效果一样（他慢慢点）。

契约（claude 2.1.220 二进制里的原文）：
  Expected {behavior: 'allow', updatedInput?: object} or {behavior: 'deny', message: string}.
"""
import json
import os
import sys
import time
import urllib.request

HUB_URL = os.getenv("DK_HUB_URL", "http://127.0.0.1:8787").rstrip("/")
RUN_ID = os.getenv("DK_RUN_ID", "")
# 总预算：超了就 deny（不是 allow —— 拿不到人的确认时必须偏保守）
TOTAL_BUDGET_SEC = float(os.getenv("DK_APPROVAL_BUDGET_SEC", "1800"))
DEBUG_LOG = os.getenv("DK_APPROVAL_DEBUG_LOG", "")

TOOL_NAME = "permission_prompt"

# hub 可能被 supervisor 注入了 http_proxy（给 claude 用），本机回环必须直连
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _log(msg: str) -> None:
    """debug 日志只写文件，绝不碰 stdout —— stdout 是 JSON-RPC 通道，污染即协议破裂。"""
    if not DEBUG_LOG:
        return
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except OSError:
        pass


def _post(path: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        f"{HUB_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _OPENER.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ask_hub(tool_name: str, tool_input: dict, suggestions) -> dict:
    """转给 Hub 并等决策。返回 claude 要的 {behavior:...} 结构。"""
    deadline = time.monotonic() + TOTAL_BUDGET_SEC
    body = {
        "run_id": RUN_ID,
        "tool_name": tool_name,
        "input": tool_input,
        "suggestions": suggestions,
    }
    approval_id = ""
    while time.monotonic() < deadline:
        try:
            r = _post("/approval/request", {**body, "approval_id": approval_id}, timeout=40)
        except Exception as e:
            # Hub 够不着 → deny。绝不 fail-open：审批链路断了就等于没有闸
            _log(f"hub 不可达 {e}")
            return {"behavior": "deny", "message": f"审批服务不可达，本次工具调用已拒绝：{e}"}
        approval_id = r.get("approval_id") or approval_id
        decision = (r.get("decision") or "").lower()
        if decision == "allow":
            out = {"behavior": "allow"}
            if isinstance(r.get("updated_input"), dict):
                out["updatedInput"] = r["updated_input"]
            return out
        if decision == "deny":
            return {"behavior": "deny", "message": r.get("message") or "用户拒绝了这次工具调用"}
        # pending → 继续问
    _log("超预算未决 → deny")
    return {"behavior": "deny",
            "message": f"等审批超过 {int(TOTAL_BUDGET_SEC)} 秒没人回，本次工具调用已拒绝。"}


# ---------------- JSON-RPC over stdio ----------------

def _reply(msg_id, result: dict) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n")
    sys.stdout.flush()


def _reply_err(msg_id, code: int, message: str) -> None:
    sys.stdout.write(json.dumps(
        {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}) + "\n")
    sys.stdout.flush()


_TOOL_DEF = {
    "name": TOOL_NAME,
    "description": "Ask the human operator to approve or deny a tool call, over Telegram.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "tool_name": {"type": "string", "description": "Tool being requested"},
            "input": {"type": "object", "description": "Input the tool would run with"},
        },
        # 故意不写 required：claude 各版本传的键名可能是 tool_name / toolName，
        # 声明得太死会让它连调都调不进来。真正的兼容在 handle_call 里做。
    },
}


def handle_call(args: dict) -> dict:
    """把 claude 传来的参数归一化后转给 Hub。键名各版本可能不同，全都认。"""
    _log(f"tools/call args={json.dumps(args, ensure_ascii=False)[:1500]}")
    tool_name = args.get("tool_name") or args.get("toolName") or args.get("tool") or "unknown"
    tool_input = (args.get("input") or args.get("tool_input")
                  or args.get("toolInput") or args.get("arguments") or {})
    if not isinstance(tool_input, dict):
        tool_input = {"_raw": tool_input}
    suggestions = (args.get("permission_suggestions") or args.get("permissionSuggestions") or [])
    verdict = _ask_hub(tool_name, tool_input, suggestions)
    _log(f"verdict={verdict}")
    # 审批结果必须是 tool result 的**文本正文**（claude 解析这段 JSON）
    return {"content": [{"type": "text", "text": json.dumps(verdict, ensure_ascii=False)}]}


def main() -> None:
    _log(f"启动 run_id={RUN_ID or '(空)'} hub={HUB_URL}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method", "")
        msg_id = msg.get("id")

        if method == "initialize":
            # 回声客户端的协议版本：写死某个版本会在对端升级后谈崩
            ver = (msg.get("params") or {}).get("protocolVersion") or "2025-06-18"
            _reply(msg_id, {
                "protocolVersion": ver,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "dk-approval", "version": "1.0.0"},
            })
        elif method == "tools/list":
            _reply(msg_id, {"tools": [_TOOL_DEF]})
        elif method == "tools/call":
            params = msg.get("params") or {}
            if params.get("name") != TOOL_NAME:
                _reply_err(msg_id, -32602, f"unknown tool: {params.get('name')}")
                continue
            try:
                _reply(msg_id, handle_call(params.get("arguments") or {}))
            except Exception as e:          # 绝不让异常冒出去杀掉 server
                _log(f"handle_call 炸了 {e!r}")
                _reply(msg_id, {"content": [{"type": "text", "text": json.dumps(
                    {"behavior": "deny", "message": f"审批链路内部错误，已拒绝：{e}"})}]})
        elif msg_id is not None:
            # 未实现的请求要回错误，不能不回 —— 对端会一直等
            _reply_err(msg_id, -32601, f"method not found: {method}")
        # notifications（无 id）不回


if __name__ == "__main__":
    main()
