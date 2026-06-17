"""Drive the harness with Playwright and score the resulting click.

Usage:
    python playwright_attack.py --strategy native|linear|humanized \
        [--stealth] [--dpr 1] [--url http://127.0.0.1:5001] [--save DIR]

Strategies:
    native     -> page.click(target): the high-level click most scrapers use.
    linear     -> mouse.move(target, steps=N): a straight, evenly-timed glide.
    humanized  -> curved Bezier path with jitter + overshoot/correct.

--stealth applies playwright-stealth (patches navigator.webdriver etc.). It does
NOT change pointer trajectories, so the behavioral score is expected to match
the non-stealth run.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

from playwright.sync_api import sync_playwright

from humanize import human_path

START = (140, 170)
TARGET = (840, 520)


def post_score(url, trace):
    req = urllib.request.Request(
        url + "/score", data=json.dumps(trace).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def apply_stealth(page):
    # Try both common package layouts of playwright-stealth.
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
        return "playwright-stealth"
    except Exception:
        pass
    try:
        from playwright_stealth import Stealth
        Stealth().apply_stealth_sync(page)
        return "playwright-stealth"
    except Exception:
        return "playwright-stealth(unavailable)"


def run(args):
    with sync_playwright() as p:
        headless = not getattr(args, "headed", False)
        slow_mo = getattr(args, "slowmo", 0) or 0
        launch_args = ["--no-sandbox"]
        if headless:
            launch_args.append("--disable-gpu")  # GPU off only matters headless
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo,
                                    args=launch_args)
        context = browser.new_context(device_scale_factor=args.dpr,
                                      viewport={"width": 1200, "height": 760})
        page = context.new_page()
        stealth_note = "off"
        if args.stealth:
            stealth_note = apply_stealth(page)
        page.goto(args.url, wait_until="load")
        page.wait_for_function("window.__HCA_READY === true")
        webdriver_flag = page.evaluate("navigator.webdriver")

        tx, ty = TARGET
        page.evaluate("([x,y]) => window.HCA.setup(x,y)", [tx, ty])

        if args.strategy == "native":
            # one hop to center + click — what driver.click() / page.click() does
            page.click("#target")
        elif args.strategy == "linear":
            page.mouse.move(*START)
            time.sleep(0.05)
            page.mouse.move(tx, ty, steps=28)   # straight line, regular timing
            page.mouse.down()
            time.sleep(0.05)
            page.mouse.up()
        elif args.strategy == "humanized":
            page.mouse.move(*START)
            for (x, y, dt) in human_path(START, TARGET, seed=args.seed):
                page.mouse.move(x, y)
                time.sleep(dt / 1000.0)
            page.mouse.down()
            time.sleep(0.06 + (args.seed % 5) / 100.0)
            page.mouse.up()

        # ensure release captured, then read the real collector trace + score
        page.evaluate("([x,y]) => window.HCA.mark('up', x, y)", [tx, ty])
        trace = page.evaluate("() => window.HCA.trace()")
        result = post_score(args.url, trace)
        browser.close()

    out = {
        "engine": "playwright",
        "stealth": bool(args.stealth),
        "stealth_lib": stealth_note,
        "strategy": args.strategy,
        "dpr": args.dpr,
        "navigator_webdriver": webdriver_flag,
        "verdict": result["verdict"],
        "score": result["score"],
        "subscores": result.get("subscores", {}),
        "n_move_events": result["features"].get("n_move_events"),
        "directness": result["features"].get("directness"),
        "easing_r2": result["features"].get("easing_r2"),
        "dt_cv": result["features"].get("dt_cv"),
        "int_coord_ratio": result["features"].get("int_coord_ratio"),
        "reason": result.get("reason", ""),
    }
    print(json.dumps(out))
    if args.save:
        import os
        os.makedirs(args.save, exist_ok=True)
        tag = f"playwright_{args.strategy}_{'stealth' if args.stealth else 'plain'}_dpr{args.dpr}"
        with open(os.path.join(args.save, tag + ".json"), "w") as f:
            json.dump(trace, f, indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=["native", "linear", "humanized"], default="native")
    ap.add_argument("--stealth", action="store_true")
    ap.add_argument("--dpr", type=float, default=1.0)
    ap.add_argument("--url", default="http://127.0.0.1:5001")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--save", default="")
    ap.add_argument("--headed", action="store_true",
                    help="show a real browser window instead of headless")
    ap.add_argument("--slowmo", type=int, default=0,
                    help="ms of delay before each Playwright action, so you can "
                         "watch the cursor (inflates timing features; does NOT "
                         "affect the int_coord_ratio / sub-pixel tell)")
    run(ap.parse_args())
