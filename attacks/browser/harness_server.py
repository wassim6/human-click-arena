"""Local harness server for the browser-automation *click* attacks.

It reuses the project's real scorer (server/scorer.py) and the real
client/collector.js, but serves a *controlled* page (fixed target, no random
reshuffling) so an automation driver can move + click deterministically and
read back the exact trace the collector captured.

This server deliberately exposes ONLY the raw behavioral scorer (no proof-of-work
/ rate-limit / puzzle), so the click drivers measure the pure behavioral score in
isolation. The rate-limit + slider-puzzle defenses are exercised against the real
server (server/app.py) by ratelimit_attack.py and puzzle_attack.py.

Run standalone:
    python harness_server.py            # http://127.0.0.1:5001
Routes:
    GET  /            -> harness.html
    GET  /collector.js-> the project's real collector
    POST /score       -> server/scorer.score(trace)
"""
from __future__ import annotations

import os
import sys

from flask import Flask, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))

from scorer import score  # noqa: E402

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(HERE, "harness.html")


@app.route("/collector.js")
def collector():
    return send_from_directory(os.path.join(ROOT, "client"), "collector.js")


@app.route("/score", methods=["POST"])
def score_endpoint():
    trace = request.get_json(force=True, silent=True)
    if not isinstance(trace, dict) or "events" not in trace:
        return jsonify({"error": "expected {events, target}"}), 400
    return jsonify(score(trace))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="127.0.0.1", port=port, debug=False)
