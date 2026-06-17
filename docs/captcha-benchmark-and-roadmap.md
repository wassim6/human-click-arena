# Where human-click-arena sits next to the real ones

A technical comparison of the arena's detector against the three commercial
systems it is implicitly competing with — **Google reCAPTCHA (v2 / v3 /
Enterprise)**, **Cloudflare Turnstile**, and **hCaptcha** — and a prioritized
roadmap for closing the gap.

> Scope note: vendor internals below are pieced together from public docs and
> third‑party reverse‑engineering, not official specs. Treat exact numbers
> (e.g. reCAPTCHA score baselines) as *reported*, not guaranteed. The arena
> side is exact — it is read straight from the code in `server/`.

---

## TL;DR

The arena is a **strong, transparent behavioral‑shape analyzer** with a couple
of cheap fingerprint gates and two rate/cost layers bolted on. Its movement
analysis (curvature, easing fit, timing irregularity, sub‑movements, tremor,
sub‑pixel) is genuinely good and is conceptually the *same sub‑signal* the
commercial systems feed into their models.

The gap is not the quality of that signal — it's **breadth and unspoofability**:

- The commercial systems score **network‑layer signals the client cannot forge**
  (TLS/JA3‑JA4 fingerprint, HTTP/2 fingerprint, IP/ASN reputation). The arena
  has **none** of these. Its README already admits this is the honest ceiling.
- They aggregate **whole‑session and cross‑session** behavior + a **device
  fingerprint**; the arena scores **one gesture, one request**.
- Their automation tells are **derived/attested**; the arena's automation tells
  (`navigator.webdriver`, CDP, driver globals) are **client‑reported and reset
  to `false` by any stealth plugin** — which is exactly why your two "winners"
  (stealth Puppeteer/Playwright) walk through them.
- They score with **continuously retrained, adversarial ML**; the arena uses a
  **fixed transparent weighted heuristic** (by design — it's meant to be
  readable and beatable).

The single highest‑leverage move is to add the **unspoofable server‑side tier**
(TLS + HTTP/2 + IP reputation). That, not more mouse math, is what stops a
well‑humanized stealth browser.

---

## 1. What the arena measures today (exact, from `server/`)

### Behavioral layer — `features.py` → `scorer.py`

| Sub‑signal | Feature | What it catches | Weight |
|---|---|---|---|
| straightness | `directness` = displacement / path length | straight‑line bots | 1.4 |
| easing | `easing_r2` (fit to known tweens) | bots matching a parametric tween | 1.6 |
| timing | `dt_cv` (CV of inter‑event intervals) | metronomic event timing | 1.2 |
| submovements | `n_velocity_peaks` | single eased move vs human corrections | 1.0 |
| tremor | `mean_abs_turn_rad` | absence of physiological jitter | 1.0 |
| subpixel | `int_coord_ratio` | OS injectors landing on whole pixels | 0.7 |

Plus hard gates and caps: **no‑movement → bot**; **easing R²≥0.985 + directness≥0.99 → cap 0.15**;
**HiDPI + all‑integer coords → cap 0.22** (the dpr=2 tell). `click_dwell_ms` and
`max_perp_deviation` are extracted but not yet scored.

### Fingerprint gates — client‑reported in `meta` (spoofable)

`navigator.webdriver`, `cdp` (CDP Runtime attached), `driverProps`
(`$cdc_…`/`__webdriver_*` globals). Any `true` → score 0. **All three are reset
by stealth plugins**, so they only ever catch naive automation.

### Cost & volume layers — `pow.py`, `reputation.py`

- **Proof‑of‑work**: Argon2id, memory‑hard (8 MiB), signed challenge. Makes
  volume expensive; does *not* tell human from bot on a single request.
- **Rate / reputation**: in‑memory counters keyed on `IP + UA + dpr`
  (>3/short → challenge, >10/long → 1 h block). A crude IP‑reputation stand‑in.
- **Slide puzzle** (`puzzle.py`) as an escalation challenge.

---

## 2. How the commercial systems actually score

### Google reCAPTCHA

- **v2 ("I'm not a robot")** — clicking the checkbox is the *least* of it. Before
  you click, reCAPTCHA has already weighed your **Google cookies** (`NID`,
  `_GRECAPTCHA`, account cookies `SID/HSID`), **browser integrity / headless
  traits**, **mouse + scroll behavior**, and **IP/ASN reputation**. A trusted
  cookie graph lets you pass with one click; a cold, cookie‑less, datacenter‑IP
  session gets the image challenge.
