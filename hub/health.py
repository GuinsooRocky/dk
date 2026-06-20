"""渠道鉴权有效性探针（P1）—— 把「进程活着但认证失效」从「连得上」里分出来。

hub 周期主动验证各渠道鉴权是否还有效（凭证过期/被吊销时进程仍连得上，但其实发不出消息）：
  - telegram：GET bot<token>/getMe，200 且 ok:true。
  - feishu：POST tenant_access_token/internal（与 feishu_common.get_tenant_token 同端点同做法），
    code==0 且拿到非空 token。
  - wecom：没有可脱离 WS 连接的鉴权 API（send 都走渠道进程那条 WS），故不在此主动探，
    改由 hub 复用「渠道壳只在 is_authenticated 时才发心跳」这个既有不变量反推（见 app.py 探针循环）。

全用 stdlib urllib + 空 ProxyHandler 直连（hub venv 没 httpx；且 hub 可能被注入代理给 claude 用，
鉴权探针要直连各平台 API，同 trust_env=False 的意图）。任何异常都当「认证无效」返回 False，不抛。
"""
import json
import urllib.request

from core import config

_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _cfg_or_env(section: str, cfg_key: str, env_key: str) -> str:
    """config.toml [section].cfg_key 优先，空则回落渠道 .env 的 env_key（同 channel_meta 双源）。"""
    val = ""
    try:
        import tomllib
        with open(config.app_root() / "config.toml", "rb") as f:
            val = (tomllib.load(f).get(section, {}).get(cfg_key) or "").strip()
    except Exception:
        val = ""
    if not val:
        val = config.read_env_value(config.channel_env_path(section), env_key)
    return val


def probe_telegram() -> bool:
    token = _cfg_or_env("telegram", "token", "TELEGRAM_BOT_TOKEN")
    if not token:
        return False
    try:
        with _DIRECT.open(f"https://api.telegram.org/bot{token}/getMe", timeout=10) as r:
            return r.status == 200 and json.loads(r.read().decode("utf-8")).get("ok") is True
    except Exception:
        return False


def probe_feishu() -> bool:
    app_id = _cfg_or_env("feishu", "app_id", "FEISHU_APP_ID")
    secret = _cfg_or_env("feishu", "app_secret", "FEISHU_APP_SECRET")
    if not app_id or not secret:
        return False
    try:
        data = json.dumps({"app_id": app_id, "app_secret": secret}).encode("utf-8")
        req = urllib.request.Request(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            data=data, headers={"Content-Type": "application/json"}, method="POST")
        with _DIRECT.open(req, timeout=10) as r:
            body = json.loads(r.read().decode("utf-8"))
        return body.get("code") == 0 and bool(body.get("tenant_access_token"))
    except Exception:
        return False
