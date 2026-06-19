"""沙箱验证：判断给 claude 的 --settings 是否真把它关进沙箱（GUARD-2/3 共用判据）。

写/全权工具只有在沙箱确实生效时才安全自动放行。判据（全真才算 verified）：
  1. CLAUDE_SETTINGS 指向的文件存在；
  2. 文件里 sandbox.enabled == true 且 sandbox.failIfUnavailable == true
     （这两字段嵌在顶层 "sandbox" key 下，按平铺读会永远验不过）；
  3. 本机 sandbox-exec 能起一个最小 profile（macOS 沙箱机制可用）。
"""
import json
import time
import subprocess
from pathlib import Path


def _settings_ok(settings_path: str) -> bool:
    if not settings_path:
        return False
    p = Path(settings_path).expanduser()
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text())
    except Exception:
        return False
    sb = data.get("sandbox") or {}
    return bool(sb.get("enabled")) and bool(sb.get("failIfUnavailable"))


_exec_ok_cache = None
_exec_ok_at = 0.0
_EXEC_TTL = 60   # 秒：缓存带 TTL，避免机制运行期失效后永久 fail-open（仍报已验证→不剥危险工具）


def _sandbox_exec_ok() -> bool:
    """sandbox-exec 能起最小 profile 即认为机制可用。带 TTL 缓存，避免每条消息都 fork 探测，
    又不至于像永久缓存那样在机制中途失效后一直误判可用。"""
    global _exec_ok_cache, _exec_ok_at
    now = time.monotonic()
    if _exec_ok_cache is None or now - _exec_ok_at > _EXEC_TTL:
        try:
            r = subprocess.run(
                ["sandbox-exec", "-p", "(version 1)(allow default)", "true"],
                capture_output=True, timeout=5,
            )
            _exec_ok_cache = (r.returncode == 0)
        except Exception:
            _exec_ok_cache = False
        _exec_ok_at = now
    return _exec_ok_cache


def status(settings_path: str) -> dict:
    """给 hub /sandbox 用：判据细节 + 总 verified。"""
    settings = _settings_ok(settings_path)
    execable = _sandbox_exec_ok()
    return {
        "settings_path": settings_path or "",
        "settings_ok": settings,
        "sandbox_exec_ok": execable,
        "verified": bool(settings and execable),
    }


def verified(settings_path: str) -> bool:
    return status(settings_path)["verified"]
