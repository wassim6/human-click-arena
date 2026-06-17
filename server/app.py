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
import puzzle as puzzlemod
import request_fingerprint as rfp
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
    alg = request.args.get("alg")            # "argon2id" (default) or "sha256"
    return jsonify(powmod.make_challenge(difficulty=bits, alg=alg))


@app.route("/pow/echo")
def pow_echo():
    """Return the server's digest for given params so the browser can confirm its
    Argon2 implementation matches before relying on it (else it uses SHA-256).
    Harmless: the hash function is public."""
    salt = request.args.get("salt", "")
    nonce = request.args.get("nonce", "")
    alg = request.args.get("alg", "argon2id")
    m = request.args.get("m", type=int, default=powmod.ARGON_M)
    t = request.args.get("t", type=int, default=powmod.ARGON_T)
    p = request.args.get("p", type=int, default=powmod.ARGON_P)
    try:
        digest = powmod._digest(alg, salt, nonce, m, t, p)
    except Exception as exc:                 # argon2 unavailable / bad params
        return jsonify({"error": str(exc)}), 400
    return jsonify({"hex": digest.hex()})


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


def _decide(behavioral, pow_ok, pow_provided, rep, request_fp):
    """Combine the layers into allow / challenge / deny."""
    if rep["state"] == "blocked":
        lo = rep["long"]
        ra = rep.get("retry_after_s")
        retry = f"; retry in {max(1, round(ra / 60))} min" if ra else ""
        return "deny", (f"rate limit: more than {lo['limit']} attempts in "
                        f"{round(lo['window_s'] / 60)} min — blocked for "
                        f"{round(rep['ban_seconds'] / 60)} min{retry}")
    # A real human always reaches /score through the page's browser fetch. A
    # non-browser HTTP client (curl/requests/Go) hitting it directly is the
    # "skip the browser, POST a forged trace" attack — deny it outright.
    # (Header values are spoofable, so this only stops the lazy direct-API bot.)
    if request_fp.get("suspicious"):
        return "deny", "request fingerprint: " + "; ".join(request_fp.get("reasons", [])
                                                           or ["non-browser client"])
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

    request_fp = rfp.analyze(request)

    decision, reason = _decide(behavioral, pow_ok, solution is not None, rep, request_fp)

    return jsonify({
        "decision": decision,
        "reason": reason,
        "behavioral": behavioral,
        "pow": {"required": REQUIRE_POW, "provided": solution is not None,
                "ok": pow_ok, "detail": pow_detail},
        "reputation": rep,
        "request_fp": request_fp,
        "escalate_bits": ESCALATED_BITS,   # difficulty to clear a "challenge"
    })


@app.route("/challenge/puzzle")
def challenge_puzzle():
    """Issue a visual slide-to-fit challenge (gap position is signed)."""
    return jsonify(puzzlemod.make_challenge())


@app.route("/challenge/puzzle/verify", methods=["POST"])
def challenge_puzzle_verify():
    """Resolve a 'challenge' by dragging the piece into the gap."""
    body = request.get_json(force=True, silent=True) or {}
    ok, detail = puzzlemod.verify(body)
    if ok:
        return jsonify({"ok": True, "decision": "allow", "reason": "passed the slide challenge"})
    return jsonify({"ok": False, "decision": "deny", "reason": detail})


@app.route("/challenge/verify", methods=["POST"])
def challenge_verify():
    """Alternative resolution: prove extra work via a harder proof-of-work.
    (Kept for non-visual clients; the demo uses the slide puzzle above.)"""
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
