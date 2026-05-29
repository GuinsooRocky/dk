"""白名单（fail-closed）。"""


def is_allowed(sender: str, allowed_users) -> bool:
    """fail-closed：白名单为空 → 拒绝所有人；非空 → 只放行名单内。绝不"空=放行所有人"。"""
    return bool(allowed_users) and sender in allowed_users
