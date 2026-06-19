"""白名单（fail-closed）。"""


def is_allowed(sender: str, allowed_users) -> bool:
    """fail-closed：白名单为空 → 拒绝所有人；非空 → 只放行名单内。绝不"空=放行所有人"。

    类型守卫：allowed_users 必须是容器（list/tuple/set）。若误传字符串，`in` 会退化成
    子串匹配（"23" in "123,456" → True）造成越权，故非容器一律拒绝。"""
    if not isinstance(allowed_users, (list, tuple, set, frozenset)):
        return False
    return bool(allowed_users) and sender in allowed_users
