"""Drive the harness with SeleniumBase and score the resulting click.

Usage:
    python seleniumbase_attack.py --strategy native|linear|humanized \
        [--stealth] [--dpr 1] [--url http://127.0.0.1:5001] [--save DIR]

--stealth enables SeleniumBase UC mode (undetected-chromedriver based). Like the
other stealth options it targets *fingerprint* surfaces, not pointer trajectory,
so the behavioral score should match the plain run.

SeleniumBase wraps Selenium, so movement uses the same ActionChains primitives.
Needs a matching chromedriver (no official linux-arm64 build exists; run on
x86_64/macOS).
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

from seleniumbase import SB
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from humanize import human_path
from selenium_attack import _summary, _save  # reuse helpers

START = (140, 170)
TARGET = (840, 520)


def post_score(url, trace):
    req = urllib.request.Request(url + "/score", data=json.dumps(trace).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def chain_path(driver, steps):
    act = ActionChains(driver, duration=0)
    body = driver.find_element(By.TAG_NAME, "body")
    act.move_to_element_with_offset(body, 1, 1)
    prev = None
    for (x, y, dt) in steps:
        if prev is None:
            act.move_by_offset(x - 1, y - 1)
        else:
            act.move_by_offset(x - prev[0], y - prev[1])
        act.pause(max(0.004, dt / 1000.0))
        prev = (x, y)
    act.click_and_hold(); act.pause(0.06); act.release(); act.perform()


def run(args):
    tx, ty = TARGET
    with SB(uc=bool(args.stealth), headless=True, browser="chrome") as sb:
        sb.open(args.url)
        sb.wait_for_ready_state_complete()
        sb.execute_script("return window.__HCA_READY === true")
        webdriver_flag = sb.execute_script("return navigator.webdriver")
        sb.execute_script("window.HCA.setup(arguments[0], arguments[1]);", tx, ty)
        driver = sb.driver

        if args.strategy == "native":
            sb.click("#target")
        elif args.strategy == "linear":
            n = 28
            steps = [(START[0] + (tx - START[0]) * i / n,
                      START[1] + (ty - START[1]) * i / n, 6.0) for i in range(n + 1)]
            chain_path(driver, steps)
        elif args.strategy == "humanized":
            chain_path(driver, human_path(START, TARGET, seed=args.seed))

        sb.execute_script("window.HCA.mark('up', arguments[0], arguments[1]);", tx, ty)
        trace = sb.execute_script("return window.HCA.trace();")
        result = post_score(args.url, trace)

    stealth_note = "seleniumbase-uc" if args.stealth else "off"
    out = _summary("seleniumbase", args, stealth_note, webdriver_flag, result)
    print(json.dumps(out))
    _save(args, "seleniumbase", trace)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=["native", "linear", "humanized"], default="native")
    ap.add_argument("--stealth", action="store_true")
    ap.add_argument("--dpr", type=float, default=1.0)
    ap.add_argument("--url", default="http://127.0.0.1:5001")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--save", default="")
    run(ap.parse_args())
