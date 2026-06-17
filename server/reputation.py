"""Sliding-window rate limiting + a tiny reputation signal.

The behavioral and sub-pixel layers judge a single click. This layer judges a
*client over time*. A humanized real-browser click is indistinguishable from a
human once -- but a bot has to do it thousands of times, and that volume from
one IP / fingerprint is the thing you can actually catch.

This is an in-memory stub for the demo. In production you would back it with
Redis (shared across servers) and key on a robust fingerprint + ASN/IP
reputation feeds. The logic is the same: count recent attempts per key, and
escalate from ok -> throttle -> block.
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque


class Reputation:
    def __init__(self, window_s: float = 300.0, soft: int = 2, hard: int = 3):
        # `hard` is the max attempts ALLOWED per window; the (hard+1)-th is blocked.
        # Default: at most 3 attempts per 5 minutes, throttle after 2.
        self.window_s = window_s
        self.soft = soft          # exceed -> start throttling (challenge)
        self.hard = hard          # exceed -> block (deny)
        self._hits: dict[str, deque] = defaultdict(deque)

    @staticmethod
    def key(ip: str, user_agent: str = "", dpr: float | int = 1) -> str:
        """Coarse client fingerprint. Deliberately simple and documented as such:
        a real system would use far more, and an attacker can rotate any of it."""
        raw = f"{ip}|{user_agent}|{dpr}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def reset(self, key: str | None = None) -> None:
        """Clear the rate-limit history. With no key, clears every client
        (handy for the local demo); with a key, clears just that client."""
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)

    def assess(self, key: str) -> dict:
        now = time.time()
        dq = self._hits[key]
        dq.append(now)
        cutoff = now - self.window_s
        while dq and dq[0] < cutoff:
            dq.popleft()

        rate = len(dq)
        if rate > self.hard:
            state = "blocked"
        elif rate > self.soft:
            state = "throttled"
        else:
            state = "ok"

        return {
            "key": key,
            "attempts_in_window": rate,
            "window_s": self.window_s,
            "state": state,
            "soft": self.soft,
            "hard": self.hard,
        }
