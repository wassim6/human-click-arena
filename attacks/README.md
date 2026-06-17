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

| Mode | Path | Timing | Tremor | Pixels | Typical verdict |
|---|---|---|---|---|---|
| `naive` | straight + easing | regular | none | integer | **bot** |
| `bezier` | curved Bezier | regular | none | integer | **bot** (curve alone isn't enough) |
| `humanized` | curved + correct | irregular | yes | integer | often **human** — beat it and submit it |

`--bow` controls how much the bezier curve bends (fraction of the travel distance); `--steps` sets how
many points the path is sampled into.

You have `--delay` seconds (default 2) after launching to focus the demo page. Slam the mouse into a
screen corner at any time to abort (pyautogui fail-safe).

### `click.png`

`click.png` ships as a generated approximation of the demo button. **Image matching is pixel- and
scale-sensitive**, so if the button isn't found, recreate the template from *your own* screen:

```bash
# screenshot, then crop tightly around the CLICK button and save as attacks/click.png
```

Lower the match threshold with `--confidence 0.6` (requires `opencv-python`).

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
