#!/usr/bin/env python3
"""Synthesize a *human-like* trace for testing the detector's positive case.

Real human traces are collected through the demo page; but CI needs a
deterministic human-like sample. This generator deliberately injects the four
things a naive PyAutoGUI move lacks:

  1. Curvature      -- a quadratic Bezier with an off-axis control point.
  2. Sub-movements  -- a ballistic overshoot followed by a corrective approach.
  3. Tremor         -- small per-sample Gaussian jitter (physiological noise).
  4. Irregular time -- jittered inter-event intervals.

This is a *model* of human motion, not a recording. It exists so the test suite
can assert that genuinely human-shaped input scores high. Treat real recordings
as ground truth.

Usage:
    python generate_human_trace.py --seed 7 | python ../server/score_cli.py
"""

import argparse
import json
import math
import random
import sys


def _bezier(p0, p1, p2, t):
    u = 1 - t
    x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
    y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
    return x, y


def generate(start, end, seed=7):
    rng = random.Random(seed)
    # control point pushed off the straight line => curvature
    mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
    nx, ny = -(end[1] - start[1]), (end[0] - start[0])
    nlen = math.hypot(nx, ny) or 1.0
    bow = rng.uniform(0.18, 0.32) * math.hypot(end[0] - start[0], end[1] - start[1])
    ctrl = (mx + nx / nlen * bow, my + ny / nlen * bow)

    # overshoot target slightly, then correct (two ballistic phases)
    overshoot = (end[0] + rng.uniform(8, 22), end[1] + rng.uniform(-14, 14))

    events = []
    t = 0.0
    n_main = rng.randint(34, 46)
    for i in range(n_main + 1):
        p = i / n_main
        # non-uniform speed: accelerate then decelerate, but noisy
        eased = p * p * (3 - 2 * p)          # smoothstep baseline
        x, y = _bezier(start, ctrl, overshoot, eased)
        x += rng.gauss(0, 0.8)               # tremor
        y += rng.gauss(0, 0.8)
        events.append({"type": "move", "x": round(x, 2), "y": round(y, 2), "t": round(t, 2)})
        t += rng.uniform(6, 21)              # irregular dt

    # corrective sub-movement from overshoot back to the real target
    n_corr = rng.randint(6, 11)
    for i in range(1, n_corr + 1):
        p = i / n_corr
        x = overshoot[0] + (end[0] - overshoot[0]) * p + rng.gauss(0, 0.6)
        y = overshoot[1] + (end[1] - overshoot[1]) * p + rng.gauss(0, 0.6)
        events.append({"type": "move", "x": round(x, 2), "y": round(y, 2), "t": round(t, 2)})
        t += rng.uniform(8, 26)

    t += rng.uniform(20, 60)                  # small hesitation before pressing
    events.append({"type": "down", "x": round(end[0], 2), "y": round(end[1], 2), "t": round(t, 2)})
    t += rng.uniform(55, 130)                 # variable dwell
    events.append({"type": "up", "x": round(end[0], 2), "y": round(end[1], 2), "t": round(t, 2)})

    return {
        "events": events,
        "target": {"x": round(end[0], 2), "y": round(end[1], 2), "r": 28},
        "_meta": {"source": "human-sim", "seed": seed},
    }


def _pair(s):
    a, b = s.split(",")
    return (float(a), float(b))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=_pair, default=(90.0, 410.0))
    ap.add_argument("--end", type=_pair, default=(600.0, 250.0))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    trace = generate(args.start, args.end, args.seed)
    json.dump(trace, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
