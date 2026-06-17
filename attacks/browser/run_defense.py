"""Boot the real server (server/app.py) and run the two defense-layer attacks:

  1. rate-limit flood  -> the bot trips reputation.py (allow -> challenge -> block)
  2. slide puzzle       -> the bot solves it with a humanized drag

Writes defense_results.json.

    python run_defense.py [--port 5002]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, HERE)


def start_server(port):
    import app as server_app
    t = threading.Thread(
        target=lambda: server_app.app.run(host="127.0.0.1", port=port,
                                          debug=False, use_reloader=False),
        daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(url + "/pow/challenge", timeout=1)
            return url
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("server did not come up")


def reset(url):
    req = urllib.request.Request(url + "/reset", data=b"{}",
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5002)
    ap.add_argument("--out", default="defense_results.json")
    args = ap.parse_args()

    url = start_server(args.port)
    import ratelimit_attack
    import puzzle_attack

    print("\n=== 1) rate-limit flood (reputation.py) ===")
    reset(url)
    rl = ratelimit_attack.run(argparse.Namespace(url=url, n=14, delay=0.0, json=False))

    print("\n=== 2) slide puzzle (puzzle.py) — humanized drag ===")
    reset(url)
    pz = puzzle_attack.run(argparse.Namespace(url=url, seed=5))

    results = {"rate_limit": rl, "puzzle": pz}
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
