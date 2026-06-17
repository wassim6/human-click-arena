# Bypasses — the arena

This is where the project gets better. If you made the scorer return `human` (score ≥ 0.5) for input
that was **not** a real human hand, you win — and you make the next version harder.

## What counts as a bypass

A trace that:

1. was produced by automation (`pyautogui`, `selenium`, `selenium-base`, `playwright`, `puppeteer`,
   a humanization lib, a replay of a recording, hand-crafted JSON — anything non-human), **and**
2. scores **≥ 0.5** ("human"), or **≥ 0.3** ("suspicious") if you think the threshold is the bug.

Replaying a recording of *your own real* mouse counts — that's a legitimate and interesting attack,
and it tells us the behavioral layer alone isn't enough (it isn't; that's the point).

## How to submit

1. Capture the exact trace you sent (the demo page has a **Copy last trace** button, or POST your own
   JSON to `/score`).
2. Add it as a file: `bypasses/<your-handle>-<short-name>.json`.
3. Copy `TEMPLATE.md` to `bypasses/<your-handle>-<short-name>.md` and fill it in: tool used, technique,
   the score you got, and how reproducible it is.
4. Open a PR. We'll verify, credit you, add the trace as a regression fixture, and harden the scorer.

## Rules

- **Defensive research only.** This repo is for understanding and improving bot detection. Don't use
  submissions to attack sites you don't own.
- Include the *method*, not just the trace — the technique is what teaches the detector.
- One technique per PR keeps the history useful.

## Hall of fame

| Handle | Technique | Behavioral score | Status |
|---|---|---|---|
| wass | [humanized pyautogui on a 1x display](pyautogui-humanized-1x.md) | 0.68 / human | won't fix (client-side ceiling) → server layer |
| _(you?)_ | | | |

The reference bypass above is the boundary of behavioral detection. The interesting open challenges
now are: beat it on a **HiDPI** display (defeat the integer-pixel signal — e.g. inject sub-pixel
coordinates), or defeat the **server** layers (cheap proof-of-work solving, or evading the rate limit
with rotated fingerprints).
