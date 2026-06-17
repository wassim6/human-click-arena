"""PyAutoGUI / pytweening easing functions, and a fit test against them.

PyAutoGUI moves the cursor in a straight line in screen space and parameterizes
*progress along that line over time* with one of these easing functions (the
default is `linear`). A real human hand does not follow any of them.

So if we project a movement onto its own start->end line, take the progress
fraction at each timestamp, and find that it fits one of these curves with a
near-perfect R^2, the movement was almost certainly machine-generated.

The functions are vectorized (operate on numpy arrays of n in [0, 1]).
"""

from __future__ import annotations

import numpy as np

TWO = 2.0


def linear(n):
    return n


def ease_in_quad(n):
    return n ** 2


def ease_out_quad(n):
    return -n * (n - 2)


def ease_in_out_quad(n):
    n = np.asarray(n, dtype=float)
    out = np.where(n < 0.5, 2 * n ** 2, -0.5 * ((2 * n - 1) * (2 * n - 3) - 1))
    return out


def ease_in_cubic(n):
    return n ** 3


def ease_out_cubic(n):
    m = n - 1
    return m ** 3 + 1


def ease_in_out_cubic(n):
    n = np.asarray(n, dtype=float) * 2
    return np.where(n < 1, 0.5 * n ** 3, 0.5 * ((n - 2) ** 3 + 2))


def ease_in_quart(n):
    return n ** 4


def ease_out_quart(n):
    m = n - 1
    return -(m ** 4 - 1)


def ease_in_sine(n):
    return -1 * np.cos(np.asarray(n) * np.pi / 2) + 1


def ease_out_sine(n):
    return np.sin(np.asarray(n) * np.pi / 2)


def ease_in_out_sine(n):
    return -0.5 * (np.cos(np.pi * np.asarray(n)) - 1)


# Name -> callable. These mirror the tween set PyAutoGUI exposes via pytweening.
EASINGS = {
    "linear": linear,
    "easeInQuad": ease_in_quad,
    "easeOutQuad": ease_out_quad,
    "easeInOutQuad": ease_in_out_quad,
    "easeInCubic": ease_in_cubic,
    "easeOutCubic": ease_out_cubic,
    "easeInOutCubic": ease_in_out_cubic,
    "easeInQuart": ease_in_quart,
    "easeOutQuart": ease_out_quart,
    "easeInSine": ease_in_sine,
    "easeOutSine": ease_out_sine,
    "easeInOutSine": ease_in_out_sine,
}


def _r2(observed: np.ndarray, predicted: np.ndarray) -> float:
    observed = np.asarray(observed, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    ss_res = float(np.sum((observed - predicted) ** 2))
    ss_tot = float(np.sum((observed - np.mean(observed)) ** 2))
    if ss_tot == 0:
        return 0.0
    return 1.0 - ss_res / ss_tot


def best_easing_fit(progress: np.ndarray, tau: np.ndarray) -> tuple[str, float]:
    """Return (easing_name, r2) for the best-matching easing function.

    progress: fraction along the start->end line at each sample, in [0, 1].
    tau:      normalized time at each sample, in [0, 1].
    A high r2 (near 1.0) means the timing matches a known tween => bot-like.
    """
    progress = np.asarray(progress, dtype=float)
    tau = np.asarray(tau, dtype=float)
    if progress.size < 3:
        return ("none", 0.0)

    best_name, best_r2 = "none", -np.inf
    for name, fn in EASINGS.items():
        predicted = np.asarray(fn(tau), dtype=float)
        r2 = _r2(progress, predicted)
        if r2 > best_r2:
            best_name, best_r2 = name, r2
    return (best_name, float(max(best_r2, 0.0)))
