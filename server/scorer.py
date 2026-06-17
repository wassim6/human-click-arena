"""Turn trace features into a human-likeness score in [0, 1].

1.0 = looks like a real human hand.  0.0 = looks generated.

This v1 scorer is a deliberately TRANSPARENT weighted heuristic. That is a
feature, not a bug: the arena is meant to be readable and beatable. The
intended end state is to replace this function with a model trained on the
labeled human/bot traces the arena collects (every accepted bypass becomes a
training example). The feature extraction stays; only `score()` gets smarter.

Each sub-signal is mapped to [0, 1] where 1 = human-like, then combined.
"""

from __future__ import annotations

from typing import Any

from features import extract


def _ramp(value: float, lo: float, hi: float) -> float:
    """Linear map: value<=lo -> 0.0, value>=hi -> 1.0 (clamped)."""
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


# Weights for each behavioral sub-signal (need not sum to 1; normalized below).
WEIGHTS = {
    "straightness": 1.4,   # bots travel in a straight line
    "easing": 1.6,         # bots match a known tween almost perfectly
    "timing": 1.2,         # bots emit events at very regular intervals
    "submovements": 1.0,   # humans correct with several velocity peaks
    "tremor": 1.0,         # humans have physiological jitter
}


def score(trace: dict[str, Any]) -> dict[str, Any]:
    f = extract(trace)

    # Hard gate: a click with no preceding movement is the loudest bot signal.
    if not f["has_movement"]:
        return {
            "score": 0.0,
            "verdict": "bot",
            "reason": "no pointer movement before click",
            "subscores": {},
            "features": f,
        }

    # --- map each feature to a human-likeness sub-score in [0, 1] ----------
    # directness ~1.0 => straight line => bot. Humans curve (lower directness).
    s_straight = _ramp(0.997 - f["directness"], 0.0, 0.097)      # d<=0.997 .. d>=0.90
    # easing R^2 near 1.0 => matches a tween => bot.
    s_easing = _ramp(0.98 - f["easing_r2"], 0.0, 0.13)           # r2>=0.98 .. r2<=0.85
    # dt coefficient of variation ~0 => metronomic => bot.
    s_timing = _ramp(f["dt_cv"], 0.05, 0.30)
    # number of velocity peaks: 1 => single eased move; >=3 => human corrections.
    s_submov = _ramp(f["n_velocity_peaks"], 1.0, 3.0)
    # turning jitter: ~0 => perfectly smooth => bot.
    s_tremor = _ramp(f["mean_abs_turn_rad"], 0.02, 0.20)

    subscores = {
        "straightness": round(s_straight, 4),
        "easing": round(s_easing, 4),
        "timing": round(s_timing, 4),
        "submovements": round(s_submov, 4),
        "tremor": round(s_tremor, 4),
    }

    total_w = sum(WEIGHTS.values())
    combined = sum(subscores[k] * WEIGHTS[k] for k in WEIGHTS) / total_w

    # A near-perfect easing fit is, on its own, very strong evidence. Cap the
    # score when the path is both straight AND fits a tween almost exactly.
    if f["easing_r2"] >= 0.985 and f["directness"] >= 0.99:
        combined = min(combined, 0.15)

    combined = round(float(combined), 4)
    verdict = "human" if combined >= 0.5 else ("suspicious" if combined >= 0.3 else "bot")

    return {
        "score": combined,
        "verdict": verdict,
        "reason": _explain(verdict, subscores, f),
        "subscores": subscores,
        "features": f,
    }


def _explain(verdict: str, sub: dict[str, float], f: dict[str, Any]) -> str:
    if verdict == "human":
        return "movement shows curvature, irregular timing and corrective sub-movements"
    weak = sorted(sub, key=lambda k: sub[k])[:2]
    hints = {
        "straightness": "path is nearly a straight line",
        "easing": f"timing matches the '{f['easing_name']}' tween (R^2={f['easing_r2']})",
        "timing": "event intervals are unusually regular",
        "submovements": "single smooth velocity profile (no corrections)",
        "tremor": "no physiological jitter",
    }
    return "; ".join(hints[k] for k in weak)
