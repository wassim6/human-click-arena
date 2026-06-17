"""Flask app: serves the demo page and exposes POST /score.

Run:
    cd server && pip install -r requirements.txt && python app.py
    open http://127.0.0.1:5000

Port is configurable:  PORT=5050 python app.py
(macOS note: port 5000 is used by the AirPlay Receiver; if 5000 misbehaves,
disable it in System Settings > General > AirDrop & Handoff, or use PORT=5050.)
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
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    print("\n  human-click-arena demo is running — open one of these:")
    print(f"      http://127.0.0.1:{port}")
    print(f"      http://localhost:{port}")
    print("  (press Ctrl+C to stop)\n")
    app.run(host=host, port=port, debug=True)
