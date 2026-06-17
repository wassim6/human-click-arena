"""Separation tests: human-like traces should score high, generated ones low.

Run from the repo root:  pytest -q
"""

import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "server"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import generate_human_trace as human          # noqa: E402
import generate_pyautogui_trace as bot         # noqa: E402
from scorer import score                       # noqa: E402


def test_pyautogui_traces_score_as_bot():
    for tween in ["linear", "easeInOutQuad", "easeInOutCubic", "easeInOutSine"]:
        trace = bot.generate((80, 400), (600, 250), 0.6, tween)
        result = score(trace)
        assert result["verdict"] == "bot", (tween, result["score"], result["subscores"])
        assert result["score"] < 0.3, (tween, result["score"])


def test_human_like_traces_score_as_human():
    for seed in range(10):
        trace = human.generate((90, 410), (600, 250), seed=seed)
        result = score(trace)
        assert result["score"] >= 0.5, (seed, result["score"], result["subscores"])


def test_click_with_no_movement_is_bot():
    trace = {
        "events": [
            {"type": "down", "x": 600, "y": 250, "t": 0.0},
            {"type": "up", "x": 600, "y": 250, "t": 60.0},
        ],
        "target": {"x": 600, "y": 250, "r": 28},
    }
    result = score(trace)
    assert result["score"] == 0.0
    assert result["verdict"] == "bot"
    assert "no pointer movement" in result["reason"]


def test_real_pyautogui_naive_trace_is_bot():
    """Regression: a real browser-captured pyautogui naive click.

    This trace originally scored 100/human because the collector had buffered
    ~3 minutes of unrelated human wandering before the bot's straight dash was
    appended. The scorer now isolates the final gesture (here: 14 events) and
    must flag it. See bypasses/ — this is the arena's first regression fixture.
    """
    import json
    path = os.path.join(HERE, "fixtures", "pyautogui_real_naive.json")
    with open(path) as fh:
        trace = json.load(fh)
    result = score(trace)
    assert result["verdict"] == "bot", (result["score"], result["subscores"])
    assert result["score"] < 0.3, result["score"]
    assert result["features"]["n_gesture_events"] < result["features"]["n_total_events"]


def test_real_pyautogui_humanized_hidpi_is_flagged():
    """A convincing 'humanized' pyautogui run (curved, overshoot, irregular
    timing) still moves to whole pixels. On a HiDPI display real pointers report
    sub-pixel coordinates, so an all-integer gesture is caught regardless of how
    human its shape is."""
    import json
    path = os.path.join(HERE, "fixtures", "pyautogui_humanized.json")
    with open(path) as fh:
        trace = json.load(fh)
    result = score(trace)
    assert result["score"] < 0.5, (result["score"], result["subscores"])
    assert result["features"]["int_coord_ratio"] >= 0.98
    assert result["features"]["device_pixel_ratio"] > 1


def test_integer_pixels_not_penalized_on_1x_display():
    """Honest tradeoff: on a standard 1x display humans also land on integers,
    so the integer-pixel signal must NOT, by itself, flip a human-shaped trace.
    (This is exactly why the HiDPI cap is conditional on dpr > 1.)"""
    import json
    path = os.path.join(HERE, "fixtures", "pyautogui_humanized.json")
    with open(path) as fh:
        trace = json.load(fh)
    trace["meta"]["dpr"] = 1
    result = score(trace)
    assert result["score"] > 0.5, result["score"]


def test_navigator_webdriver_true_is_caught_but_keeps_behavioral_read():
    """The fingerprint layer: navigator.webdriver === true can only happen under
    automation, so it flips even a perfectly human-shaped trace to bot — while
    still exposing the behavioral score for reference."""
    trace = human.generate((90, 410), (600, 250), seed=0)
    trace.setdefault("meta", {})["webdriver"] = True
    result = score(trace)
    assert result["verdict"] == "bot"
    assert result["score"] == 0.0
    assert result["fingerprint"]["navigator_webdriver"] is True
    assert result["features"]["behavioral_score"] >= 0.5   # behavioral read kept
    assert "navigator.webdriver is true" in result["reason"]


