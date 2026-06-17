"""The server-side request fingerprint: browser vs non-browser HTTP client."""

import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "server"))

from werkzeug.test import EnvironBuilder        # noqa: E402
from werkzeug.wrappers import Request           # noqa: E402

import request_fingerprint as rfp               # noqa: E402

CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _req(headers):
    return Request(EnvironBuilder(method="POST", path="/score", headers=headers).get_environ())


def test_real_browser_fetch_passes():
    r = _req({"User-Agent": CHROME_UA, "Accept-Language": "en-US,en;q=0.9",
              "Accept-Encoding": "gzip, deflate, br", "Sec-Fetch-Mode": "cors",
              "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Dest": "empty",
              "Sec-CH-UA": '"Chromium";v="126"'})
    res = rfp.analyze(r)
    assert res["client_class"] == "browser"
    assert res["suspicious"] is False


def test_python_requests_is_flagged():
    r = _req({"User-Agent": "python-requests/2.31.0", "Accept-Encoding": "gzip, deflate"})
    res = rfp.analyze(r)
    assert res["client_class"] == "non_browser"
    assert res["suspicious"] is True


def test_curl_is_flagged():
    res = rfp.analyze(_req({"User-Agent": "curl/8.4.0", "Accept": "*/*"}))
    assert res["suspicious"] is True


def test_spoofed_headers_pass_this_layer():
    """Honest limitation: header values are trivially spoofable, so a scraper that
    sends the Chrome headers sails past this layer (only rate/PoW stop it)."""
    r = _req({"User-Agent": CHROME_UA, "Accept-Language": "en-US",
              "Sec-Fetch-Mode": "cors", "Sec-CH-UA": '"Chromium";v="126"'})
    assert rfp.analyze(r)["suspicious"] is False


def test_edge_ja3_blocklist_hit():
    rfp.JA3_BLOCKLIST.add("deadbeefcafe")
    try:
        r = _req({"User-Agent": CHROME_UA, "Accept-Language": "en-US",
                  "Sec-Fetch-Mode": "cors", "CF-JA3-Hash": "deadbeefcafe"})
        res = rfp.analyze(r)
        assert res["tls"]["ja3"] == "deadbeefcafe"
        assert res["tls_available"] is True
        assert res["suspicious"] is True
    finally:
        rfp.JA3_BLOCKLIST.discard("deadbeefcafe")
