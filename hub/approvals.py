"""审批登记处 —— 「谁发起的、回哪、谁能批」这三件事的唯一真相。

两张表：
  RUNS      run_id  -> 冻结的请求者上下文 {channel, chat_id, user}
  PENDING   approval_id -> 一次待批的工具调用 + 决策

为什么要 RUNS 这张表：审批推给谁、谁的点击算数，**只能来自请求进 Hub 那一刻抓到的
endpoint**，不能从白名单取第一个人、不能拿"最近活跃的人"猜（PRD §14 冻结通知路由）。
MCP server 只拿得到 run_id，它伪造不出别人的 chat_id —— 串台在结构上就不成立。

为什么 decided_by 要校验：A 的确认不能批 B 的动作（PRD §13）。点击带的是 Telegram
callback 里的真实 from.id，跟冻结的 requester 比，不一致直接拒。

内存态即可：审批是"人正盯着手机"的秒级~分钟级动作，Hub 重启了那次跑也没了，
落盘反而要处理"复活一个已经没有 claude 在等的审批"这种更麻烦的状态。
"""
import threading
import time
import uuid

# run_id -> {channel, chat_id, user, created}
_RUNS: dict = {}
# approval_id -> {run_id, tool_name, input, decision, message, created, decided_by, decided_at}
_PENDING: dict = {}
_LOCK = threading.Lock()

RUN_TTL_SEC = 6 * 3600        # 跑完不显式清理也不留一辈子
APPROVAL_TTL_SEC = 2 * 3600


def _gc() -> None:
    """调用方持锁。顺手清过期，省一个定时器。"""
    now = time.time()
    for k, v in list(_RUNS.items()):
        if now - v.get("created", 0) > RUN_TTL_SEC:
            _RUNS.pop(k, None)
    for k, v in list(_PENDING.items()):
        if now - v.get("created", 0) > APPROVAL_TTL_SEC:
            _PENDING.pop(k, None)


def open_run(channel: str, chat_id: str, user: str) -> str:
    """请求进 Hub 时调一次，冻结请求者上下文，返回 run_id 给 claude 子进程带下去。"""
    run_id = uuid.uuid4().hex
    with _LOCK:
        _gc()
        _RUNS[run_id] = {"channel": channel, "chat_id": str(chat_id),
                         "user": str(user), "created": time.time()}
    return run_id


def close_run(run_id: str) -> None:
    """claude 跑完就撤掉，别让残留的 run_id 还能开新审批。"""
    with _LOCK:
        _RUNS.pop(run_id, None)
        for k, v in list(_PENDING.items()):
            if v.get("run_id") == run_id and not v.get("decision"):
                _PENDING.pop(k, None)


def get_run(run_id: str):
    with _LOCK:
        r = _RUNS.get(run_id)
        return dict(r) if r else None


def request(run_id: str, tool_name: str, tool_input: dict, suggestions=None) -> dict:
    """MCP server 第一次问 → 建一条待批记录。返回 {approval_id, ctx}；run 不存在返回 None。"""
    ctx = get_run(run_id)
    if ctx is None:
        return {}
    approval_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _gc()
        _PENDING[approval_id] = {
            "run_id": run_id, "tool_name": tool_name, "input": tool_input,
            "suggestions": suggestions or [], "decision": "", "message": "",
            "created": time.time(), "decided_by": "", "decided_at": 0.0,
        }
    return {"approval_id": approval_id, "ctx": ctx}


def poll(approval_id: str) -> dict:
    """查一条待批的当前状态。不存在 → 当 deny（宁可拒也不能默认放行）。"""
    with _LOCK:
        p = _PENDING.get(approval_id)
        if p is None:
            return {"decision": "deny", "message": "审批记录已失效（超时或 Hub 重启），本次拒绝"}
        return {"decision": p["decision"], "message": p["message"],
                "updated_input": p.get("updated_input")}


def decide(approval_id: str, decision: str, by_user: str) -> dict:
    """用户点按钮 → 落决策。校验三件事：记录在、没被批过、点的人就是请求者。"""
    decision = (decision or "").lower()
    if decision not in ("allow", "deny"):
        return {"ok": False, "reason": f"非法决策 {decision!r}"}
    with _LOCK:
        p = _PENDING.get(approval_id)
        if p is None:
            return {"ok": False, "reason": "审批记录不存在或已过期"}
        if p["decision"]:
            # 幂等：重复点同一个按钮不报错，点相反的按钮不许翻案
            same = p["decision"] == decision
            return {"ok": same, "reason": "" if same else f"已经是 {p['decision']}，不能改判",
                    "already": True, "decision": p["decision"]}
        ctx = _RUNS.get(p["run_id"]) or {}
        requester = str(ctx.get("user", ""))
        if requester and str(by_user) != requester:
            # 别人的确认不算数（PRD §13）；这条要能在日志里看见，是安全事件不是小错
            return {"ok": False, "reason": "not_requester",
                    "detail": f"点击者 {by_user} 不是本次请求者，拒绝代批"}
        p["decision"] = decision
        p["decided_by"] = str(by_user)
        p["decided_at"] = time.time()
        p["message"] = "用户拒绝了这次工具调用" if decision == "deny" else ""
        return {"ok": True, "decision": decision}


def snapshot() -> dict:
    """给 /status 和排查用：不含 input 正文（可能有敏感内容，PRD §15 默认不记正文）。"""
    with _LOCK:
        return {
            "runs": len(_RUNS),
            "pending": [
                {"approval_id": k, "tool_name": v["tool_name"],
                 "decision": v["decision"] or "waiting",
                 "age_sec": int(time.time() - v["created"])}
                for k, v in _PENDING.items()
            ],
        }
