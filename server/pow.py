"""Stateless proof-of-work — memory-hard (Argon2id) by default.

PoW does NOT tell a bot from a human. It makes every *attempt* cost real work,
so the attack the behavioral + sub-pixel layers can't stop -- a humanized
real-browser click on a 1x display -- becomes expensive at scale.

Two algorithms are supported, selected per challenge and signed so the client
can't downgrade:

  - "argon2id" (default): each hash is **memory-hard** (8 MiB here), so GPUs and
    ASICs can't make grinding cheap. This is the ALTCHA-style hardening.
  - "sha256": cheap CPU hash, kept as a fallback for clients without a WASM
    Argon2 (the browser solver falls back to it if hash-wasm can't load).

The client finds a nonce whose hash has >= `difficulty` leading zero bits. The
server verifies a single hash. Challenges are HMAC-signed (stateless) with
single-use salts (replay protection).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import deque

try:
    from argon2.low_level import Type, hash_secret_raw
    ARGON2_AVAILABLE = True
except Exception:                       # pragma: no cover - depends on install
    ARGON2_AVAILABLE = False

_SECRET = os.environ.get("POW_SECRET", secrets.token_hex(32)).encode()

# Argon2id cost. Memory is the point (GPU/ASIC resistance); keep difficulty low
# because each hash is already expensive.
ARGON_M = int(os.environ.get("POW_ARGON_M_KIB", "8192"))   # 8 MiB
ARGON_T = int(os.environ.get("POW_ARGON_T", "2"))
ARGON_P = int(os.environ.get("POW_ARGON_P", "1"))

DEFAULT_BITS = {
    "argon2id": int(os.environ.get("POW_ARGON_BITS", "5")),
    "sha256": int(os.environ.get("POW_SHA_BITS", "14")),
}
DEFAULT_ALG = os.environ.get("POW_ALG", "argon2id")
if DEFAULT_ALG == "argon2id" and not ARGON2_AVAILABLE:
    DEFAULT_ALG = "sha256"

CHALLENGE_TTL_S = 120

_spent: "deque[tuple[str, float]]" = deque()
_spent_set: set[str] = set()


def _sign(salt: str, alg: str, difficulty: int, m: int, t: int, p: int, ts: int) -> str:
    msg = f"{salt}.{alg}.{difficulty}.{m}.{t}.{p}.{ts}".encode()
    return hmac.new(_SECRET, msg, hashlib.sha256).hexdigest()


def make_challenge(difficulty: int | None = None, alg: str | None = None) -> dict:
    alg = (alg or DEFAULT_ALG)
    if alg == "argon2id" and not ARGON2_AVAILABLE:
        alg = "sha256"
    if alg not in DEFAULT_BITS:
        alg = "sha256"
    difficulty = int(difficulty if difficulty is not None else DEFAULT_BITS[alg])
    m, t, p = (ARGON_M, ARGON_T, ARGON_P) if alg == "argon2id" else (0, 0, 0)
    salt = secrets.token_hex(12)
    ts = int(time.time())
    return {
        "salt": salt, "alg": alg, "difficulty": difficulty,
        "m": m, "t": t, "p": p, "ts": ts,
        "sig": _sign(salt, alg, difficulty, m, t, p, ts),
    }


def _digest(alg: str, salt: str, nonce: str, m: int, t: int, p: int) -> bytes:
    if alg == "argon2id":
        return hash_secret_raw(secret=str(nonce).encode(), salt=salt.encode(),
                               time_cost=t, memory_cost=m, parallelism=p,
                               hash_len=32, type=Type.ID)
    return hashlib.sha256(f"{salt}.{nonce}".encode()).digest()


def leading_zero_bits(digest: bytes) -> int:
    bits = 0
    for byte in digest:
        if byte == 0:
            bits += 8
            continue
        bits += 8 - byte.bit_length()
        break
    return bits


def _gc_spent(now: float) -> None:
    while _spent and _spent[0][1] < now:
        salt, _ = _spent.popleft()
        _spent_set.discard(salt)


def reset() -> None:
    _spent.clear()
    _spent_set.clear()


def verify(solution: dict) -> tuple[bool, str]:
    if not isinstance(solution, dict):
        return False, "no solution"
    try:
        salt = str(solution["salt"])
        alg = str(solution.get("alg", "sha256"))
        difficulty = int(solution["difficulty"])
        m = int(solution.get("m", 0))
        t = int(solution.get("t", 0))
        p = int(solution.get("p", 0))
        ts = int(solution["ts"])
        sig = str(solution["sig"])
        nonce = str(solution["nonce"])
    except (KeyError, ValueError, TypeError):
        return False, "malformed solution"

    if alg == "argon2id" and not ARGON2_AVAILABLE:
        return False, "argon2 unavailable on server"

    now = time.time()
    _gc_spent(now)

    if not hmac.compare_digest(sig, _sign(salt, alg, difficulty, m, t, p, ts)):
        return False, "bad signature"
    if now - ts > CHALLENGE_TTL_S:
        return False, "challenge expired"
    if salt in _spent_set:
        return False, "challenge already used"
    if leading_zero_bits(_digest(alg, salt, nonce, m, t, p)) < difficulty:
        return False, "insufficient work"

    _spent_set.add(salt)
    _spent.append((salt, ts + CHALLENGE_TTL_S))
    return True, "ok"


def solve(challenge: dict, max_iter: int = 1 << 26) -> int:
    """Reference solver (tests / CLI). The browser does this in JS/WASM."""
    salt = str(challenge["salt"])
    alg = str(challenge.get("alg", "sha256"))
    difficulty = int(challenge["difficulty"])
    m, t, p = int(challenge.get("m", 0)), int(challenge.get("t", 0)), int(challenge.get("p", 0))
    nonce = 0
    while nonce < max_iter:
        if leading_zero_bits(_digest(alg, salt, str(nonce), m, t, p)) >= difficulty:
            return nonce
        nonce += 1
    raise RuntimeError("no solution found within max_iter")
