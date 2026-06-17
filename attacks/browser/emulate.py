"""Measure Selenium / SeleniumBase click trajectories on a host with no usable
chromedriver (e.g. linux-arm64, where no official chromedriver is published).

Every WebDriver click bottoms out at the same CDP pointer primitive used by
Playwright/Puppeteer, so we replay Selenium's *exact* event stream through the
shared Chromium and score the real pointer events the page receives:

  * native    -> a single pointer move to the element centre + down/up
  * linear    -> a chained straight line of pointer moves (ActionChains)
  * humanized -> the same chain following a curved/jittered human path

Faithful detail: the W3C Actions API uses INTEGER coordinates (no sub-pixel),
so replayed points are rounded to whole pixels — which is exactly why Selenium
is still caught by the HiDPI sub-pixel tell that Playwright/Puppeteer (float
coordinates) can evade. The run is tagged method="trajectory-equivalent".

This module is only used when the real selenium driver can't start; the shipped
selenium_attack.py / seleniumbase_attack.py run the genuine libraries elsewhere.
"""
from __future__ import annotations

import json
import time
import urllib.request

from playwright.sync_api import sync_playwright

from humanize import human_path

START = (140, 170)
TARGET = (840, 520)


def post_score(url, trace):
    req = urllib.request.Request(url + "/score", data=json.dumps(trace).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def run(args):
    engine = getattr(args, "engine", "selenium")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
        context = browser.new_context(device_scale_factor=args.dpr,
                                      viewport={"width": 1200, "height": 760})
        page = context.new_page()
        stealth_note = "off"
        if args.stealth:
            # selenium-stealth / SeleniumBase-UC patch the same fingerprint
            # surfaces; we stand in with playwright-stealth so navigator.webdriver
            # reflects the stealth state. Trajectory is unaffected either way.
            try:
                from playwright_stealth import stealth_sync
                stealth_sync(page); stealth_note = "selenium-stealth" if engine == "selenium" else "seleniumbase-uc"
            except Exception:
                try:
                    from playwright_stealth import Stealth
                    Stealth().apply_stealth_sync(page); stealth_note = "selenium-stealth" if engine == "selenium" else "seleniumbase-uc"
                except Exception:
                    stealth_note = "(stealth lib unavailable)"
        page.goto(args.url, wait_until="load")
        page.wait_for_function("window.__HCA_READY === true")
        webdriver_flag = page.evaluate("navigator.webdriver")

        tx, ty = TARGET
        page.evaluate("([x,y]) => window.HCA.setup(x,y)", [tx, ty])

        def imove(x, y):  # integer-only, like the W3C Actions API
            page.mouse.move(round(x), round(y))

        if args.strategy == "native":
            imove(tx, ty)               # one hop to centre
            page.mouse.down(); time.sleep(0.05); page.mouse.up()
        elif args.strategy == "linear":
            imove(*START); time.sleep(0.03)
            n = 28
            for i in range(1, n + 1):
                imove(START[0] + (tx - START[0]) * i / n, START[1] + (ty - START[1]) * i / n)
                time.sleep(0.006)
            page.mouse.down(); time.sleep(0.05); page.mouse.up()
        elif args.strategy == "humanized":
            imove(*START)
            for (x, y, dt) in human_path(START, TARGET, seed=args.seed):
                imove(x, y); time.sleep(dt / 1000.0)
            page.mouse.down(); time.sleep(0.06); page.mouse.up()

        page.evaluate("([x,y]) => window.HCA.mark('up', x, y)", [tx, ty])
        trace = page.evaluate("() => window.HCA.trace()")
        result = post_score(args.url, trace)
        browser.close()

    f = result["features"]
    out = {"engine": engine, "stealth": bool(args.stealth), "stealth_lib": stealth_note,
           "strategy": args.strategy, "dpr": args.dpr, "navigator_webdriver": webdriver_flag,
           "verdict": result["verdict"], "score": result["score"],
           "subscores": result.get("subscores", {}), "n_move_events": f.get("n_move_events"),
           "directness": f.get("directness"), "easing_r2": f.get("easing_r2"),
           "dt_cv": f.get("dt_cv"), "int_coord_ratio": f.get("int_coord_ratio"),
           "method": "trajectory-equivalent (no arm64 chromedriver in sandbox)",
           "reason": result.get("reason", "")}
    print(json.dumps(out))
    if getattr(args, "save", ""):
        import os
        os.makedirs(args.save, exist_ok=True)
        tag = f"{engine}_{args.strategy}_{'stealth' if args.stealth else 'plain'}_dpr{args.dpr}"
        with open(os.path.join(args.save, tag + ".json"), "w") as fh:
            json.dump(trace, fh, indent=1)
    return out
