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


def test_clear_separation_margin():
    """The worst human should still beat the best bot by a comfortable margin."""
    humans = [score(human.generate((90, 410), (600, 250), seed=s))["score"] for s in range(10)]
    bots = []
    for tween in ["linear", "easeInOutQuad", "easeInOutCubic", "easeInOutSine"]:
        bots.append(score(bot.generate((80, 400), (600, 250), 0.6, tween))["score"])
    assert min(humans) > max(bots), (min(humans), max(bots))
