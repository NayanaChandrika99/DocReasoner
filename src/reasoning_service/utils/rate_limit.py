# ABOUTME: Provides a simple in-process rate limiter for tool usage.
# ABOUTME: Prevents hitting provider quotas by bounding calls per period.
"""Token-bucket style rate limiter used for tool calls."""

from __future__ import annotations

import time
from collections import deque
from typing import Deque


class RateLimiter:
    """Simple sliding-window rate limiter."""

    def __init__(self, max_calls: int, period_seconds: float) -> None:
        self.max_calls = max_calls
        self.period = period_seconds
        self._timestamps: Deque[float] = deque()

    def allow(self) -> bool:
        if self.max_calls <= 0:
            return True
        now = time.time()
        window_start = now - self.period
        while self._timestamps and self._timestamps[0] < window_start:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_calls:
            return False
        self._timestamps.append(now)
        return True
