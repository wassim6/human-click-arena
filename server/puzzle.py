"""Visual slide-to-fit challenge (the human-facing escalation).

When a decision is borderline ("challenge"), we show a puzzle: drag a piece
into a gap at a random position. The server issues the gap position signed with
an HMAC (stateless, single-use, time-limited), and verifies on release that:

  1. the signature/expiry/single-use checks pass,
  2. the released position matches the gap within tolerance, and
  3. the drag was a *real drag* (enough move samples over enough time and
     distance) -- not an instant "post the target" with no interaction.

Note (honest): the gap position is visible to the client, so a determined bot
can read it and produce a human-looking drag to it -- the same wall as the main
click. This raises cost and gives a real UX step; it is not unbeatable.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import random
import secrets
import time
from collections import deque

_SECRET = os.environ.get("PUZZLE_SECRET", secrets.token_hex(32)).encode()
TTL_S = 180
TOLERANCE = 0.06            # released must be within 6% of the gap
MIN_MOVES = 5
MIN_DURATION_MS = 150
MIN_TRAVEL_PX = 20

_spent: "deque[tuple[str, float]]" = deque()
_spent_set: set[str] = set()


def _sign(salt: str, target: float, tol: float, ts: int) -> str:
    msg = f"{salt}.{target:.4f}.{tol:.4f}.{ts}".encode()
    return hmac.new(_SECRET, msg, hashlib.sha256).hexdigest()


def make_challenge() -> dict:
    salt = secrets.token_hex(10)
    target = round(random.uniform(0.40, 0.85), 4)   # gap sits on the right side
    ts = int(time.time())
    return {
        "salt": salt,
        "target": target,
        "tol": TOLERANCE,
        "ts": ts,
        "sig": _sign(salt, target, TOLERANCE, ts),
        "type": "puzzle",
    }


def _gc(now: float) -> None:
    while _spent and _spent[0][1] < now:
        salt, _ = _spent.popleft()
        _spent_set.discard(salt)


def reset() -> None:
    _spent.clear()
    _spent_set.clear()


def _drag_is_live(trace: dict | None) -> tuple[bool, str]:
    if not isinstance(trace, dict):
        return False, "no drag recorded"
    moves = [e for e in trace.get("events", []) if e.get("type") == "move"]
    if len(moves) < MIN_MOVES:
        return False, "drag too short (looks like a teleport)"
    dur = float(moves[-1]["t"]) - float(moves[0]["t"])
    if dur < MIN_DURATION_MS:
        return False, "drag too fast"
    xs = [float(m["x"]) for m in moves]
    if max(xs) - min(xs) < MIN_TRAVEL_PX:
        return False, "piece barely moved"
    return True, "ok"


def verify(solution: dict) -> tuple[bool, str]:
    if not isinstance(solution, dict):
        return False, "no solution"
    try:
        salt = str(solution["salt"])
        target = float(solution["target"])
        tol = float(solution["tol"])
        ts = int(solution["ts"])
        sig = str(solution["sig"])
        released = float(solution["released"])
    except (KeyError, ValueError, TypeError):
        return False, "malformed solution"

    now = time.time()
    _gc(now)

    if not hmac.compare_digest(sig, _sign(salt, target, tol, ts)):
        return False, "bad signature"
    if now - ts > TTL_S:
        return False, "challenge expired"
    if salt in _spent_set:
        return False, "challenge already used"
    if abs(released - target) > tol:
        return False, "piece not aligned with the gap"

    live, why = _drag_is_live(solution.get("trace"))
    if not live:
        return False, why

    _spent_set.add(salt)
    _spent.append((salt, ts + TTL_S))
    return True, "ok"
