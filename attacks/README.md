# Live attacks

Scripts here drive the **real OS mouse** against the running demo, instead of fabricating a trace.
This is the honest test of the whole premise: OS-level input is `isTrusted: true` with no automation
framework attached, so the only thing that can give it away is the **shape of the motion**.

## `pyautogui_attack.py`

Uses the real `pyautogui` library. It screenshots the screen, locates the demo button via the
[`click.png`](click.png) template (image recognition), moves the physical cursor onto it, and clicks.

```bash
# 1. start the demo in another terminal
python server/app.py            # open http://127.0.0.1:5000, make the CLICK button visible

# 2. install attacker deps
pip install -r attacks/requirements.txt

# 3a. naive — straight line + a fixed easing tween (the scorer flags this)
python attacks/pyautogui_attack.py --mode naive

# 3b. bezier — curved path, but regular timing + integer pixels + no tremor.
#     Defeats straightness/easing, yet still gets flagged by the other signals.
python attacks/pyautogui_attack.py --mode bezier --bow 0.3

# 3c. humanized — bezier + tremor + irregular timing + overshoot/correct
#     + variable click dwell (your challenge: can it score as human?)
python attacks/pyautogui_attack.py --mode humanized --rounds 5
```

The three modes are a progression. Against the current scorer they land roughly:

| Mode | Path | Timing | Tremor | Pixels | Verdict on HiDPI | Verdict on 1x |
|---|---|---|---|---|---|---|
| `naive` | straight + easing | regular | none | integer | **bot** | **bot** |
| `bezier` | curved Bezier | regular | none | integer | **bot** | **bot** |
| `humanized` | curved + correct | irregular | yes | integer | **bot** | **human** |

`--bow` controls how much the bezier curve bends (fraction of travel distance); `--steps` sets how many
points the path is sampled into.

### The integer-pixel ceiling

`humanized` produces genuinely human-shaped motion — curved, with overshoot/correction, irregular
timing and tremor. The behavioral signals alone score it as human. What still gives it away is that
`pyautogui` moves to **whole pixels**, while on a **HiDPI display (`devicePixelRatio > 1`)** a real
pointer reports **sub-pixel** coordinates. So an all-integer gesture is a near-certain OS injector
there — that's the cap that flips `humanized` to bot (see `tests/fixtures/pyautogui_humanized.json`).

This is conditional and honest: on a **1x display** humans also land on integers, so the signal is
uninformative and `humanized` passes. To beat the detector for real you'd need to feed it **sub-pixel,
genuinely human-recorded** motion (e.g. replay a recording, or inject fractional coordinates below the
`pyautogui` layer). At that point the behavioral + sub-pixel layers can't separate it from a human —
which is exactly where a production system leans on **server-side** signals (TLS/JA3, IP reputation).
That's the real next bypass to submit.

You have `--delay` seconds (default 2) after launching to focus the demo page. Slam the mouse into a
screen corner at any time to abort (pyautogui fail-safe).

### `click.png`

`click.png` ships as a generated approximation of the demo button. **Image matching is pixel- and
scale-sensitive**, so if the button isn't found, recreate the template from *your own* screen:

```bash
# screenshot, then crop tightly around the CLICK button and save as attacks/click.png
```

Lower the match threshold with `--confidence 0.6` (requires `opencv-python`).

### Solving the slide challenge

When repeated clicks trigger a `challenge`, the page shows a slide-to-fit puzzle. Add `--solve-puzzle`
and the attacker will, after each click, locate the piece and the gap on screen and humanized-drag one
onto the other:

```bash
python attacks/pyautogui_attack.py --mode humanized --image attacks/click-my.png --solve-puzzle
```

It uses two templates, [`piece.png`](piece.png) (the blue draggable square) and [`gap.png`](gap.png)
(the dashed outline), shipped as approximations of the demo's CSS. As with `click.png`, **image
matching is scale-sensitive** — on a HiDPI/Retina screen, re-screenshot the piece and the gap from your
own display and pass them with `--piece` / `--gap`, and/or lower `--confidence 0.6` (needs
`opencv-python`).

Honest note: this works because the gap is *visible* on screen — the bot just has to see it and drag
there convincingly. The drag is verified server-side for a real motion (not a teleport), so the same
humanized-motion arms race applies; it's not a magic bypass.

### macOS notes

- **Retina/HiDPI:** screenshots are in physical pixels but `moveTo` uses logical points. If the cursor
  lands at double the offset, pass `--retina-scale 2`.
- **Permissions:** grant the terminal app *Accessibility* and *Screen Recording* in
  System Settings > Privacy & Security, or pyautogui can't move the mouse / take screenshots.
- **Port 5000** is the AirPlay Receiver; run the demo with `PORT=5050 python server/app.py` if needed.

## Why two PyAutoGUI files?

| File | What it does | When |
|---|---|---|
| `tools/generate_pyautogui_trace.py` | Fabricates a JSON trace offline (no GUI) | tests / CI / quick scoring |
| `attacks/pyautogui_attack.py` | Drives the real cursor against the live demo | hands-on, end-to-end attack |

The first proves the scorer's math without a desktop; the second is the real thing. Beat the scorer
with the humanized mode and [submit it as a bypass](../bypasses/README.md).