- **v3** — invisible, returns a **0.0–1.0 risk score per action**, no challenge.
  Same signal mix: browser integrity, behavior (mouse/scroll/typing/tab‑switch),
  IP+ASN reputation, **history tied to the session/browser/token**, and cookie
  trust. Reported baselines: a cookied session starts ~0.5–0.7, a cleared one
  ~0.3–0.5. Sites pick thresholds (e.g. block <0.3, challenge 0.3–0.6, allow >0.6).
- **Enterprise** — adds reason codes, account‑defender / multi‑factor risk, and
  more aggressive cross‑Google signals.

### Cloudflare Turnstile

Non‑interactive by default. Runs a battery of **background JS micro‑challenges**:
**proof‑of‑work**, **proof‑of‑space**, **browser‑API probing** (canvas, WebGL,
audio, `navigator`), and quirk detection, plus **human signals** (mouse timing,
focus events, jitter). Results feed **distributed ML models** that output a
human probability and **adapt difficulty per request**. Issues a **short‑lived
token verified server‑side**. Crucially it can use **Private Access Tokens
(PAT)**: a device manufacturer (e.g. Apple) **attests the hardware/software is
genuine** without revealing the site — a signal that **fingerprinting can't fake
and stealth can't patch**. It also rides Cloudflare's **network‑wide threat
intelligence** (the global view of the IP/ASN across all sites).

### hCaptcha

Risk score **0.0–1.0** from **privacy‑preserving ML** using "thousands of data
points," **device fingerprinting**, **behavioral patterns**, and **intent
analysis**, with explicit **multi‑accounting / abuse‑at‑scale** detection.
Enterprise ("BotStop") scores *abuse*, not just *humanity*. Falls back to image
tasks and runs **proof‑of‑work** under the hood.

---

## 3. Signal‑by‑signal: arena vs the field

✅ = scored · ⚠️ = collected but spoofable / weak · ❌ = absent

| Signal class | Arena | reCAPTCHA | Turnstile | hCaptcha |
|---|:--:|:--:|:--:|:--:|
| Pointer‑movement shape (curve/easing/tremor) | ✅ strong | ✅ | ✅ | ✅ |
| Sub‑pixel / HiDPI coordinate tell | ✅ | ~ | ~ | ~ |
| Timing irregularity | ✅ | ✅ | ✅ | ✅ |
| Whole‑session behavior (scroll, focus, keystroke) | ❌ | ✅ | ✅ | ✅ |
| Cross‑session history / reputation | ❌ | ✅ (cookies/account) | ✅ (network) | ✅ |
| `navigator.webdriver` / CDP / driver globals | ⚠️ client‑reported | ✅ derived | ✅ derived | ✅ derived |
| Headless / stealth‑patch detection | ❌ | ✅ | ✅ | ✅ |
| Device fingerprint (canvas/WebGL/audio/fonts) | ❌ | ✅ | ✅ | ✅ |
| **TLS fingerprint (JA3/JA4)** | ❌ | ✅ | ✅ | ✅ |
| **HTTP/2 fingerprint + header order** | ❌ | ✅ | ✅ | ✅ |
| **IP / ASN reputation, datacenter vs residential** | ⚠️ raw rate limit | ✅ | ✅ | ✅ |
| Proof‑of‑work / proof‑of‑space | ✅ PoW | — | ✅ both | ✅ |
| Device attestation / Private Access Tokens | ❌ | ~ | ✅ | ~ |
| Signed, single‑use, action‑bound token | ⚠️ partial (PoW sig) | ✅ | ✅ | ✅ |
| ML risk model (adversarial, retrained) | ❌ fixed heuristic | ✅ | ✅ | ✅ |

The pattern is clear: the arena is **competitive on movement** and even ahead on
the **sub‑pixel tell**, but it is **missing the entire network/device tier** and
treats automation flags as trustworthy when they aren't.

---

## 4. The tier that actually stops your "winners"

Your README's honest ceiling is correct: a humanized real‑browser click on a 1×
display is indistinguishable from a human **at the event level**. What still
separates them lives **below JavaScript**, where the client can't lie:

- **TLS fingerprint (JA3/JA4).** The ClientHello (cipher suites, extensions,
  curves, order) is set by the TLS stack, not your JS. A stealth Puppeteer that
  *says* it's Chrome 120 but presents a non‑Chrome ClientHello — or pairs a
  Chrome JA3 with a Firefox UA — is flagged instantly. Proxies hide the IP, not
  the handshake.
- **HTTP/2 fingerprint.** Frame ordering, SETTINGS values, header casing/order.
  "Chrome TLS over HTTP/1.1" screams automation tool.
- **IP/ASN reputation.** Datacenter ASN, known proxy/VPN ranges, and threat‑intel
  feeds. Residential proxies dodge the reputation check but still carry the
  wrong TLS/HTTP fingerprint.
