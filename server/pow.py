"""Stateless proof-of-work challenge (ALTCHA-style, simplified).

PoW does NOT tell a bot from a human. It makes every *attempt* cost CPU, so the
attack that the behavioral + sub-pixel layers cannot stop -- a humanized
real-browser click on a 1x display -- becomes expensive to do at scale. One
click costs nothing to a human; a million clicks cost a botnet real money.

Design: the server signs each challenge with an HMAC secret, so it does not
need to store issued challenges (stateless verify). The client must find a
nonce such that SHA-256("{salt}.{nonce}") has at least `difficulty` leading
zero bits. We additionally remember spent salts for the challenge TTL to stop
trivial replay.

Production hardening (left as a note, not implemented here): swap SHA-256 for a
memory-hard function (Argon2id / scrypt) so GPUs/ASICs don't make PoW cheap.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import deque

# Secret for signing challenges. Set POW_SECRET in production; ephemeral here.
_SECRET = os.environ.get("POW_SECRET", secrets.token_hex(32)).encode()

DEFAULT_BITS = int(os.environ.get("POW_BITS", "14"))   # ~16k expected hashes
CHALLENGE_TTL_S = 120

# Spent salts (replay protection) with their expiry; small in-memory ring.
_spent: "deque[tuple[str, float]]" = deque()
_spent_set: set[str] = set()


def _sign(salt: str, difficulty: int, ts: int) -> str:
    msg = f"{salt}.{difficulty}.{ts}".encode()
    return hmac.new(_SECRET, msg, hashlib.sha256).hexdigest()


def make_challenge(difficulty: int | None = None) -> dict:
    difficulty = int(difficulty if difficulty is not None else DEFAULT_BITS)
    salt = secrets.token_hex(12)
    ts = int(time.time())
    return {
        "salt": salt,
        "difficulty": difficulty,
        "ts": ts,
        "sig": _sign(salt, difficulty, ts),
        "alg": "sha256-leading-zero-bits",
    }


def leading_zero_bits(digest: bytes) -> int:
    bits = 0
    for byte in digest:
        if byte == 0:
            bits += 8
            continue
        # count leading zeros in this byte
        bits += 8 - byte.bit_length()
        break
    return bits


def _gc_spent(now: float) -> None:
    while _spent and _spent[0][1] < now:
        salt, _ = _spent.popleft()
        _spent_set.discard(salt)


def verify(solution: dict) -> tuple[bool, str]:
    """Verify a PoW solution dict {salt, difficulty, ts, sig, nonce}."""
    if not isinstance(solution, dict):
        return False, "no solution"
    try:
        salt = str(solution["salt"])
        difficulty = int(solution["difficulty"])
        ts = int(solution["ts"])
        sig = str(solution["sig"])
        nonce = str(solution["nonce"])
    except (KeyError, ValueError, TypeError):
        return False, "malformed solution"

    now = time.time()
    _gc_spent(now)

    if not hmac.compare_digest(sig, _sign(salt, difficulty, ts)):
        return False, "bad signature"
    if now - ts > CHALLENGE_TTL_S:
        return False, "challenge expired"
    if salt in _spent_set:
        return False, "challenge already used"

    digest = hashlib.sha256(f"{salt}.{nonce}".encode()).digest()
    if leading_zero_bits(digest) < difficulty:
        return False, "insufficient work"

    _spent_set.add(salt)
    _spent.append((salt, ts + CHALLENGE_TTL_S))
    return True, "ok"


def reset() -> None:
    """Forget spent salts (demo convenience; replay protection starts fresh)."""
    _spent.clear()
    _spent_set.clear()


def solve(salt: str, difficulty: int, max_iter: int = 1 << 26) -> int:
    """Reference solver (used by tests / CLI). The browser does this in JS."""
    nonce = 0
    while nonce < max_iter:
        digest = hashlib.sha256(f"{salt}.{nonce}".encode()).digest()
        if leading_zero_bits(digest) >= difficulty:
            return nonce
        nonce += 1
    raise RuntimeError("no solution found within max_iter")
