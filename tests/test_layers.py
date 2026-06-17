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
    ch = json.loads(client.get("/pow/challenge").data)
    nonce = P.solve(ch["salt"], ch["difficulty"])
    return dict(body, pow=dict(ch, nonce=str(nonce)))


# ---- proof of work --------------------------------------------------------

def test_pow_roundtrip_and_replay():
    ch = P.make_challenge(12)
    nonce = P.solve(ch["salt"], ch["difficulty"])
    ok, _ = P.verify(dict(ch, nonce=str(nonce)))
    assert ok
    ok2, msg2 = P.verify(dict(ch, nonce=str(nonce)))   # replay
    assert not ok2 and "used" in msg2


def test_pow_rejects_wrong_work():
    ch = P.make_challenge(20)
    ok, msg = P.verify(dict(ch, nonce="0"))            # nonce 0 won't meet 20 bits
    assert not ok and "insufficient" in msg


# ---- reputation -----------------------------------------------------------

def test_reputation_escalates():
    rep = Reputation(window_s=60, soft=3, hard=5)
    states = [rep.assess("k")["state"] for _ in range(6)]
    assert states[0] == "ok"
    assert "throttled" in states
    assert states[-1] == "blocked"


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


def test_challenge_escalation_endpoint():
    client = A.app.test_client()
    # solving the escalated proof-of-work clears the challenge
    ch = json.loads(client.get(f"/pow/challenge?bits={A.ESCALATED_BITS}").data)
    nonce = P.solve(ch["salt"], ch["difficulty"])
    r = json.loads(client.post("/challenge/verify", json={"pow": dict(ch, nonce=str(nonce))}).data)
    assert r["decision"] == "allow"
    # a too-easy solution does not
    ch2 = json.loads(client.get("/pow/challenge?bits=8").data)
    n2 = P.solve(ch2["salt"], ch2["difficulty"])
    r2 = json.loads(client.post("/challenge/verify", json={"pow": dict(ch2, nonce=str(n2))}).data)
    assert r2["decision"] == "deny"


def test_volume_gets_denied_even_when_behavior_says_human():
    A.reputation = Reputation(window_s=60, soft=8, hard=20)
    require = A.REQUIRE_POW
    A.REQUIRE_POW = False                 # isolate the reputation layer
    try:
        client = A.app.test_client()
        trace = _load(HUMANIZED_1X)
        decisions = [json.loads(client.post("/score", json=trace).data)["decision"]
                     for _ in range(25)]
    finally:
        A.REQUIRE_POW = require
    assert decisions[0] == "allow"
    assert decisions[-1] == "deny"        # same human-looking click, denied at volume
