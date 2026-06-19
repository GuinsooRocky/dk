"""长消息分段。"""


# 多段时各渠道会给每段加 "[i/N] " 前缀；预留这点宽度，否则按 max_len 精确切出的段
# 加完前缀就超平台上限（企业微信 2000：2000+前缀必被拒发）。12 足够覆盖到 "[999/999] "。
_PREFIX_RESERVE = 12


def split_chunks(text: str, max_len: int) -> list:
    """超过 max_len 就切片；不超过返回单元素列表。
    切片时按 max_len-_PREFIX_RESERVE 收窄，给调用方的 "[i/N] " 前缀留位（单段不加前缀，不受影响）。"""
    if len(text) <= max_len:
        return [text]
    budget = max(1, max_len - _PREFIX_RESERVE)
    return [text[i:i + budget] for i in range(0, len(text), budget)]
