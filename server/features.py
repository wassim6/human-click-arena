"""Extract behavioral features from a pointer trace.

A trace is a dict: {"events": [...], "target": {...}} where each event is
{"type": "move"|"down"|"up", "x": float, "y": float, "t": float_ms}.

These features are the raw signals the scorer turns into a human/bot score.
They are intentionally simple and readable -- this is a teaching/arena repo,
not a black box. Beat them and send a PR.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from easing import best_easing_fit


def _moves(events: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xs, ys, ts = [], [], []
    for e in events:
        if e.get("type") == "move":
            xs.append(float(e["x"]))
            ys.append(float(e["y"]))
            ts.append(float(e["t"]))
    return np.array(xs), np.array(ys), np.array(ts)


def _click_dwell_ms(events: list[dict]) -> float | None:
    t_down = t_up = None
    for e in events:
        if e.get("type") == "down" and t_down is None:
            t_down = float(e["t"])
        elif e.get("type") == "up" and t_down is not None and t_up is None:
            t_up = float(e["t"])
    if t_down is None or t_up is None:
        return None
    return t_up - t_down


def extract(trace: dict[str, Any]) -> dict[str, Any]:
    events = trace.get("events", [])
    x, y, t = _moves(events)
    n = x.size

    f: dict[str, Any] = {
        "n_move_events": int(n),
        "has_movement": bool(n >= 2),
        "click_dwell_ms": _click_dwell_ms(events),
    }

    if n < 2:
        # No movement before the click is itself the strongest bot signal.
        f.update(
            directness=1.0,
            max_perp_deviation=0.0,
            dt_cv=0.0,
            n_velocity_peaks=0,
            mean_abs_turn_rad=0.0,
            easing_name="none",
            easing_r2=1.0 if n == 0 else 0.0,
            total_time_ms=0.0,
            path_length_px=0.0,
        )
        return f

    # --- geometry ---------------------------------------------------------
    dx = np.diff(x)
    dy = np.diff(y)
    seg = np.hypot(dx, dy)
    path_length = float(np.sum(seg))
    displacement = float(np.hypot(x[-1] - x[0], y[-1] - y[0]))
    directness = displacement / path_length if path_length > 0 else 1.0

    # perpendicular deviation from the straight start->end line
    start = np.array([x[0], y[0]])
    end = np.array([x[-1], y[-1]])
    line = end - start
    line_len = np.hypot(*line)
    if line_len > 0:
        unit = line / line_len
        rel = np.stack([x - start[0], y - start[1]], axis=1)
        proj = rel @ unit                       # progress in px along the line
        perp = np.abs(rel[:, 0] * unit[1] - rel[:, 1] * unit[0])
        max_perp = float(np.max(perp)) / line_len
        progress = np.clip(proj / line_len, 0.0, 1.0)
    else:
        max_perp = 0.0
        progress = np.linspace(0, 1, n)

    # --- timing -----------------------------------------------------------
    dt = np.diff(t)
    dt = dt[dt > 0] if np.any(dt > 0) else dt
    total_time = float(t[-1] - t[0])
    if dt.size and np.mean(dt) > 0:
        dt_cv = float(np.std(dt) / np.mean(dt))   # ~0 for bots, larger for humans
    else:
        dt_cv = 0.0

    # --- velocity / sub-movements ----------------------------------------
    dt_full = np.diff(t)
    dt_full[dt_full == 0] = 1e-6
    speed = seg / dt_full
    n_peaks = _count_peaks(speed)

    # --- tremor / jitter: mean absolute turning angle between segments ----
    mean_abs_turn = _mean_abs_turn(dx, dy)

    # --- easing fit (timing along the line vs known tweens) ---------------
    if total_time > 0:
        tau = (t - t[0]) / total_time
    else:
        tau = np.linspace(0, 1, n)
    easing_name, easing_r2 = best_easing_fit(progress, tau)

    f.update(
        directness=round(directness, 5),
        max_perp_deviation=round(max_perp, 5),
        dt_cv=round(dt_cv, 5),
        n_velocity_peaks=int(n_peaks),
        mean_abs_turn_rad=round(float(mean_abs_turn), 5),
        easing_name=easing_name,
        easing_r2=round(float(easing_r2), 5),
        total_time_ms=round(total_time, 2),
        path_length_px=round(path_length, 2),
    )
    return f


def _count_peaks(speed: np.ndarray) -> int:
    """Count local maxima in the speed profile (proxy for sub-movements).

    Humans correct toward a target with several ballistic sub-movements, so the
    speed profile has multiple humps; a single eased move has one."""
    if speed.size < 3:
        return 1
    # light smoothing to avoid counting sample noise as peaks
    k = np.array([0.25, 0.5, 0.25])
    s = np.convolve(speed, k, mode="same")
    thresh = 0.1 * float(np.max(s)) if np.max(s) > 0 else 0.0
    peaks = 0
    for i in range(1, s.size - 1):
        if s[i] > s[i - 1] and s[i] >= s[i + 1] and s[i] > thresh:
            peaks += 1
    return max(peaks, 1)


def _mean_abs_turn(dx: np.ndarray, dy: np.ndarray) -> float:
    """Mean absolute change of direction between consecutive segments (radians).

    Near 0 for a straight eased line; non-trivial for a jittery human path."""
    ang = np.arctan2(dy, dx)
    if ang.size < 2:
        return 0.0
    dang = np.diff(ang)
    dang = (dang + np.pi) % (2 * np.pi) - np.pi   # wrap to [-pi, pi]
    return float(np.mean(np.abs(dang)))
