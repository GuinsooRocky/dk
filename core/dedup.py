"""事件幂等去重（线程安全，FIFO 保留最近 N 个）。"""
import threading
from collections import OrderedDict


class Dedup:
    def __init__(self, maxsize: int = 2000):
        self._seen: "OrderedDict[str, bool]" = OrderedDict()
        self._lock = threading.Lock()
        self._max = maxsize

    def seen(self, key: str) -> bool:
        """第一次见 key 返回 False 并记下；再次见同一 key 返回 True。空 key 不去重。"""
        if not key:
            return False
        with self._lock:
            if key in self._seen:
                return True
            self._seen[key] = True   # 只需键，FIFO 保留最近 _max 个
            while len(self._seen) > self._max:
                self._seen.popitem(last=False)
            return False

    def discard(self, key: str) -> None:
        """撤销一次 seen 记账。处理过程中途失败时调用，让平台重投的同一条能再被处理，
        而不是因已记账被永久判重吞掉。"""
        if not key:
            return
        with self._lock:
            self._seen.pop(key, None)
