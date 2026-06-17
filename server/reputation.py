"""Two-tier rate limiting + a temporary ban.

The behavioral and sub-pixel layers judge a single click. This layer judges a
*client over time* with two windows:

  - short tier:  more than `short_limit` attempts per `short_window`  -> CHALLENGE
                 (escalate: make them solve a harder proof-of-work)
  - long tier:   more than `long_limit`  attempts per `long_window`   -> BLOCK
                 (ban the client for `ban_seconds`)

Defaults: > 3 per 5 min -> challenge; > 10 per 30 min -> blocked for 1 hour.

A humanized real-browser click is indistinguishable from a human once -- but a
bot has to do it many times, and that volume from one key is what you catch.

In-memory stub for the demo; production would back this with Redis (shared
across servers) and key on a robust fingerprint + ASN/IP reputation feeds.
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque


class Reputation:
    def __init__(
        self,
        short_window: float = 300.0,    # 5 minutes
        short_limit: int = 3,           # > this in short_window -> challenge
        long_window: float = 1800.0,    # 30 minutes
        long_limit: int = 10,           # > this in long_window -> block
        ban_seconds: float = 3600.0,    # blocked for 1 hour
    ):
        self.short_window = short_window
        self.short_limit = short_limit
        self.long_window = long_window
        self.long_limit = long_limit
        self.ban_seconds = ban_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._ban_until: dict[str, float] = {}

    @staticmethod
    def key(ip: str, user_agent: str = "", dpr: float | int = 1) -> str:
        """Coarse client fingerprint. Deliberately simple and documented as such:
        a real system would use far more, and an attacker can rotate any of it."""
        raw = f"{ip}|{user_agent}|{dpr}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def reset(self, key: str | None = None) -> None:
        """Clear history (and any ban). No key clears every client (demo)."""
        if key is None:
            self._hits.clear()
            self._ban_until.clear()
        else:
            self._hits.pop(key, None)
            self._ban_until.pop(key, None)

    def assess(self, key: str) -> dict:
        now = time.time()
        dq = self._hits[key]
        banned = self._ban_until.get(key, 0.0) > now

        if not banned:
            dq.append(now)

        # keep only the last `long_window` seconds of history
        cutoff = now - self.long_window
        while dq and dq[0] < cutoff:
            dq.popleft()

        long_count = len(dq)
        short_cutoff = now - self.short_window
        short_count = sum(1 for t in dq if t >= short_cutoff)

        if banned:
            state = "blocked"
        elif long_count > self.long_limit:
            self._ban_until[key] = now + self.ban_seconds   # trip the 1h ban
            state = "blocked"
        elif short_count > self.short_limit:
            state = "throttled"                              # -> challenge
        else:
            state = "ok"

        out = {
            "key": key,
            "state": state,
            "short": {"count": short_count, "limit": self.short_limit,
                      "window_s": self.short_window},
            "long": {"count": long_count, "limit": self.long_limit,
                     "window_s": self.long_window},
            "ban_seconds": self.ban_seconds,
        }
        if state == "blocked":
            out["retry_after_s"] = max(0, round(self._ban_until.get(key, now) - now))
        return out
