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
# Difficulty (leading zero bits) of the escalated challenge shown on a
# "challenge" decision. Higher = more CPU for the client to clear it.
ESCALATED_BITS = int(os.environ.get("ESCALATED_BITS", "18"))

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


@app.route("/reset", methods=["POST"])
def reset_endpoint():
    """Demo helper: clear the rate-limit history and proof-of-work state so you
    can keep testing after hitting the limit. Not something a real server exposes."""
    reputation.reset()
    powmod.reset()
    return jsonify({
        "ok": True,
        "reputation": {
            "state": "ok", "key": "(reset)",
            "short": {"count": 0, "limit": reputation.short_limit, "window_s": reputation.short_window},
            "long": {"count": 0, "limit": reputation.long_limit, "window_s": reputation.long_window},
            "ban_seconds": reputation.ban_seconds,
        },
    })


def _decide(behavioral, pow_ok, pow_provided, rep):
    """Combine the layers into allow / challenge / deny."""
    if rep["state"] == "blocked":
        lo = rep["long"]
        ra = rep.get("retry_after_s")
        retry = f"; retry in {max(1, round(ra / 60))} min" if ra else ""
        return "deny", (f"rate limit: more than {lo['limit']} attempts in "
                        f"{round(lo['window_s'] / 60)} min — blocked for "
                        f"{round(rep['ban_seconds'] / 60)} min{retry}")
    if REQUIRE_POW and not pow_ok:
        return "deny", "proof-of-work missing or invalid"
    if behavioral["verdict"] == "bot":
        return "deny", "behavioral: " + behavioral["reason"]
    if rep["state"] == "throttled":
        sh = rep["short"]
        return "challenge", (f"rate limit: more than {sh['limit']} attempts in "
                             f"{round(sh['window_s'] / 60)} min — solve a harder proof-of-work")
    if behavioral["verdict"] == "suspicious":
        return "challenge", "borderline behavioral score — solve a harder proof-of-work"
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
        "escalate_bits": ESCALATED_BITS,   # difficulty to clear a "challenge"
    })


@app.route("/challenge/verify", methods=["POST"])
def challenge_verify():
    """Resolve a 'challenge' decision: the client proves extra work by solving a
    harder proof-of-work. Pass only if the solution is valid AND its difficulty
    meets the escalated bar. (A real system might use a different second factor.)"""
    body = request.get_json(force=True, silent=True) or {}
    solution = body.get("pow")
    ok, detail = powmod.verify(solution) if solution else (False, "no solution")
    if ok and int(solution.get("difficulty", 0)) >= ESCALATED_BITS:
        return jsonify({"ok": True, "decision": "allow",
                        "reason": f"passed escalated proof-of-work ({ESCALATED_BITS} bits)"})
    why = detail if not ok else f"need at least {ESCALATED_BITS} bits of work"
    return jsonify({"ok": False, "decision": "deny", "reason": why})


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    print("\n  human-click-arena demo is running — open one of these:")
    print(f"      http://127.0.0.1:{port}")
    print(f"      http://localhost:{port}")
    print("  (press Ctrl+C to stop)\n")
    app.run(host=host, port=port, debug=True)
