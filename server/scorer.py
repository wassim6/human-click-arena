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

from features import extract, final_gesture


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
    "subpixel": 0.7,       # OS injectors land on integer pixels (modest weight)
}


def score(trace: dict[str, Any]) -> dict[str, Any]:
    # Only the gesture that ends in the click matters. A collector may have
    # buffered minutes of unrelated human wandering before an automated click
    # was appended; scoring the whole buffer lets that motion mask the bot.
    all_events = trace.get("events", [])
    meta = trace.get("meta") or {}
    dpr = float(meta.get("dpr", 1) or 1)
    # Fingerprint tell (not behavioral): the browser's own automation flag.
    # `true` => WebDriver-controlled; `false`/None => human OR stealthed bot.
    wd = meta.get("webdriver")
    webdriver_flag = wd is True
    # Second fingerprint tell: a Chrome DevTools Protocol client with the Runtime
    # domain enabled (Puppeteer/Playwright/chromedriver). Same nature as
    # webdriver: zero false positives, but trivially patchable and blind to OS
    # injectors. Only `true` is informative.
    cdp = meta.get("cdp")
    cdp_flag = cdp is True
    # Third fingerprint tell: chromedriver/selenium injected globals ($cdc_…,
    # __webdriver_*). Non-empty => a non-stealth Selenium. UC mode erases them.
    driver_props = meta.get("driverProps") or []
    driver_props_flag = isinstance(driver_props, list) and len(driver_props) > 0
    gesture = final_gesture(all_events)
    f = extract({"events": gesture, "target": trace.get("target")})
    f["n_total_events"] = len(all_events)
    f["n_gesture_events"] = len(gesture)
    f["device_pixel_ratio"] = dpr
    f["navigator_webdriver"] = (bool(wd) if wd is not None else None)
    f["cdp_runtime"] = (bool(cdp) if cdp is not None else None)
    f["driver_props"] = list(driver_props) if driver_props_flag else []
    fingerprint = {"navigator_webdriver": f["navigator_webdriver"],
                   "cdp_runtime": f["cdp_runtime"],
                   "driver_props": f["driver_props"]}

    # Hard gate: a click with no preceding movement is the loudest bot signal.
    if not f["has_movement"]:
        reason = "no pointer movement before click"
        flags = []
        if webdriver_flag:
            flags.append("navigator.webdriver is true")
        if cdp_flag:
            flags.append("CDP Runtime attached")
        if driver_props_flag:
            flags.append("chromedriver/selenium globals present")
        if flags:
            reason = " + ".join(flags) + " (automation); " + reason
        return {
            "score": 0.0,
            "verdict": "bot",
            "reason": reason,
            "subscores": {},
            "features": f,
            "fingerprint": fingerprint,
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
    # sub-pixel coordinates => human; all-integer => OS injector (pyautogui).
    s_subpixel = _ramp(1.0 - f["int_coord_ratio"], 0.02, 0.30)

    subscores = {
        "straightness": round(s_straight, 4),
        "easing": round(s_easing, 4),
        "timing": round(s_timing, 4),
        "submovements": round(s_submov, 4),
        "tremor": round(s_tremor, 4),
        "subpixel": round(s_subpixel, 4),
    }

    total_w = sum(WEIGHTS.values())
    combined = sum(subscores[k] * WEIGHTS[k] for k in WEIGHTS) / total_w

    # A near-perfect easing fit is, on its own, very strong evidence. Cap the
    # score when the path is both straight AND fits a tween almost exactly.
    if f["easing_r2"] >= 0.985 and f["directness"] >= 0.99:
        combined = min(combined, 0.15)

    # Decisive HiDPI tell: on a display with devicePixelRatio > 1, real pointer
    # events report sub-pixel coordinates. An all-integer gesture there is an OS
    # injector (pyautogui/xdotool move to whole pixels and cannot do sub-pixel),
    # no matter how human the *shape* of the motion is. This is what catches an
    # otherwise-convincing "humanized" pyautogui run. Not applied on 1x displays,
    # where humans also land on integers.
    hidpi_integer = dpr > 1.0 and f["int_coord_ratio"] >= 0.98
    if hidpi_integer:
        combined = min(combined, 0.22)

    combined = round(float(combined), 4)
    verdict = "human" if combined >= 0.5 else ("suspicious" if combined >= 0.3 else "bot")

    reason = _explain(verdict, subscores, f)
    if hidpi_integer:
        reason = (f"every sample is an integer pixel on a HiDPI display (dpr={dpr:g}) — "
                  f"OS injector, not a real pointer; " + reason)

    # Keep the behavioral verdict for reference, then apply the fingerprint layer.
    f["behavioral_score"] = combined

    # Fingerprint gate: navigator.webdriver === true can only happen under
    # automation, so it's a zero-false-positive bot tell. It's *trivial* to
    # defeat (any stealth plugin resets it to false), so it only ever catches
    # naive automation — but that catch is free. We still expose the behavioral
    # breakdown so the arena keeps teaching the harder, unspoofable layer.
    if webdriver_flag or cdp_flag or driver_props_flag:
        combined = 0.0
        verdict = "bot"
        tells = []
        if webdriver_flag:
            tells.append("navigator.webdriver is true")
        if cdp_flag:
            tells.append("a CDP Runtime client is attached (Puppeteer/Playwright/chromedriver)")
        if driver_props_flag:
            tells.append("chromedriver/selenium globals present (" + ", ".join(driver_props[:3]) + ")")
        reason = (" and ".join(tells) + " — the browser is under automation control "
                  "(fingerprint tells, all patchable). Behavioral read: " + reason)

    return {
        "score": combined,
        "verdict": verdict,
        "reason": reason,
        "subscores": subscores,
        "features": f,
        "fingerprint": fingerprint,
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
        "subpixel": "every sample lands on an integer pixel (OS-injected)",
    }
    return "; ".join(hints[k] for k in weak)
