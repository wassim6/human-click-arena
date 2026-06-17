"""Server-side request fingerprint — the JA3 you can actually get behind a
TLS-terminating proxy (Render, most PaaS, most CDNs).

HONEST SCOPE (read this before believing the layer does more than it does):

  Real TLS JA3/JA4 and HTTP/2 frame fingerprints need the *raw* ClientHello and
  h2 SETTINGS — which only the process that terminates TLS sees. On Render (and
  behind almost any managed proxy/CDN) TLS + HTTP/2 are terminated at the edge
  and your Flask app receives decrypted HTTP/1.1. So your app CANNOT compute a
  real JA3 itself. Two realistic options remain:

    1. If an edge injects the fingerprint as a header (Cloudflare `cf-ja3-hash`,
       or a custom `x-ja3` / `x-ja4`), read it here. We do, and flag known-bad
       hashes from JA3_BLOCKLIST.
    2. Fall back to an HTTP-layer fingerprint from the headers Flask *does* see:
       the User-Agent and the presence/consistency of the `Sec-Fetch-*` /
       `sec-ch-ua` client-hint headers that browsers attach automatically.

  WHAT THIS CATCHES: a *non-browser* client hitting /score directly — curl,
  requests, httpx, Go-http, our own urllib flood — i.e. the "skip the browser
  and POST a forged human trace" attack that the JS + behavioral layers cannot
  see at all. (Header order would add signal, but WSGI discards it, so we rely
  on header *presence/values*.)

  WHAT THIS DOES NOT CATCH: a real Chrome under automation (Playwright/Puppeteer/
  Selenium driving a genuine browser). Its `fetch()` carries real `Sec-Fetch-*`
  and `sec-ch-ua`, and its TLS is a real Chrome's — identical to a human. Those
  attackers are the behavioral/sub-pixel/rate/PoW layers' job, not this one.
  And header values are trivially spoofable, so treat this as a cheap filter,
  not a wall.
"""
from __future__ import annotations

import re

# Substrings in the User-Agent that mark a non-browser HTTP stack or a headless
# build that forgot to mask itself.
UA_REDFLAGS = [
    "python-requests", "python-urllib", "aiohttp", "httpx", "curl", "wget",
    "go-http-client", "okhttp", "java/", "libwww", "axios", "node-fetch",
    "got (", "postmanruntime", "insomnia", "scrapy", "headlesschrome",
    "phantomjs", "electron", "playwright", "puppeteer", "selenium",
]

# Optional: JA3/JA4 hashes you've decided are bot stacks. Populated by you over
# time (e.g. the JA3 of curl_cffi / a known scraper). Empty by default.
JA3_BLOCKLIST: set[str] = set()
JA4_BLOCKLIST: set[str] = set()


def _ja_from_edge(headers) -> dict:
    """Read a TLS fingerprint if (and only if) an upstream edge injected one."""
    ja3 = (headers.get("CF-JA3-Hash") or headers.get("X-JA3-Hash")
           or headers.get("X-JA3") or "")
    ja4 = (headers.get("X-JA4") or headers.get("CF-JA4") or "")
    return {"ja3": ja3 or None, "ja4": ja4 or None,
            "source": "edge-header" if (ja3 or ja4) else None}


def analyze(request) -> dict:
    h = request.headers
    ua = (h.get("User-Agent") or "").strip()
    ua_l = ua.lower()

    # Browsers attach Sec-Fetch-* to every fetch/navigation and cannot be removed
    # from page JS; Chromium also sends sec-ch-ua. Non-browser clients omit them.
    has_sec_fetch = any(h.get(k) for k in ("Sec-Fetch-Site", "Sec-Fetch-Mode", "Sec-Fetch-Dest"))
    has_ch_ua = bool(h.get("Sec-CH-UA"))
    has_accept_lang = bool(h.get("Accept-Language"))
    ae = (h.get("Accept-Encoding") or "").lower()
    has_brotli = "br" in ae

    ua_flags = [s for s in UA_REDFLAGS if s in ua_l] or ([] if ua else ["empty user-agent"])

    ja = _ja_from_edge(h)
    ja3_bad = bool(ja["ja3"] and ja["ja3"] in JA3_BLOCKLIST)
    ja4_bad = bool(ja["ja4"] and ja["ja4"] in JA4_BLOCKLIST)

    # Classify the client.
    if has_sec_fetch or has_ch_ua:
        client_class = "browser"
    elif ua_flags or not has_accept_lang:
        client_class = "non_browser"
    else:
        client_class = "unknown"

    reasons = []
    if ua_flags:
        reasons.append("user-agent looks like an HTTP library/headless: " + ", ".join(ua_flags))
    if client_class == "non_browser":
        reasons.append("no Sec-Fetch-*/sec-ch-ua headers — request did not come from a real browser fetch")
    if ja3_bad:
        reasons.append(f"TLS JA3 {ja['ja3']} is on the blocklist")
    if ja4_bad:
        reasons.append(f"TLS JA4 {ja['ja4']} is on the blocklist")

    suspicious = client_class == "non_browser" or ja3_bad or ja4_bad

    return {
        "client_class": client_class,          # browser | non_browser | unknown
        "suspicious": suspicious,
        "reasons": reasons,
        "ua": ua,
        "signals": {
            "sec_fetch": has_sec_fetch,
            "sec_ch_ua": has_ch_ua,
            "accept_language": has_accept_lang,
            "brotli": has_brotli,
        },
        "tls": ja,                              # {ja3, ja4, source} — None unless an edge injects it
        "tls_available": ja["source"] is not None,
    }