def test_cdp_runtime_flag_is_caught():
    """The CDP fingerprint gate: meta.cdp === true (a DevTools-Protocol Runtime
    client) flips even a human-shaped trace to bot, like the webdriver flag.
    NOTE: current Puppeteer/Playwright defer Runtime.enable and report false here
    (measured) — this only catches DevTools-open / old clients."""
    trace = human.generate((90, 410), (600, 250), seed=0)
    trace.setdefault("meta", {})["cdp"] = True
    result = score(trace)
    assert result["verdict"] == "bot"
    assert result["score"] == 0.0
    assert result["fingerprint"]["cdp_runtime"] is True
    assert "CDP" in result["reason"]


def test_driver_props_present_is_caught():
    """meta.driverProps non-empty (chromedriver/selenium injected globals) flips a
    human-shaped trace to bot — catches non-UC Selenium. Puppeteer/Playwright and
    UC mode report an empty list, so they are unaffected."""
    trace = human.generate((90, 410), (600, 250), seed=0)
    trace.setdefault("meta", {})["driverProps"] = ["$cdc_asdjflasutopfhvcZLmcfl_"]
    result = score(trace)
    assert result["verdict"] == "bot"
    assert result["score"] == 0.0
    assert result["fingerprint"]["driver_props"] == ["$cdc_asdjflasutopfhvcZLmcfl_"]
    assert "chromedriver/selenium" in result["reason"]


def test_empty_driver_props_does_not_penalize():
    """No false positives: an empty driverProps list (Puppeteer/Playwright/UC)
    must not lower a human-shaped trace."""
    trace = human.generate((90, 410), (600, 250), seed=2)
    trace.setdefault("meta", {})["driverProps"] = []
    assert score(trace)["score"] >= 0.5


def test_env_decisive_headless_tell_is_caught():
    """A decisive environment anomaly (HeadlessChrome UA or permissions mismatch)
    hard-gates to bot — catches *non-stealth* headless. Stealth plugins spoof
    these surfaces (measured), so the stealthed engines report no anomalies."""
    trace = human.generate((90, 410), (600, 250), seed=0)
    trace.setdefault("meta", {})["env"] = {"anomalies": ["headless_ua"], "details": {}}
    result = score(trace)
    assert result["verdict"] == "bot"
    assert result["score"] == 0.0
    assert "headless" in result["reason"]


def test_env_soft_anomalies_cap_to_suspicious_not_hard_bot():
    """Several non-decisive anomalies are a SOFT signal (FP risk): they pull the
    score down to suspicious, not a hard 0 — a real GPU-less/privacy browser
    might trip a couple."""
    trace = human.generate((90, 410), (600, 250), seed=0)
    trace.setdefault("meta", {})["env"] = {
        "anomalies": ["no_plugins", "no_languages", "missing_window_chrome"], "details": {}}
    result = score(trace)
    assert result["verdict"] != "human"
    assert 0.0 < result["score"] <= 0.3


def test_env_no_anomalies_does_not_penalize():
    trace = human.generate((90, 410), (600, 250), seed=1)
    trace.setdefault("meta", {})["env"] = {"anomalies": [], "details": {}}
    assert score(trace)["score"] >= 0.5


def test_navigator_webdriver_false_or_absent_does_not_penalize():
    """Zero false positives: a real human AND a stealthed bot both report
    webdriver=false, so the flag must never lower a human-shaped trace. Only
    `true` is informative."""
    base = human.generate((90, 410), (600, 250), seed=1)
    assert score(base)["score"] >= 0.5                     # absent -> unaffected
    base.setdefault("meta", {})["webdriver"] = False
    result = score(base)
    assert result["score"] >= 0.5                          # false -> unaffected
    assert result["fingerprint"]["navigator_webdriver"] is False


def test_clear_separation_margin():
    """The worst human should still beat the best bot by a comfortable margin."""
    humans = [score(human.generate((90, 410), (600, 250), seed=s))["score"] for s in range(10)]
    bots = []
    for tween in ["linear", "easeInOutQuad", "easeInOutCubic", "easeInOutSine"]:
        bots.append(score(bot.generate((80, 400), (600, 250), 0.6, tween))["score"])
    assert min(humans) > max(bots), (min(humans), max(bots))
