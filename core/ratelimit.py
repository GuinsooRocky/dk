"""出站限速器（R1）—— per-channel token-bucket，防刷屏/撞平台频控。

战略 §12：当前个人规模其实用不上，所以默认**宽松**（20 条/分钟/渠道）不挡正常用量，
只在真刷屏时把消息节流排队。**超限不静默吞**：acquire() 阻塞等到有令牌（或超时），
让消息延迟发出而不是被丢。纯 stdlib（threading/time），各渠道 venv 都能 import。
"""
import threading
import time

DEFAULT_RATE_PER_MIN = 20


class TokenBucket:
    def __init__(self, rate_per_min: int = DEFAULT_RATE_PER_MIN):
        self.capacity = float(max(1, rate_per_min))
        self.refill_per_sec = self.capacity / 60.0
        self.tokens = self.capacity
        self.updated = time.monotonic()
        self.lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.refill_per_sec)
        self.updated = now

    def try_acquire(self) -> bool:
        """非阻塞拿一个令牌；没有则 False（调用方自己决定排队还是放弃）。"""
        with self.lock:
            self._refill()
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False

    def acquire(self, timeout: float = 30.0) -> bool:
        """阻塞等到有令牌（超限排队不静默吞）；timeout 内拿不到返回 False。"""
        deadline = time.monotonic() + timeout
        while True:
            with self.lock:
                self._refill()
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                need = (1 - self.tokens) / self.refill_per_sec
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(need, remaining, 0.5))


_buckets: dict = {}
_buckets_lock = threading.Lock()


def _bucket(channel: str) -> TokenBucket:
    with _buckets_lock:
        b = _buckets.get(channel)
        if b is None:
            b = TokenBucket()
            _buckets[channel] = b
        return b


def try_acquire(channel: str) -> bool:
    return _bucket(channel).try_acquire()


def acquire(channel: str, timeout: float = 30.0) -> bool:
    return _bucket(channel).acquire(timeout)
