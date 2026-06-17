"""Flask app: serves the demo page and exposes POST /score.

Run:
    cd server && pip install -r requirements.txt && python app.py
    open http://localhost:5000
"""

from __future__ import annotations

import os

from flask import Flask, jsonify, request, send_from_directory

from scorer import score

CLIENT_DIR = os.path.join(os.path.dirname(__file__), "..", "client")

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(CLIENT_DIR, "index.html")


@app.route("/collector.js")
def collector():
    return send_from_directory(CLIENT_DIR, "collector.js")


@app.route("/score", methods=["POST"])
def score_endpoint():
    trace = request.get_json(force=True, silent=True)
    if not isinstance(trace, dict) or "events" not in trace:
        return jsonify({"error": "expected JSON {events: [...], target: {...}}"}), 400
    return jsonify(score(trace))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
