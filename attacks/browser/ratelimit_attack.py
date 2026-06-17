"""Make the bot trip the server's rate limit (reputation.py).

Even a bot that *passes* the behavioral + proof-of-work layers — a humanized
trace plus a solved PoW on every request — gets caught the moment it does it at
volume from one client key. This driver runs that exact "good citizen" request
in a loop against the real server (server/app.py) and prints the decision
escalating: allow -> challenge (throttled) -> deny (blocked).

    python ratelimit_attack.py [--url http://127.0.0.1:5002] [--n 14]

It solves the PoW with the project's own reference solver and sends a trace from
tools/generate_human_trace.py, so the ONLY reason it gets stopped is frequency.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pow as powmod            # noqa: E402  (reference PoW solver)
import generate_human_trace as human  # noqa: E402

UA = "hca-ratelimit-bot/1.0"


def _get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read())


def _post(url, body, headers=None):
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json", "User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def passing_trace():
    """A humanized, behavioral-human trace with webdriver=false (stealthed bot)."""
    tr = human.generate((90, 410), (600, 250), seed=3)
    tr["meta"] = {"dpr": 1, "ua": UA, "webdriver": False}
    return tr


def run(args):
    base = args.url
    trace = passing_trace()
    timeline = []
    print(f"  flooding {base}/score as one client ({UA}) — PoW solved each time\n")
    print(f"  {'#':>3}  {'http':>4}  {'decision':<10}  short  long   reason")
    for i in range(1, args.n + 1):
        ch = _get(base + "/pow/challenge")
        nonce = powmod.solve(ch["salt"], ch["difficulty"])
        body = dict(trace)
        body["pow"] = {"salt": ch["salt"], "difficulty": ch["difficulty"],
                       "ts": ch["ts"], "sig": ch["sig"], "nonce": nonce}
        status, res = _post(base + "/score", body)
        decision = res.get("decision", "?")
        rep = res.get("reputation", {})
        sh = rep.get("short", {}); lo = rep.get("long", {})
        row = {"i": i, "http": status, "decision": decision,
               "short": f"{sh.get('count')}/{sh.get('limit')}",
               "long": f"{lo.get('count')}/{lo.get('limit')}",
               "state": rep.get("state"), "reason": res.get("reason", "")}
        timeline.append(row)
        print(f"  {i:>3}  {status:>4}  {decision:<10}  {row['short']:>5}  {row['long']:>5}  "
              f"{row['reason'][:60]}")
        if rep.get("state") == "blocked":
            print("\n  -> client BLOCKED (banned). The bot hit the rate limit.")
            break
        time.sleep(args.delay)

    out = {"engine": "rate-limit-flood", "url": base, "timeline": timeline,
           "tripped_challenge": any(r["decision"] == "challenge" for r in timeline),
           "tripped_block": any(r["state"] == "blocked" for r in timeline)}
    if args.json:
        print(json.dumps(out))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5002")
    ap.add_argument("--n", type=int, default=14)
    ap.add_argument("--delay", type=float, default=0.0)
    ap.add_argument("--json", action="store_true")
    run(ap.parse_args())
