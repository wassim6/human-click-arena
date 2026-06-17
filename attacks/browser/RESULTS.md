# Results — the bot vs every defense layer

Engines: **selenium, seleniumbase, puppeteer, playwright** (stealth + non-stealth).
The server (`server/app.py`) now layers five defenses; this is how each one fares.

Raw data: [`results.json`](results.json) (click matrix) and
[`defense_results.json`](defense_results.json) (rate-limit + puzzle). Captured
traces under [`captured/`](captured/).

| Layer | What it checks | Where |
|---|---|---|
| fingerprint | `navigator.webdriver` automation flag | `scorer.py` |
| behavioral | trajectory shape (curvature, easing, timing, sub-movements, tremor) | `scorer.py` / `features.py` |
| sub-pixel | integer-only coordinates on a HiDPI display | `scorer.py` |
| proof-of-work | SHA-256 leading-zero-bits per request | `pow.py` |
| rate / reputation | request volume per client over time | `reputation.py` |
| puzzle | slide-to-fit drag (alignment + live drag) | `puzzle.py` |

## 1. Click matrix — dpr = 1

4 engines × 3 movement strategies × {plain, stealth}, behavioral scorer with the
fingerprint layer active.

<!-- table_main -->
| Engine | Strategy | Mode | navigator.webdriver | Verdict | Score | Caught by |
|---|---|---|---|---|---|---|
| selenium | native | plain | true | **bot** | 0.00 | fingerprint |
| selenium | native | stealth | false | **bot** | 0.00 | behavioral |
| seleniumbase | native | plain | true | **bot** | 0.00 | fingerprint |
| seleniumbase | native | stealth | false | **bot** | 0.00 | behavioral |
| puppeteer | native | plain | true | **bot** | 0.00 | fingerprint |
| puppeteer | native | stealth | false | **bot** | 0.00 | behavioral |
| playwright | native | plain | true | **bot** | 0.00 | fingerprint |
| playwright | native | stealth | false | **bot** | 0.00 | behavioral |
| selenium | linear | plain | true | **bot** | 0.00 | fingerprint |
| selenium | linear | stealth | false | **suspicious** | 0.32 | behavioral |
| seleniumbase | linear | plain | true | **bot** | 0.00 | fingerprint |
| seleniumbase | linear | stealth | false | **bot** | 0.15 | behavioral |
| puppeteer | linear | plain | true | **bot** | 0.00 | fingerprint |
| puppeteer | linear | stealth | false | **suspicious** | 0.42 | behavioral |
| playwright | linear | plain | true | **bot** | 0.00 | fingerprint |
| playwright | linear | stealth | false | **suspicious** | 0.42 | behavioral |
| selenium | humanized | plain | true | **bot** | 0.00 | fingerprint |
| selenium | humanized | stealth | false | **human** | 0.59 | — (passes) |
| seleniumbase | humanized | plain | true | **bot** | 0.00 | fingerprint |
| seleniumbase | humanized | stealth | false | **human** | 0.60 | — (passes) |
| puppeteer | humanized | plain | true | **bot** | 0.00 | fingerprint |
| puppeteer | humanized | stealth | false | **human** | 0.72 | — (passes) |
| playwright | humanized | plain | true | **bot** | 0.00 | fingerprint |
| playwright | humanized | stealth | false | **human** | 0.70 | — (passes) |

Read it as a funnel: **plain (non-stealth) automation is caught for free by the
`navigator.webdriver` flag** — every plain row is bot 0.00 regardless of how the
mouse moved. Stealth resets the flag, so those rows fall through to the
behavioral layer, where `native` (no movement) and `linear` (straight + tween)
are still flagged. **Only `stealth + humanized` survives** (human 0.59–0.72).

## 2. Sub-pixel tell — dpr = 2 (humanized + stealth, the survivors)

Re-running just the survivors on a HiDPI display:

<!-- table_dpr2 -->
| Engine (stealth, humanized) | int_coord_ratio | Verdict | Score |
|---|---|---|---|
| selenium | 1.0 | **bot** | 0.22 |
| seleniumbase | 1.0 | **bot** | 0.22 |
| puppeteer | 0.0106 | **human** | 0.81 |
| playwright | 0.0323 | **human** | 0.70 |

Selenium / SeleniumBase drive the W3C Actions API, which only accepts **integer**
coordinates, so on a 2× display every sample is a whole pixel and the HiDPI gate
caps them to bot 0.22 — even with a perfect human-shaped drag. Playwright /
Puppeteer move to fractional pixels and slip through. So on HiDPI the strongest
surviving attacker is **stealth + humanized + Playwright/Puppeteer**.

## 3. Rate limit — the bot trips reputation.py

`ratelimit_attack.py` runs the *good-citizen* request — humanized trace **plus a
solved proof-of-work** — in a loop from one client key. It still gets stopped, by
volume alone:

```
  #  http  decision    short  long   reason
  1   200  allow        1/3    1/10   passed behavioral + proof-of-work + rate check
  2   200  allow        2/3    2/10   passed …
  3   200  allow        3/3    3/10   passed …
  4   200  challenge    4/3    4/10   > 3 attempts in 5 min — solve a harder proof-of-work
  …   200  challenge     …      …     …
 10   200  challenge   10/3   10/10   …
 11   200  deny        11/3   11/10   > 10 attempts in 30 min — blocked for 60 min
```

Three clean requests, then **throttled (challenge)** past the short limit, then
**blocked** past the long limit. A humanized bot is indistinguishable from a
human on *one* click — but the volume from one key is exactly what this catches.

## 4. Puzzle — the bot solves the slider (humanized drag)

`puzzle_attack.py` fetches a real `/challenge/puzzle`, drags the handle into the
gap with a curved, jittered, real-time drag, and posts to `/challenge/puzzle/verify`:

```json
{ "target": 0.805, "released": 0.8058, "align_error": 0.0008, "tol": 0.06,
  "n_drag_moves": 36, "solved": true, "decision": "allow",
  "reason": "passed the slide challenge" }
```

**Solved.** As `puzzle.py` itself notes, the gap position is visible to the
client, so a humanized drag clears both checks (alignment + "is this a live
drag"). The puzzle raises cost and adds a real UX step; it is not unbeatable —
the same wall as the click.

## Takeaways

- **Defense in depth works as a funnel.** Each layer removes a class of attacker
  cheaply: the fingerprint flag deletes all naive automation, behavioral +
  sub-pixel delete naive *and* HiDPI-integer movement, PoW taxes volume, and
  rate/reputation stops the repeat offender. No single layer is sufficient; the
  stack is.
- **The irreducible attacker is the same everywhere:** stealth + humanized +
  a float-coordinate engine (Playwright/Puppeteer) on a 1× display, at low
  volume. Against that, only PoW (cost) and reputation (volume) bite — which is
  precisely why `app.py` ships them.
- **Brittleness to tighten:** the `linear` glide still straddles bot/suspicious
  (0.15–0.42) around the `easing_r2 ≥ 0.985` cap; soften that cliff. The eight
  `stealth + humanized` passes in `captured/` are labeled-bot/​scored-human
  traces — drop them into `tests/fixtures/` and `bypasses/` as regressions.

## Reproduce

```bash
cd attacks/browser
pip install -r requirements.txt && python -m playwright install chromium && npm install
python run_all.py                 # click matrix  -> results.json
python run_defense.py             # rate-limit + puzzle -> defense_results.json
```
