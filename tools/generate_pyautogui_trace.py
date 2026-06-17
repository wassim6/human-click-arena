#!/usr/bin/env python3
"""Generate a trace the way PyAutoGUI / selenium-base UC-mode would produce one.

PyAutoGUI's `moveTo(x, y, duration, tween)` walks the cursor in a STRAIGHT LINE
in screen space, sampling at near-regular time steps, with progress along the
line driven by a tween (easing) function. There is no curvature, no tremor, no
corrective sub-movement, and the click dwell is constant.

This script REPLICATES that math so the test suite and CI can run without a GUI
or a real desktop. It is the "attacker, naive setting" baseline for the arena.

Usage:
    python generate_pyautogui_trace.py --tween easeInOutQuad
    python generate_pyautogui_trace.py --start 80,400 --end 600,250 --duration 0.6 | \
        python ../server/score_cli.py
"""

import argparse
import json
import math
import sys


def linear(n):
    return n


def ease_in_out_quad(n):
    if n < 0.5:
        return 2 * n * n
    return -0.5 * ((2 * n - 1) * (2 * n - 3) - 1)


def ease_in_out_cubic(n):
    n *= 2
    if n < 1:
        return 0.5 * n ** 3
    n -= 2
    return 0.5 * (n ** 3 + 2)


def ease_in_quad(n):
    return n * n


def ease_out_quad(n):
    return -n * (n - 2)


def ease_in_out_sine(n):
    return -0.5 * (math.cos(math.pi * n) - 1)


TWEENS = {
    "linear": linear,
    "easeInQuad": ease_in_quad,
    "easeOutQuad": ease_out_quad,
    "easeInOutQuad": ease_in_out_quad,
    "easeInOutCubic": ease_in_out_cubic,
    "easeInOutSine": ease_in_out_sine,
}


def generate(start, end, duration_s, tween, min_sleep=0.0125):
    """Mirror pyautogui._mouseMoveDrag step sampling."""
    fn = TWEENS[tween]
    steps = max(int(duration_s / min_sleep), 1)
    events = []
    for i in range(steps + 1):
        p = fn(i / steps)
        x = start[0] + (end[0] - start[0]) * p
        y = start[1] + (end[1] - start[1]) * p
        t_ms = (duration_s * 1000.0) * (i / steps)
        events.append({"type": "move", "x": round(x, 2), "y": round(y, 2), "t": round(t_ms, 2)})

    click_t = duration_s * 1000.0
    events.append({"type": "down", "x": round(end[0], 2), "y": round(end[1], 2), "t": round(click_t + 5, 2)})
    events.append({"type": "up", "x": round(end[0], 2), "y": round(end[1], 2), "t": round(click_t + 65, 2)})

    return {
        "events": events,
        "target": {"x": round(end[0], 2), "y": round(end[1], 2), "r": 28},
        "_meta": {"source": "pyautogui-sim", "tween": tween, "duration_s": duration_s},
    }


def _pair(s):
    a, b = s.split(",")
    return (float(a), float(b))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=_pair, default=(80.0, 400.0))
    ap.add_argument("--end", type=_pair, default=(600.0, 250.0))
    ap.add_argument("--duration", type=float, default=0.6, help="seconds")
    ap.add_argument("--tween", choices=sorted(TWEENS), default="easeInOutQuad")
    args = ap.parse_args(argv)

    trace = generate(args.start, args.end, args.duration, args.tween)
    json.dump(trace, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
