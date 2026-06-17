# human-click-arena

**An open challenge: can you make a click that our detector thinks is human — when it isn't?**

📊 **[Live dashboard](https://wassim6.github.io/human-click-arena/)** — every engine vs every defense layer, the rate-limit timeline, and the hall of fame. Built from real runs by `tools/build_dashboard.py`.

This project is a small, transparent **behavioral bot-detection arena**. It scores a stream of
pointer events (mouse movements + click) and returns a probability that the interaction came from a
**real human hand** rather than from an automation tool.

It is built for one purpose: **to be broken, publicly, so it gets better.** Bring your
`selenium`, `puppeteer`, `playwright`, `selenium-base`, `pyautogui`, `ghost-cursor`, recorded human
traces — whatever you have. If you slip past the scorer, [submit your bypass](bypasses/README.md) and
it becomes a regression test + a new training example.

---

## Why this exists (and what it is *not*)

A lot of people assume you can write JavaScript that verifies "this click physically came from a
mouse, not from a script." **You cannot.** Everything JavaScript sees is mediated by the browser, and
OS-level input injectors (like `pyautogui`) produce events that are *indistinguishable from a real
hand* at the event level — `isTrusted` is `true`, no automation framework is attached, the browser is
pristine.

So this project does **not** try to detect the *framework*. It attacks the one surface where a
generated input still betrays itself: **the shape of the movement.** A human trajectory has ballistic
sub-movements, physiological tremor, irregular timing, overshoot-and-correct near the target, and
curvature that doesn't fit a clean parametric curve. A naive `pyautogui` / `selenium-base` move is a
straight line in space whose timing follows a known easing function. That gap is what we score.

### Honest ceiling

- This **reliably flags `pyautogui`/`selenium-base` out-of-the-box.** That alone beats the default
  behavior of most automation stacks.
- A determined attacker who **replays real recorded human traces** (or uses good humanization libs)
  can defeat the behavioral layer alone. That's expected — and it's the whole point of the arena.
- In production you would combine this with **server-side signals you can't spoof in JS** (TLS/JA3/JA4
  fingerprint, HTTP/2 fingerprint, IP reputation). This repo deliberately ships only the behavioral
  layer, because that's the interesting, learnable part.

The score is a **risk score, not a binary gate.** Treat it that way.

---

## How it works (short version)

```
 browser                          server
┌───────────────────┐            ┌──────────────────────────────┐
│ collector.js      │  trace ──▶ │ features.py  → numeric signals│
│ records pointer   │   (JSON)   │ easing.py    → PyAutoGUI match│
│ move/down/up      │            │ scorer.py    → score 0..1     │
└───────────────────┘            └──────────────────────────────┘
```

The scorer looks at, among others:

| Signal | Human | Bot (naive) |
|---|---|---|
| Movement before click | yes | often **none** (instant red flag) |
| Path straightness (displacement / path length) | curved (~0.6–0.95) | ~1.0 (straight line) |
| Inter-event timing regularity (CV of `dt`) | irregular | very regular |
| Velocity peaks (sub-movements) | several | one smooth peak |
| Tremor / high-frequency jitter | present | ~0 |
| Easing-function fit (R²) | low | **near 1.0** (matches a known tween) |
| Pixel coordinates | sub-pixel on HiDPI/trackpad | exact integers (OS-injected) |
| Click dwell (`down`→`up`) | varies | near-constant |

Only the **final gesture** is scored: the run of motion ending in the click, cut at the last long idle
gap. A real collector may buffer minutes of unrelated wandering before an automated click is appended,
and scoring the whole buffer lets that human motion mask the bot — see the regression fixture
`tests/fixtures/pyautogui_real_naive.json` (a real captured pyautogui click that this isolates and flags).

Full write-up: [docs/how-it-works.md](docs/how-it-works.md).

---

## What the arena can and can't catch

`/score` returns one **decision** — `allow` / `challenge` / `deny` — from three layers. Be honest about
what each one can do:

| Attack | Behavioral + sub-pixel | Proof-of-work | Rate / reputation | Net result |
|---|---|---|---|---|
| `dispatchEvent()` / pure JS click | caught (`isTrusted`-free, no motion) | — | — | **deny** |
| Selenium / Puppeteer (framework attached) | caught (framework + shape) | costs CPU | — | **deny** |
| naive pyautogui (straight + easing) | **caught** (straightness, easing, integers) | costs CPU | — | **deny** |
| bezier pyautogui (curved, regular timing) | **caught** (timing, integers, no tremor) | costs CPU | — | **deny** |
| humanized pyautogui on **HiDPI** | **caught** (integer pixels on dpr > 1) | costs CPU | — | **deny** |
| humanized pyautogui on **1x** | **passes as human** (the wall) | costs CPU per try | **caught at volume** | allow once, **deny at scale** |
| replay of a real recorded human trace | **passes** (it _is_ human motion) | costs CPU per try | **caught at volume** | allow once, **deny at scale** |

The takeaway: **no single-request signal — client or server — separates a humanized real-browser click
from a human.** Past that wall you stop trying to tell bot from human and instead change the economics:
proof-of-work makes each attempt cost CPU, and rate/reputation catches the same client repeating it.
That is exactly why real systems (Cloudflare, etc.) lean on reputation, proof-of-work, and cross-site
telemetry rather than mouse curves alone. The reference bypass that defines this wall is frozen in
[`bypasses/pyautogui-humanized-1x.md`](bypasses/pyautogui-humanized-1x.md).

