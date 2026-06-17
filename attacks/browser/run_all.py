"""Boot the harness server in-process and run every engine/strategy combo.

This is the one-command runner for the browser-automation arena. It starts the
Flask scorer on a background thread, then invokes each available engine driver
across strategies (native / linear / humanized) x (plain / stealth), collects
the scores, and writes a results table to results.json.

    python run_all.py [--engines playwright,puppeteer,selenium,seleniumbase]
                      [--port 5001] [--dpr 1] [--out results.json]

Engines whose dependencies are missing are skipped with a note (so it still
runs end-to-end with whatever is installed).
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.request


def start_server(port):
    import harness_server
    t = threading.Thread(
        target=lambda: harness_server.app.run(host="127.0.0.1", port=port,
                                              debug=False, use_reloader=False),
        daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(url + "/", timeout=1)
            return url
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("harness server did not come up")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default="playwright,puppeteer,selenium,seleniumbase")
    ap.add_argument("--port", type=int, default=5001)
    ap.add_argument("--dpr", type=float, default=1.0)
    ap.add_argument("--strategies", default="native,linear,humanized")
    ap.add_argument("--out", default="results.json")
    ap.add_argument("--save", default="captured")
    args = ap.parse_args()

    url = start_server(args.port)
    engines = args.engines.split(",")
    strategies = args.strategies.split(",")
    results = []

    # Python-driven engines call their run() directly; node engines via subprocess.
    py_drivers = {}
    try:
        import playwright_attack
        py_drivers["playwright"] = playwright_attack
    except Exception as e:
        print("playwright import failed:", e)
    try:
        import selenium_attack
        py_drivers["selenium"] = selenium_attack
    except Exception as e:
        print("selenium import failed:", e)
    try:
        import seleniumbase_attack
        py_drivers["seleniumbase"] = seleniumbase_attack
    except Exception as e:
        print("seleniumbase import failed:", e)

    for engine in engines:
        for strat in strategies:
            for stealth in (False, True):
                ns = argparse.Namespace(strategy=strat, stealth=stealth, dpr=args.dpr,
                                        url=url, seed=7, save=args.save)
                try:
                    if engine in py_drivers:
                        r = py_drivers[engine].run(ns)
                    elif engine == "puppeteer":
                        r = run_node(url, strat, stealth, args.dpr, args.save)
                    else:
                        continue
                    results.append(r)
                    print(f"{engine:13} {strat:10} {'stealth' if stealth else 'plain':8} "
                          f"-> {r['verdict']:10} {r['score']}")
                except Exception as e:
                    print(f"{engine:13} {strat:10} {'stealth' if stealth else 'plain':8} "
                          f"-> ERROR {e}")
                    results.append({"engine": engine, "strategy": strat,
                                    "stealth": stealth, "error": str(e)})

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {len(results)} results to {args.out}")


def run_node(url, strat, stealth, dpr, save):
    import subprocess
    cmd = ["node", "puppeteer_attack.js", "--strategy", strat, "--dpr", str(dpr),
           "--url", url, "--save", save]
    if stealth:
        cmd.append("--stealth")
    out = subprocess.check_output(cmd, text=True, timeout=120)
    return json.loads(out.strip().splitlines()[-1])


if __name__ == "__main__":
    main()
