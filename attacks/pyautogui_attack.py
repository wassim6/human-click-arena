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
  --mode bezier     curved Bezier path, but otherwise machine-like: regular
                    timing, integer pixels, no tremor, one smooth speed profile.
                    Defeats the straightness + easing signals -- can it beat the
                    timing / sub-pixel / tremor / sub-movement checks too?
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


def attack_bezier(x: float, y: float, duration: float, steps: int, bow: float):
    """Curved Bezier move, but machine-like otherwise.

    Bends the path off the straight line (defeats straightness + easing fit) yet
    keeps constant inter-step timing, no tremor, and a single smooth speed --
    so it should still trip timing / sub-pixel / tremor / sub-movement signals.
    """
    start = pyautogui.position()
    target = (x, y)
    mx, my = (start[0] + target[0]) / 2, (start[1] + target[1]) / 2
    nx, ny = -(target[1] - start[1]), (target[0] - start[0])
    nlen = math.hypot(nx, ny) or 1.0
    dist = math.hypot(target[0] - start[0], target[1] - start[1])
    ctrl = (mx + nx / nlen * (bow * dist), my + ny / nlen * (bow * dist))

    step_delay = max(duration / steps, 0.0)
    for i in range(1, steps + 1):
        bx, by = _bezier(start, ctrl, target, i / steps)
        pyautogui.moveTo(bx, by, duration=0)
        time.sleep(step_delay)            # constant dt -> regular, bot-like
    pyautogui.click()


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


def _humanized_segment(start, target, rng):
    """Move from start to target along a gentle curve with tremor + irregular
    timing, while the mouse button is whatever it currently is (used for drags)."""
    mx, my = (start[0] + target[0]) / 2, (start[1] + target[1]) / 2
    nx, ny = -(target[1] - start[1]), (target[0] - start[0])
    nlen = math.hypot(nx, ny) or 1.0
    dist = math.hypot(target[0] - start[0], target[1] - start[1])
    bow = rng.uniform(0.05, 0.15) * dist             # gentler curve for a slider
    ctrl = (mx + nx / nlen * bow, my + ny / nlen * bow)
    steps = rng.randint(28, 40)
    for i in range(1, steps + 1):
        p = i / steps
        eased = p * p * (3 - 2 * p)
        bx, by = _bezier(start, ctrl, target, eased)
        bx += rng.gauss(0, 0.6)
        by += rng.gauss(0, 0.6)
        pyautogui.moveTo(bx, by, duration=0)
        time.sleep(rng.uniform(0.006, 0.020))


def humanized_drag(sx, sy, ex, ey, seed=None):
    """Press the piece and drag it onto the gap with human-like motion."""
    rng = random.Random(seed)
    pyautogui.moveTo(sx + rng.uniform(-2, 2), sy + rng.uniform(-2, 2),
                     duration=rng.uniform(0.18, 0.35), tween=pyautogui.easeOutQuad)
    pyautogui.mouseDown()
    time.sleep(rng.uniform(0.04, 0.10))
    _humanized_segment(pyautogui.position(), (ex, ey), rng)
    time.sleep(rng.uniform(0.03, 0.08))              # settle before releasing
    pyautogui.mouseUp()


def solve_puzzle(piece_img, gap_img, confidence, retina_scale, attempts=12):
    """Locate the slide puzzle's piece and gap on screen and drag one onto the
    other. Returns True if a puzzle was found and a drag performed."""
    for _ in range(attempts):
        piece = locate(piece_img, confidence, retina_scale)
        gap = locate(gap_img, confidence, retina_scale)
        if piece and gap:
            print(f"  puzzle found: piece {tuple(round(v) for v in piece)} -> "
                  f"gap {tuple(round(v) for v in gap)}; humanized drag")
            humanized_drag(piece[0], piece[1], gap[0], gap[1])
            return True
        time.sleep(0.4)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", default=DEFAULT_IMAGE, help="template to locate (default: click.png)")
    ap.add_argument("--mode", choices=["naive", "bezier", "humanized"], default="naive")
    ap.add_argument("--confidence", type=float, default=0.8, help="match confidence (needs opencv)")
    ap.add_argument("--duration", type=float, default=0.6, help="move duration (s), naive/bezier")
    ap.add_argument("--tween", default="easeInOutQuad", help="naive easing (pyautogui.<name>)")
    ap.add_argument("--steps", type=int, default=40, help="bezier: number of path samples")
    ap.add_argument("--bow", type=float, default=0.25, help="bezier: curve amount (frac of distance)")
    ap.add_argument("--retina-scale", type=float, default=1.0, help="set 2.0 on macOS Retina")
    ap.add_argument("--rounds", type=int, default=1, help="repeat the attack N times")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds before starting (go focus the page)")
    ap.add_argument("--solve-puzzle", action="store_true",
                    help="after clicking, drag the slide puzzle if it appears")
    ap.add_argument("--piece", default=os.path.join(HERE, "piece.png"),
                    help="template of the draggable puzzle piece")
    ap.add_argument("--gap", default=os.path.join(HERE, "gap.png"),
                    help="template of the dashed gap outline")
    args = ap.parse_args(argv)

    if not os.path.exists(args.image):
        sys.exit(f"template not found: {args.image}")
    if args.solve_puzzle:
        for tmpl in (args.piece, args.gap):
            if not os.path.exists(tmpl):
                sys.exit(f"puzzle template not found: {tmpl}")

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
        elif args.mode == "bezier":
            attack_bezier(x, y, args.duration, args.steps, args.bow)
        else:
            attack_humanized(x, y, seed=None)
        time.sleep(1.0)  # let the page score + relocate the target

        if args.solve_puzzle:
            if solve_puzzle(args.piece, args.gap, args.confidence, args.retina_scale):
                time.sleep(1.0)
            else:
                print("  no puzzle detected (allowed directly, or templates didn't match "
                      "-- lower --confidence or re-screenshot piece.png / gap.png)")

    print("done. Check the verdict panel on the demo page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
