"""Human-like pointer path generator (curved + jittered + overshoot).

Used by the Playwright/Selenium drivers' `humanized` strategy. This is a
representative re-implementation of what libraries like ghost-cursor produce:
a curved Bezier path, irregular per-step timing, physiological-style jitter,
and an overshoot-then-correct near the target (a second sub-movement).

Returns a list of (x, y, dt_ms) steps to feed to a mouse API.
"""
from __future__ import annotations

import math
import random


def _bezier(p0, p1, p2, p3, t):
    u = 1 - t
    x = (u**3) * p0[0] + 3 * (u**2) * t * p1[0] + 3 * u * (t**2) * p2[0] + (t**3) * p3[0]
    y = (u**3) * p0[1] + 3 * (u**2) * t * p1[1] + 3 * u * (t**2) * p2[1] + (t**3) * p3[1]
    return x, y


def human_path(start, end, seed=None, overshoot=True):
    rng = random.Random(seed)
    sx, sy = start
    ex, ey = end
    dist = math.hypot(ex - sx, ey - sy)

    # Perpendicular unit vector to bow the path sideways (curvature).
    dx, dy = ex - sx, ey - sy
    plen = math.hypot(dx, dy) or 1.0
    px, py = -dy / plen, dx / plen
    bow = rng.uniform(0.12, 0.28) * dist * rng.choice([-1, 1])

    c1 = (sx + dx * 0.30 + px * bow, sy + dy * 0.30 + py * bow)
    c2 = (sx + dx * 0.70 + px * bow * 0.6, sy + dy * 0.70 + py * bow * 0.6)

    # Optional overshoot target (we aim slightly past, then correct back).
    aim = end
    if overshoot:
        over = rng.uniform(8, 22)
        aim = (ex + dx / plen * over, ey + dy / plen * over)

    n_main = max(18, int(dist / 14))
    steps = []
    prev = start
    for i in range(1, n_main + 1):
        t = i / n_main
        # ease-in-out but with per-step noise so timing is irregular
        x, y = _bezier(start, c1, c2, aim, t)
        x += rng.gauss(0, 0.6)   # tremor / jitter (sub-pixel + integer mix)
        y += rng.gauss(0, 0.6)
        base = 16 * (0.5 - 0.5 * math.cos(math.pi * t))  # slow-fast-slow
        dt = max(4.0, base + rng.gauss(0, 5))
        steps.append((x, y, dt))
        prev = (x, y)

    if overshoot:
        # corrective sub-movement back onto the real target
        n_corr = rng.randint(4, 7)
        for i in range(1, n_corr + 1):
            t = i / n_corr
            x = prev[0] + (ex - prev[0]) * t + rng.gauss(0, 0.4)
            y = prev[1] + (ey - prev[1]) * t + rng.gauss(0, 0.4)
            steps.append((x, y, max(6.0, rng.gauss(22, 7))))
    # land exactly on target
    steps.append((ex, ey, max(6.0, rng.gauss(18, 5))))
    return steps
