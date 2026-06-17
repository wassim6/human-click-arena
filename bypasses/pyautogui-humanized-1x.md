# Bypass: humanized pyautogui on a 1x display (reference bypass)

- **Handle:** wass (project author)
- **Date:** 2026-06-17
- **Tool / stack:** real `pyautogui` driving a real Chrome, `--mode humanized`, on a standard 1x display
- **Trace file:** `bypasses/pyautogui-humanized-1x.json`

This is the **reference bypass**: the attack that the client-side layers cannot stop, and the reason
the project grew a server-side layer. It is kept here permanently as the boundary of what behavioral
detection can do.

## Score achieved

```
behavioral score:   0.68
behavioral verdict: human
```

## Technique

A genuine browser driven by the real OS mouse (`pyautogui`), so every event is `isTrusted` with no
automation framework attached and a real TLS/HTTP fingerprint — nothing for framework- or
request-fingerprinting to flag. The motion is humanized:

- **Path generation:** quadratic Bézier with an off-axis control point (curved, not straight).
- **End approach:** overshoot past the target, then a corrective sub-movement back onto it.
- **Timing model:** irregular per-step delays (mean ~30 ms, high variance).
- **Tremor / noise:** small per-sample jitter.
- **Click dwell:** variable down→up interval (~94 ms here).
- **The key escape:** captured on a **1x display**, so `devicePixelRatio == 1`. On a HiDPI display
  pyautogui's integer pixels would be caught (real pointers report sub-pixel there); on 1x, humans
  also land on integers, so that signal is — correctly — disabled to avoid false positives.

## Reproducibility

- [x] Stochastic but consistently passes

## Why it works

It fools every behavioral sub-score: `straightness` (curved), `easing` (no clean tween fit),
`timing` (irregular), `submovements` (overshoot + correction = multiple velocity peaks), `tremor`
(jitter present). The only remaining client-side tell — integer pixels — is unavailable on 1x.

## Status: WON'T FIX (by design)

There is no robust *client-side* signal that separates this from a real human on a 1x display without
also blocking real users. This is the theoretical ceiling of single-request behavioral detection. The
project's answer is **not** another behavioral heuristic but the server-side layer:

- **proof-of-work** (`server/pow.py`) — makes each attempt cost CPU, so doing this at scale is expensive;
- **rate limiting / reputation** (`server/reputation.py`) — catches the same client doing it many times.

Run it through `/score` once → `allow`. Run it 30× from the same client → `deny` (rate limit), with
the behavioral verdict still "human" the whole time. That contrast is the whole lesson.