- **Attestation (PAT).** Hardware‑backed proof of a genuine device. Stealth can
  patch a flag; it cannot mint an Apple attestation.

None of these require a better mouse model — and none can be defeated by
ghost‑cursor or playwright‑stealth, which is the whole point.

---

## 5. Roadmap — prioritized by (impact × unspoofability ÷ effort)

### Tier 1 — add the unspoofable server‑side signals  *(highest leverage)*

1. **TLS JA3/JA4 + UA‑consistency check.** Terminate TLS at a proxy that exposes
   the ClientHello (e.g. nginx with a JA3 module, HAProxy, or a small Go front
   that forwards the hash as a header) and pass `X‑JA4` into Flask. Score:
   datacenter‑typical or automation‑typical fingerprint → penalty; JA3 browser
   family ≠ UA browser family → hard fail. *Note: a plain Flask/WSGI app can't
   see the raw ClientHello — this needs a TLS‑terminating front end.*
2. **HTTP/2 fingerprint + header order/casing** captured at the same front end.
3. **IP/ASN reputation.** Cheapest immediate win: ship a datacenter‑ASN list and
   a proxy/VPN range feed; flag non‑residential origins. Replaces the raw
   in‑memory counter with a real reputation input.

### Tier 2 — turn the client flags you already collect into real tells

4. **Detect the stealth *patch*, not the flag.** Stealth libs reset
   `navigator.webdriver=false` but leave fingerprints: `Function.prototype.toString`
   tampering, inconsistent `navigator.permissions`, missing `chrome.runtime`,
   `navigator.plugins`/`mimeTypes` inconsistencies, `hardwareConcurrency`/
   `deviceMemory` oddities. Collect these in `collector.js` and score them.
5. **Headless detection.** WebGL vendor/renderer = `SwiftShader`/`llvmpipe`,
   absent `AudioContext`, screen/orientation and permissions quirks.
6. **Device fingerprint + internal consistency.** Canvas/WebGL/audio/fonts hash;
   cross‑check UA ⇄ platform ⇄ JS‑engine behavior ⇄ (later) TLS.

### Tier 3 — broaden behavior and make the scorer a model

7. **Score the whole session, not just the final gesture.** Add scroll dynamics,
   focus/blur, dwell/hesitation, keystroke timing, multiple gestures. (You
   already isolate the final gesture in `final_gesture()` — keep that, but also
   summarize the surrounding session.)
8. **Replace the linear heuristic with a trained model** on the labeled
   human/bot traces the arena collects — the README's stated end state. Feature
   extraction stays; only `score()` changes. Add an adversarial retraining loop:
   every accepted bypass becomes a training row.
9. **Harden the token.** Issue a signed, **single‑use, short‑TTL token bound to
   action + hostname** on a pass; verify server‑side. You already sign PoW
   challenges — generalize that to the score result.

### Tier 4 — proof‑of‑personhood  *(highest unspoofability, hardest)*

10. **Private Access Tokens / Privacy Pass attestation.** Let genuine devices
    vouch via OS/hardware attestation. Large lift, but it's the only tier even a
    perfect stealth browser cannot fake.

### What *not* to invest more in

More mouse‑shape math has diminishing returns — your behavioral layer is already
near the realistic ceiling for single‑gesture analysis, and a replayed real
human trace beats any amount of it. Spend the effort below JavaScript (Tier 1)
and on breadth (Tier 3) instead.

---

## Sources

- [reCAPTCHA v3 score & signals — DataDome](https://datadome.co/anti-detect-tools/recaptha-score/)
- [reCAPTCHA cookie/session requirements — CaptchaAI](https://blog.captchaai.com/recaptcha-cookie-session-requirements)
- [reCAPTCHA v2 vs v3 — FriendlyCaptcha](https://friendlycaptcha.com/insights/recaptcha-v2-vs-v3/)
- [Cloudflare Turnstile — official overview](https://developers.cloudflare.com/turnstile/)
- [How Turnstile works — peak.fo](https://blog.peak.fo/cloudflare-turnstile-how-it-works/)
- [Turnstile & Private Access Tokens — Scrappey](https://scrappey.com/qa/anti-bot/what-is-cloudflare-turnstile)
- [hCaptcha Enterprise / bot detection](https://www.hcaptcha.com/bot-detection)
- [How modern CAPTCHAs work in 2025 — Kameleo](https://kameleo.io/blog/how-modern-captchas-work-in-2025)
- [TLS fingerprinting JA3/JA4 — Scrapfly](https://scrapfly.io/web-scraping-tools/ja3-fingerprint)
- [TLS fingerprinting & proxy detection — Medium](https://medium.com/@patriciazmorales/tls-fingerprinting-ja3-ja4-proxies-detection-8b5b2e515e8c)
