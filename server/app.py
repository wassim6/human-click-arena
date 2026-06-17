"""Flask app: serves the demo and layers three defenses behind one decision.

    POST /score            behavioral + sub-pixel + proof-of-work + rate/reputation
    GET  /pow/challenge    issue a proof-of-work challenge

Run:
    cd server && pip install -r requirements.txt && python app.py
    open http://127.0.0.1:5000

Port is configurable:  PORT=5050 python app.py
(macOS note: port 5000 is used by the AirPlay Receiver; if 5000 misbehaves,
disable it in System Settings > General > AirDrop & Handoff, or use PORT=5050.)

Why three layers? The behavioral + sub-pixel layers can flag a generated click,
but NOT a humanized real-browser click on a 1x display -- that is genuinely
indistinguishable from a human on a single request (client OR server). So the
last two layers stop relying on telling bot from human:
  - proof-of-work makes every attempt cost CPU (volume gets expensive),
  - rate/reputation catches the same client doing it many times.
"""

from __future__ import annotations

import os

from flask import Flask, jsonify, request, send_from_directory

import pow as powmod
from reputation import Reputation
from scorer import score

CLIENT_DIR = os.path.join(os.path.dirname(__file__), "..", "client")
REQUIRE_POW = os.environ.get("REQUIRE_POW", "1") not in ("0", "false", "False")

app = Flask(__name__, static_folder=None)
reputation = Reputation()


@app.route("/")
def index():
    return send_from_directory(CLIENT_DIR, "index.html")


@app.route("/<path:name>.js")
def js(name):
    return send_from_directory(CLIENT_DIR, name + ".js")


@app.route("/pow/challenge")
def pow_challenge():
    bits = request.args.get("bits", type=int)
    return jsonify(powmod.make_challenge(bits))


def _decide(behavioral, pow_ok, pow_provided, rep):
    """Combine the layers into allow / challenge / deny."""
    if rep["state"] == "blocked":
        return "deny", f"rate limit: {rep['attempts_in_window']} attempts in {int(rep['window_s'])}s from this client"
    if REQUIRE_POW and not pow_ok:
        return "deny", "proof-of-work missing or invalid"
    if behavioral["verdict"] == "bot":
        return "deny", "behavioral: " + behavioral["reason"]
    if behavioral["verdict"] == "suspicious" or rep["state"] == "throttled":
        return "challenge", "borderline — escalate (harder proof-of-work or a second factor)"
    return "allow", "passed behavioral + proof-of-work + rate check"


@app.route("/score", methods=["POST"])
def score_endpoint():
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict) or "events" not in body:
        return jsonify({"error": "expected JSON {events: [...], target: {...}, meta?, pow?}"}), 400

    behavioral = score(body)

    solution = body.get("pow")
    if solution is not None:
        pow_ok, pow_detail = powmod.verify(solution)
    else:
        pow_ok, pow_detail = (not REQUIRE_POW), ("not provided" if REQUIRE_POW else "skipped")

    meta = body.get("meta") or {}
    key = Reputation.key(request.remote_addr or "?", str(meta.get("ua", "")), meta.get("dpr", 1))
    rep = reputation.assess(key)

    decision, reason = _decide(behavioral, pow_ok, solution is not None, rep)

    return jsonify({
        "decision": decision,
        "reason": reason,
        "behavioral": behavioral,
        "pow": {"required": REQUIRE_POW, "provided": solution is not None,
                "ok": pow_ok, "detail": pow_detail},
        "reputation": rep,
    })


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    print("\n  human-click-arena demo is running — open one of these:")
    print(f"      http://127.0.0.1:{port}")
    print(f"      http://localhost:{port}")
    print("  (press Ctrl+C to stop)\n")
    app.run(host=host, port=port, debug=True)
