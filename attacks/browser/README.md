# Browser-automation attacks — selenium / seleniumbase / puppeteer / playwright

Drives the detector with the four big automation stacks, in **stealth and
non-stealth** modes, across three movement strategies, and scores the resulting
click. This is the "bring your selenium/puppeteer/playwright" challenge from the
top-level README, wired up end to end.

Results from a real run are in **[RESULTS.md](RESULTS.md)** (`results.json` +
captured traces under `captured/`).

## What gets tested

Each engine is run with `--stealth` and without, across three strategies:

| Strategy | What it does | Realistic of |
|---|---|---|
| `native` | the engine's own `click()` — one hop to the element centre + down/up | a typical scraper |
| `linear` | a straight, evenly-timed glide to the target (`mouse.move(..., steps=N)` / chained moves) | a lazy "move before click" |
| `humanized` | curved Bezier path + jitter + overshoot/correct (Puppeteer uses real **ghost-cursor**) | an attacker who humanizes |

`--stealth` toggles the well-known fingerprint patches:
`selenium-stealth`, SeleniumBase **UC mode**, `puppeteer-extra-plugin-stealth`,
`playwright-stealth`. They patch `navigator.webdriver`, `chrome.runtime`, WebGL
vendor, etc. — **none of them touch pointer trajectories**, which is the whole
point: against a behavioral scorer they change nothing.

## Run it

```bash
# 1) deps
cd attacks/browser
pip install -r requirements.txt
python -m playwright install chromium      # playwright/puppeteer share this browser
npm install                                # puppeteer-core + extra + stealth + ghost-cursor

# 2) everything at once (boots the scorer in-process, writes results.json)
python run_all.py
#    -> selenium, seleniumbase, puppeteer, playwright  x  3 strategies  x  {plain, stealth}

# or a single engine/strategy against a server you started yourself:
python harness_server.py &                 # http://127.0.0.1:5001
python playwright_attack.py  --strategy humanized            # human?
python puppeteer_attack.js   --strategy humanized --stealth  # (node)
python selenium_attack.py    --strategy native               # bot
python seleniumbase_attack.py --strategy linear --stealth

# HiDPI sub-pixel tell (the integer-coordinate engines get caught):
python run_all.py --engines selenium,playwright --strategies humanized --dpr 2
```

Each driver prints one JSON line (verdict, score, sub-scores, key features) and,
with `--save DIR`, writes the exact trace it sent so you can replay or submit it
as a [bypass](../../bypasses/README.md).

## Files

| File | Role |
|---|---|
| `harness_server.py` | serves a *controlled* page (fixed target) using the real `collector.js` + real `scorer.py`, exposes `POST /score` |
| `harness.html` | the page; exposes `window.HCA` to attach the collector and read the trace back |
| `playwright_attack.py` | Playwright driver (`--stealth` = playwright-stealth) |
| `puppeteer_attack.js` | Puppeteer driver (`--stealth` = puppeteer-extra-stealth; `humanized` = ghost-cursor) |
| `selenium_attack.py` | Selenium driver (`--stealth` = selenium-stealth) |
| `seleniumbase_attack.py` | SeleniumBase driver (`--stealth` = UC mode) |
| `humanize.py` | curved + jittered + overshoot path generator (Python strategies) |
| `emulate.py` | trajectory-equivalent fallback when no chromedriver is available (see note) |
| `run_all.py` | boots the server and runs the whole matrix → `results.json` |

> **Note on Selenium/SeleniumBase + arm64.** Selenium needs a matching
> `chromedriver`, and **no official `linux-arm64` chromedriver is published**
> upstream (Chrome-for-Testing ships `linux64`/macOS only). On such a host the
> real driver can't start, so `run_all.py` falls back to `emulate.py`, which
> replays Selenium's *exact* pointer event stream (integer-coordinate W3C
> Actions) through the shared Chromium and scores the real events. On a normal
> x86_64/macOS machine the genuine `selenium_attack.py` / `seleniumbase_attack.py`
> run unchanged. Either way the trajectory — the only thing the scorer sees — is
> identical, because every WebDriver/CDP click bottoms out at the same pointer
> primitive.
