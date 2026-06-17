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


def chain_path(driver, steps, slowmo=0):
    # Drive the W3C pointer with ABSOLUTE viewport coordinates via
    # move_to_location. Selenium 4's move_to_element_with_offset measures from
    # the element *center*, which pushed the cumulative path past the viewport
    # edge -> "move target out of bounds". move_to_location takes integer
    # viewport coords (origin = top-left), so the path stays in bounds AND every
    # sample is a whole pixel -> int_coord_ratio = 1.0: exactly the W3C-integer
    # tell we want to show. slowmo = extra ms per pause so you can watch it.
    from selenium.webdriver.common.actions.action_builder import ActionBuilder
    from selenium.webdriver.common.actions.pointer_input import PointerInput
    from selenium.webdriver.common.actions import interaction

    extra = (slowmo or 0) / 1000.0
    mouse = PointerInput(interaction.POINTER_MOUSE, "mouse")
    builder = ActionBuilder(driver, mouse=mouse, duration=0)
    p = builder.pointer_action
    for (x, y, dt) in steps:
        p.move_to_location(int(round(x)), int(round(y)))
        p.pause(max(0.004, dt / 1000.0) + extra)
    p.pointer_down()
    p.pause(0.06)
    p.pointer_up()
    builder.perform()


def run(args):
    tx, ty = TARGET
    headed = getattr(args, "headed", False)
    slowmo = getattr(args, "slowmo", 0) or 0
    with SB(uc=bool(args.stealth), headless=not headed, browser="chrome") as sb:
        sb.open(args.url)
        sb.wait_for_ready_state_complete()
        driver = sb.driver
        # Apply --dpr via CDP emulation instead of --force-device-scale-factor.
        # force-device-scale-factor shrinks the *real* window's CSS viewport in
        # headed mode (=> "move target out of bounds" at 840,520). Emulation sets
        # devicePixelRatio AND a fixed 1200x760 CSS layout viewport, independent of
        # the OS window, so the drag stays in bounds and the HiDPI gate still fires.
        if args.dpr and float(args.dpr) != 1.0:
            driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width": 1200, "height": 760,
                "deviceScaleFactor": float(args.dpr), "mobile": False})
        sb.execute_script("return window.__HCA_READY === true")
        webdriver_flag = sb.execute_script("return navigator.webdriver")
        sb.execute_script("window.HCA.setup(arguments[0], arguments[1]);", tx, ty)

        if args.strategy == "native":
            sb.click("#target")
        elif args.strategy == "linear":
            n = 28
            steps = [(START[0] + (tx - START[0]) * i / n,
                      START[1] + (ty - START[1]) * i / n, 6.0) for i in range(n + 1)]
            chain_path(driver, steps, slowmo=slowmo)
        elif args.strategy == "humanized":
            chain_path(driver, human_path(START, TARGET, seed=args.seed), slowmo=slowmo)

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
    ap.add_argument("--headed", action="store_true",
                    help="show a real browser window instead of headless")
    ap.add_argument("--slowmo", type=int, default=0,
                    help="extra ms added to each move pause so you can watch the "
                         "drag (inflates timing features; does NOT affect "
                         "int_coord_ratio / the HiDPI tell)")
    run(ap.parse_args())