What this repo deliberately does **not** ship (a real deployment would): TLS/JA3-JA4 and HTTP/2
fingerprints, IP/ASN reputation feeds, and a shared (Redis-backed) rate store. Note even those wouldn't
flag a humanized click from a genuine browser on a clean residential IP — only its *volume over time*.

---

## Quick start

```bash
# 1. Python scorer + demo server
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
# then open http://127.0.0.1:5000  → click the target; the page solves a proof-of-work
# and shows the layered decision (behavioral + proof-of-work + rate/reputation)

# /score requires a proof-of-work by default. To poke it with raw behavioral only:
#   REQUIRE_POW=0 python app.py
# The stdin CLI below scores behavior directly and never needs one.

# 2. Generate a fake PyAutoGUI trace and score it from the CLI
python ../tools/generate_pyautogui_trace.py --tween easeInOutQuad | python score_cli.py

# 3. Run the tests (human vs bot separation)
pip install pytest
pytest -q
```

No GPU, no GUI, no external services required. The PyAutoGUI trace generator **replicates** PyAutoGUI's
tweening math, so the test suite runs in CI without a desktop.

### Troubleshooting `ERR_CONNECTION_REFUSED`

`Connection refused` means **nothing is listening** on the port — the server isn't running. It is not
a code problem.

- Make sure `python app.py` is actually running in a terminal and stays running (you should see the
  "demo is running" banner). Open the page in a *second* terminal/tab.
- Prefer **`http://127.0.0.1:5000`**. If `localhost` is refused but `127.0.0.1` works, your `localhost`
  is resolving to IPv6 (`::1`) while the dev server listens on IPv4 — just use `127.0.0.1`.
- **macOS:** port 5000 is taken by the AirPlay Receiver. If you get odd behavior on 5000, run on
  another port: `PORT=5050 python app.py` then open `http://127.0.0.1:5050`.
- Don't open the `index.html` file directly (`file://…`) — it must be served by Flask so that `/score`
  is reachable.

---

## Repository layout

```
human-click-arena/
├── client/
│   ├── collector.js        # captures pointer events into a trace
│   ├── sha256.js           # compact SHA-256 (for the proof-of-work solver)
│   ├── pow.js              # proof-of-work: fetch challenge, grind a nonce
│   └── index.html          # interactive demo + live layered decision
├── server/
│   ├── app.py              # Flask: serves the demo, POST /score, GET /pow/challenge
│   ├── features.py         # trajectory feature extraction
│   ├── easing.py           # PyAutoGUI tween functions + fit/matching
│   ├── scorer.py           # behavioral + sub-pixel → score 0..1 + breakdown
│   ├── pow.py              # stateless proof-of-work challenge / verify
│   ├── puzzle.py           # signed visual slide-to-fit challenge / verify
│   ├── reputation.py       # two-tier rate limit + temporary ban
│   ├── score_cli.py        # score a trace from stdin (for piping)
│   └── requirements.txt
├── tools/
│   ├── generate_pyautogui_trace.py   # synthetic PyAutoGUI-style trace (offline, CI)
│   └── generate_human_trace.py       # synthetic human-like trace (offline, CI)
├── attacks/
│   ├── pyautogui_attack.py # REAL pyautogui: finds click.png on screen, moves + clicks
│   ├── click.png           # template image of the demo button
│   └── requirements.txt
├── tests/
│   ├── test_scorer.py
│   └── fixtures/           # sample human + bot traces (JSON)
├── bypasses/
│   ├── README.md           # how to submit a bypass
│   └── TEMPLATE.md
└── docs/
    └── how-it-works.md
```

> Two PyAutoGUI files, on purpose: `tools/generate_pyautogui_trace.py` fabricates a JSON trace
> *offline* (so tests run without a desktop), while `attacks/pyautogui_attack.py` drives the **real OS
> cursor** against the live demo using image recognition on `click.png`. See [attacks/](attacks/README.md).

## Trace format

A trace is JSON: a list of pointer samples plus the click.

```json
{
  "events": [
    { "type": "move", "x": 412.0, "y": 233.5, "t": 0.0 },
    { "type": "move", "x": 415.2, "y": 231.1, "t": 11.3 },
    { "type": "down", "x": 600.0, "y": 410.0, "t": 842.7 },
    { "type": "up",   "x": 600.0, "y": 410.0, "t": 921.4 }
  ],
  "target": { "x": 600, "y": 410, "r": 24 }
}
```

`t` is milliseconds from the first event. `x`/`y` are CSS pixels. See `tests/fixtures/`.

---

## Play the game

1. Beat the scorer with any tool you like.
2. Capture the trace you sent (the demo page lets you copy it; or POST your own to `/score`).
3. Open a PR adding it under `bypasses/` using [the template](bypasses/TEMPLATE.md).
4. We add it as a regression fixture and tighten the scorer. Your name goes in the hall of fame.

The goal is **not** an unbeatable detector — that doesn't exist client-side. The goal is to make each
bypass cost more than the last.

## License

MIT — see [LICENSE](LICENSE).
