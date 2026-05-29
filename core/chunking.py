"""长消息分段。"""


def split_chunks(text: str, max_len: int) -> list:
    """超过 max_len 就切片；不超过返回单元素列表。"""
    if len(text) <= max_len:
        return [text]
    return [text[i:i + max_len] for i in range(0, len(text), max_len)]
