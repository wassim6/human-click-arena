"""Tests for the server layers: proof-of-work, reputation, and the combined
decision -- including the honest gap (humanized@1x passes behavior) and the
catch (volume gets denied)."""

import json
import os
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "server"))

pytest.importorskip("flask")

import app as A                  # noqa: E402
import pow as P                  # noqa: E402
from reputation import Reputation  # noqa: E402
from scorer import score         # noqa: E402

HUMANIZED_1X = os.path.join(HERE, "fixtures", "pyautogui_humanized_1x.json")
NAIVE = os.path.join(HERE, "fixtures", "pyautogui_real_naive.json")


def _load(path):
    with open(path) as fh:
        return json.load(fh)


def _solved(client, body):
    # use sha256 in tests so solving is instant (argon2id is exercised separately)
    ch = json.loads(client.get("/pow/challenge?alg=sha256").data)
    nonce = P.solve(ch)
    return dict(body, pow=dict(ch, nonce=str(nonce)))


# ---- proof of work --------------------------------------------------------

def test_pow_sha256_roundtrip_and_replay():
    ch = P.make_challenge(12, alg="sha256")
    nonce = P.solve(ch)
    ok, _ = P.verify(dict(ch, nonce=str(nonce)))
    assert ok
    ok2, msg2 = P.verify(dict(ch, nonce=str(nonce)))   # replay
    assert not ok2 and "used" in msg2


def test_pow_rejects_wrong_work():
    ch = P.make_challenge(20, alg="sha256")
    ok, msg = P.verify(dict(ch, nonce="0"))            # nonce 0 won't meet 20 bits
    assert not ok and "insufficient" in msg


def test_pow_argon2id_is_memory_hard_and_round_trips():
    if not P.ARGON2_AVAILABLE:
        import pytest as _pt
        _pt.skip("argon2-cffi not installed")
    ch = P.make_challenge(4, alg="argon2id")           # low bits: each hash is costly
    assert ch["alg"] == "argon2id" and ch["m"] >= 1024  # memory-hard params signed in
    nonce = P.solve(ch)
    ok, _ = P.verify(dict(ch, nonce=str(nonce)))
    assert ok
    # tampering with the memory cost breaks the signature
    bad = dict(ch, m=8, nonce=str(nonce))
    ok2, msg2 = P.verify(bad)
    assert not ok2 and "signature" in msg2


# ---- reputation -----------------------------------------------------------

def test_reputation_two_tiers():
    # > 3 per short window -> throttled (challenge); > 10 per long window -> blocked
    rep = Reputation(short_window=300, short_limit=3, long_window=1800, long_limit=10)
    states = [rep.assess("k")["state"] for _ in range(12)]
    assert states[:3] == ["ok", "ok", "ok"]
    assert states[3] == "throttled"
    assert states[-1] == "blocked"


def test_ban_persists_for_an_hour():
    rep = Reputation(short_limit=3, long_limit=5, ban_seconds=3600)
    for _ in range(6):
        rep.assess("k")                 # trips the ban on the 6th (> 5)
    a = rep.assess("k")                 # still banned afterwards
    assert a["state"] == "blocked"
    assert 0 < a["retry_after_s"] <= 3600


# ---- combined decision ----------------------------------------------------

def test_humanized_1x_passes_behavioral_but_is_the_known_gap():
    """The reference bypass: behavior alone calls it human."""
    result = score(_load(HUMANIZED_1X))
    assert result["verdict"] == "human"
    assert result["score"] >= 0.5


def test_layered_endpoint_allow_deny_paths():
    A.reputation = Reputation()
    client = A.app.test_client()
    trace = _load(HUMANIZED_1X)

    # with valid PoW + low volume -> allow (honest: we can't deny a single one)
    r = json.loads(client.post("/score", json=_solved(client, trace)).data)
    assert r["decision"] == "allow"

    # missing PoW -> deny
    A.reputation = Reputation()
    r = json.loads(client.post("/score", json=trace).data)
    assert r["decision"] == "deny" and "proof-of-work" in r["reason"]

    # naive bot with valid PoW -> deny on behavior
    A.reputation = Reputation()
    r = json.loads(client.post("/score", json=_solved(client, _load(NAIVE))).data)
    assert r["decision"] == "deny" and r["behavioral"]["verdict"] == "bot"


def test_visual_puzzle_challenge():
    import puzzle as Z
    moves = {"events": [{"type": "move", "x": 80 + i * 6, "y": 40, "t": i * 28.0} for i in range(14)]}

    ch = Z.make_challenge()
    ok, _ = Z.verify(dict(ch, released=ch["target"], trace=moves))
    assert ok                                                 # aligned + real drag

    ok2, m2 = Z.verify(dict(ch, released=ch["target"], trace=moves))
    assert not ok2 and "used" in m2                           # replay

    ch2 = Z.make_challenge()
    ok3, m3 = Z.verify(dict(ch2, released=max(0.0, ch2["target"] - 0.4), trace=moves))
    assert not ok3 and "aligned" in m3                        # wrong position

    ch3 = Z.make_challenge()
    ok4, _ = Z.verify(dict(ch3, released=ch3["target"],
                           trace={"events": [{"type": "move", "x": 1, "y": 1, "t": 0}]}))
    assert not ok4                                            # teleport, no real drag


def test_challenge_escalation_endpoint():
    client = A.app.test_client()
    # solving the escalated proof-of-work clears the challenge (sha256 -> fast in tests)
    ch = json.loads(client.get(f"/pow/challenge?alg=sha256&bits={A.ESCALATED_BITS}").data)
    nonce = P.solve(ch)
    r = json.loads(client.post("/challenge/verify", json={"pow": dict(ch, nonce=str(nonce))}).data)
    assert r["decision"] == "allow"
    # a too-easy solution does not
    ch2 = json.loads(client.get("/pow/challenge?alg=sha256&bits=8").data)
    n2 = P.solve(ch2)
    r2 = json.loads(client.post("/challenge/verify", json={"pow": dict(ch2, nonce=str(n2))}).data)
    assert r2["decision"] == "deny"


def test_volume_gets_denied_even_when_behavior_says_human():
    A.reputation = Reputation()           # defaults: >3/5min challenge, >10/30min block
    require = A.REQUIRE_POW
    A.REQUIRE_POW = False                  # isolate the reputation layer
    try:
        client = A.app.test_client()
        trace = _load(HUMANIZED_1X)
        decisions = [json.loads(client.post("/score", json=trace).data)["decision"]
                     for _ in range(15)]
    finally:
        A.REQUIRE_POW = require
    assert decisions[0] == "allow"         # human-looking click is allowed at first
    assert "challenge" in decisions        # then escalated (> 3 in 5 min)
    assert decisions[-1] == "deny"         # then blocked at volume (> 10 in 30 min)
