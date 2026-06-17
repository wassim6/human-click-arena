#!/usr/bin/env python3
"""Live attack: drive the REAL OS mouse with pyautogui to beat the demo.

Unlike ``tools/generate_pyautogui_trace.py`` (which fabricates a JSON trace
offline for CI), this script controls the actual desktop cursor. It:

  1. takes a screenshot and locates the demo button using the template
     ``click.png`` (image recognition),
  2. moves the real OS pointer onto it,
  3. clicks.

Because this is OS-level input, the events the browser sees are
``isTrusted: true`` with no automation framework attached -- exactly the case
no client-side check can distinguish from a human hand. So whether you get
flagged depends entirely on the *shape* of the movement:

  --mode naive      straight line + a fixed easing tween  (the scorer catches this)
  --mode humanized  curved Bezier + tremor + variable timing + corrective
                    sub-movement + variable click dwell    (try to beat the scorer)

Run the demo first (``python server/app.py`` -> open http://127.0.0.1:5000),
make the CLICK button visible, then:

    pip install -r attacks/requirements.txt
    python attacks/pyautogui_attack.py --mode naive
    python attacks/pyautogui_attack.py --mode humanized --rounds 5

This is for testing your OWN demo / detector. Defensive research only.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time

try:
    import pyautogui
except ImportError:
    sys.exit("pyautogui is not installed. Run: pip install -r attacks/requirements.txt")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IMAGE = os.path.join(HERE, "click.png")

# Fail-safe: slam the mouse into a screen corner to abort.
pyautogui.FAILSAFE = True
# We control all timing ourselves, so disable pyautogui's built-in pause
# (otherwise it adds a constant delay after every call -> regular, bot-like dt).
pyautogui.PAUSE = 0


def locate(image: str, confidence: float, retina_scale: float):
    """Return (x, y) logical coordinates of the button center, or None."""
    try:
        center = pyautogui.locateCenterOnScreen(image, confidence=confidence)
    except TypeError:
        # confidence= needs opencv-python; fall back to exact pixel match.
        print("  (opencv not installed -> exact match; install opencv-python for confidence=)")
        center = pyautogui.locateCenterOnScreen(image)
    if center is None:
        return None
    # On Retina/HiDPI, screenshots are in physical pixels but moveTo uses
    # logical points. Pass --retina-scale 2 on a Mac Retina display.
    return (center.x / retina_scale, center.y / retina_scale)


def attack_naive(x: float, y: float, duration: float, tween: str):
    fn = getattr(pyautogui, tween, pyautogui.easeInOutQuad)
    pyautogui.moveTo(x, y, duration=duration, tween=fn)  # straight line, eased
    pyautogui.click()


def _bezier(p0, p1, p2, t):
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])


def attack_humanized(x: float, y: float, seed: int | None = None):
    """Curved path + tremor + irregular timing + overshoot/correct + varied dwell."""
    rng = random.Random(seed)
    start = pyautogui.position()
    target = (x, y)

    # control point pushed off the straight line => curvature
    mx, my = (start[0] + target[0]) / 2, (start[1] + target[1]) / 2
    nx, ny = -(target[1] - start[1]), (target[0] - start[0])
    nlen = math.hypot(nx, ny) or 1.0
    dist = math.hypot(target[0] - start[0], target[1] - start[1])
    bow = rng.uniform(0.15, 0.30) * dist
    ctrl = (mx + nx / nlen * bow, my + ny / nlen * bow)

    # slight overshoot, then a corrective sub-movement back to target
    overshoot = (target[0] + rng.uniform(6, 18), target[1] + rng.uniform(-12, 12))

    steps = rng.randint(34, 46)
    for i in range(1, steps + 1):
        p = i / steps
        eased = p * p * (3 - 2 * p)                 # smoothstep, noisy below
        bx, by = _bezier(start, ctrl, overshoot, eased)
        bx += rng.gauss(0, 0.7)                      # tremor
        by += rng.gauss(0, 0.7)
        pyautogui.moveTo(bx, by, duration=0)
        time.sleep(rng.uniform(0.006, 0.020))        # irregular dt

    corr = rng.randint(6, 10)
    for i in range(1, corr + 1):
        p = i / corr
        cx = overshoot[0] + (target[0] - overshoot[0]) * p + rng.gauss(0, 0.5)
        cy = overshoot[1] + (target[1] - overshoot[1]) * p + rng.gauss(0, 0.5)
        pyautogui.moveTo(cx, cy, duration=0)
        time.sleep(rng.uniform(0.008, 0.026))

    time.sleep(rng.uniform(0.03, 0.09))              # hesitation before press
    pyautogui.mouseDown()
    time.sleep(rng.uniform(0.055, 0.130))            # variable dwell
    pyautogui.mouseUp()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", default=DEFAULT_IMAGE, help="template to locate (default: click.png)")
    ap.add_argument("--mode", choices=["naive", "humanized"], default="naive")
    ap.add_argument("--confidence", type=float, default=0.8, help="match confidence (needs opencv)")
    ap.add_argument("--duration", type=float, default=0.6, help="naive move duration (s)")
    ap.add_argument("--tween", default="easeInOutQuad", help="naive easing (pyautogui.<name>)")
    ap.add_argument("--retina-scale", type=float, default=1.0, help="set 2.0 on macOS Retina")
    ap.add_argument("--rounds", type=int, default=1, help="repeat the attack N times")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds before starting (go focus the page)")
    args = ap.parse_args(argv)

    if not os.path.exists(args.image):
        sys.exit(f"template not found: {args.image}")

    print(f"Starting in {args.delay}s -- focus the demo page and reveal the CLICK button.")
    print("(slam the mouse into a screen corner to abort)")
    time.sleep(args.delay)

    for r in range(args.rounds):
        pos = locate(args.image, args.confidence, args.retina_scale)
        if pos is None:
            print(f"[round {r+1}] button not found on screen. Tips: lower --confidence, "
                  f"make sure the button is fully visible, or re-create click.png from a "
                  f"screenshot of YOUR screen (Retina renders at 2x -> try --retina-scale 2).")
            return 1
        x, y = pos
        print(f"[round {r+1}] found at ({x:.0f}, {y:.0f}) -> {args.mode} attack")
        if args.mode == "naive":
            attack_naive(x, y, args.duration, args.tween)
        else:
            attack_humanized(x, y, seed=None)
        time.sleep(1.0)  # let the page score + relocate the target

    print("done. Check the verdict panel on the demo page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
