"""Drive the harness with Selenium WebDriver and score the resulting click.

Usage:
    python selenium_attack.py --strategy native|linear|humanized \
        [--stealth] [--dpr 1] [--url http://127.0.0.1:5001] [--save DIR]

Strategies:
    native     -> element.click(): WebDriver "Element Click" = one pointer move
                  to the in-view centre + down + up (no real trajectory).
    linear     -> a manually chained straight line of micro ActionChains moves.
    humanized  -> the same chain following a curved/jittered human path.

--stealth applies selenium-stealth (navigator.webdriver, WebGL vendor, ...). It
does NOT change pointer trajectories, so the behavioral score should match plain.

Note: Selenium needs a matching chromedriver (Selenium Manager fetches it). There
is no official linux-arm64 chromedriver, so this runs on x86_64/macOS, not on an
arm64 box. Set $CHROME_BIN to reuse a specific Chrome/Chromium binary.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from humanize import human_path

START = (140, 170)
TARGET = (840, 520)


def post_score(url, trace):
    req = urllib.request.Request(url + "/score", data=json.dumps(trace).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def make_driver(dpr):
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1200,760")
    opts.add_argument(f"--force-device-scale-factor={dpr}")
    if os.environ.get("CHROME_BIN"):
        opts.binary_location = os.environ["CHROME_BIN"]
    return webdriver.Chrome(options=opts)


def chain_path(driver, steps):
    """Replay a list of (x,y,dt_ms) absolute points as chained pointer moves."""
    act = ActionChains(driver, duration=0)
    prev = None
    body = driver.find_element(By.TAG_NAME, "body")
    act.move_to_element_with_offset(body, 1, 1)
    for (x, y, dt) in steps:
        if prev is None:
            act.move_by_offset(x - 1, y - 1)
        else:
            act.move_by_offset(x - prev[0], y - prev[1])
        act.pause(max(0.004, dt / 1000.0))
        prev = (x, y)
    act.click_and_hold()
    act.pause(0.06)
    act.release()
    act.perform()


def run(args):
    driver = make_driver(args.dpr)
    stealth_note = "off"
    try:
        if args.stealth:
            from selenium_stealth import stealth
            stealth(driver, languages=["en-US", "en"], vendor="Google Inc.",
                    platform="Win32", webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine", fix_hairline=True)
            stealth_note = "selenium-stealth"
        driver.get(args.url)
        WebDriverWait(driver, 10).until(lambda d: d.execute_script("return window.__HCA_READY === true"))
        webdriver_flag = driver.execute_script("return navigator.webdriver")
        tx, ty = TARGET
        driver.execute_script("window.HCA.setup(arguments[0], arguments[1]);", tx, ty)

        if args.strategy == "native":
            driver.find_element(By.ID, "target").click()
        elif args.strategy == "linear":
            n = 28
            steps = [(START[0] + (tx - START[0]) * i / n,
                      START[1] + (ty - START[1]) * i / n, 6.0) for i in range(n + 1)]
            chain_path(driver, steps)
        elif args.strategy == "humanized":
            chain_path(driver, human_path(START, TARGET, seed=args.seed))

        driver.execute_script("window.HCA.mark('up', arguments[0], arguments[1]);", tx, ty)
        trace = driver.execute_script("return window.HCA.trace();")
        result = post_score(args.url, trace)
    finally:
        driver.quit()

    out = _summary("selenium", args, stealth_note, webdriver_flag, result)
    print(json.dumps(out))
    _save(args, "selenium", trace)
    return out


def _summary(engine, args, stealth_note, webdriver_flag, result):
    f = result["features"]
    return {"engine": engine, "stealth": bool(args.stealth), "stealth_lib": stealth_note,
            "strategy": args.strategy, "dpr": args.dpr, "navigator_webdriver": webdriver_flag,
            "verdict": result["verdict"], "score": result["score"],
            "subscores": result.get("subscores", {}), "n_move_events": f.get("n_move_events"),
            "directness": f.get("directness"), "easing_r2": f.get("easing_r2"),
            "dt_cv": f.get("dt_cv"), "int_coord_ratio": f.get("int_coord_ratio"),
            "reason": result.get("reason", "")}


def _save(args, engine, trace):
    if not args.save:
        return
    os.makedirs(args.save, exist_ok=True)
    tag = f"{engine}_{args.strategy}_{'stealth' if args.stealth else 'plain'}_dpr{args.dpr}"
    with open(os.path.join(args.save, tag + ".json"), "w") as fh:
        json.dump(trace, fh, indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=["native", "linear", "humanized"], default="native")
    ap.add_argument("--stealth", action="store_true")
    ap.add_argument("--dpr", type=float, default=1.0)
    ap.add_argument("--url", default="http://127.0.0.1:5001")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--save", default="")
    run(ap.parse_args())
