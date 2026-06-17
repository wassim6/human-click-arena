"""Make the bot solve the server's slide puzzle with a humanized drag.

Flow against the real server (server/app.py):
    GET  /challenge/puzzle          -> {salt, target, tol, ts, sig}
    (drag the handle into the gap with a curved, jittered, real-time drag)
    POST /challenge/puzzle/verify   -> {ok, decision, reason}

The server's puzzle.verify checks: valid signature, not expired/used, the handle
released within `tol` of the gap, AND that the drag is a *live* drag (enough
move samples, duration and travel — not an instant teleport). A humanized drag
clears all of it.

    python puzzle_attack.py [--url http://127.0.0.1:5002] [--seed 5]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from humanize import human_path  # noqa: E402

# Track geometry (must match the page below). released = (handle.left - LEFT)/W.
LEFT, TOP, W, H, HANDLE_W = 120, 300, 520, 44, 48

SLIDER_HTML = f"""<!DOCTYPE html><html><head><meta charset=utf-8>
<style>
 html,body{{margin:0;height:100%;background:#0e1116}}
 #track{{position:absolute;left:{LEFT}px;top:{TOP}px;width:{W}px;height:{H}px;
   background:#21262d;border:1px solid #30363d;border-radius:8px}}
 #gap{{position:absolute;top:{TOP}px;width:{HANDLE_W}px;height:{H}px;
   border:2px dashed #d29922;box-sizing:border-box;border-radius:8px}}
 #handle{{position:absolute;left:{LEFT}px;top:{TOP}px;width:{HANDLE_W}px;height:{H}px;
   background:#1f6feb;border:1px solid #79c0ff;border-radius:8px;box-sizing:border-box}}
</style></head><body>
<div id=track></div><div id=gap></div><div id=handle></div>
<script>
(function(){{
 var LEFT={LEFT},W={W},HW={HANDLE_W};
 var handle=document.getElementById('handle'),gap=document.getElementById('gap');
 var dragging=false,grabX=0,startLeft=0,t0=null,moves=[];
 function clamp(v){{return Math.max(LEFT,Math.min(LEFT+W-HW,v));}}
 handle.addEventListener('pointerdown',function(e){{dragging=true;grabX=e.clientX;startLeft=handle.offsetLeft;}});
 window.addEventListener('pointermove',function(e){{
   if(!dragging)return;
   handle.style.left=clamp(startLeft+(e.clientX-grabX))+'px';
   if(t0===null)t0=performance.now();
   moves.push({{type:'move',x:Math.round(e.clientX*100)/100,y:Math.round(e.clientY*100)/100,
     t:Math.round((performance.now()-t0)*100)/100}});
 }});
 window.addEventListener('pointerup',function(){{dragging=false;}});
 window.PZ={{
   setup:function(target){{gap.style.left=(LEFT+target*W)+'px';return {{grabX:LEFT+HW/2,grabY:{TOP}+{H}/2}};}},
   released:function(){{return (handle.offsetLeft-LEFT)/W;}},
   trace:function(){{return {{events:moves.slice()}};}}
 }};
 window.__PZ_READY=true;
}})();
</script></body></html>"""


def _get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read())


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def run(args):
    base = args.url
    ch = _get(base + "/challenge/puzzle")     # {salt, target, tol, ts, sig, type}
    target = float(ch["target"])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
        page = browser.new_context(viewport={"width": 1000, "height": 600}).new_page()
        page.set_content(SLIDER_HTML)
        page.wait_for_function("window.__PZ_READY === true")
        grab = page.evaluate("(t) => window.PZ.setup(t)", target)

        gx, gy = grab["grabX"], grab["grabY"]
        end_x = gx + target * W                 # pointer dx == handle travel
        page.mouse.move(gx, gy)
        page.mouse.down()
        for (x, y, dt) in human_path((gx, gy), (end_x, gy), seed=args.seed):
            page.mouse.move(x, y)
            time.sleep(dt / 1000.0)
        page.mouse.up()

        released = page.evaluate("() => window.PZ.released()")
        trace = page.evaluate("() => window.PZ.trace()")
        browser.close()

    solution = {"salt": ch["salt"], "target": ch["target"], "tol": ch["tol"],
                "ts": ch["ts"], "sig": ch["sig"], "released": released, "trace": trace}
    res = _post(base + "/challenge/puzzle/verify", solution)

    out = {"engine": "puzzle-solver", "strategy": "humanized", "target": round(target, 4),
           "released": round(released, 4), "align_error": round(abs(released - target), 4),
           "tol": ch["tol"], "n_drag_moves": len(trace["events"]),
           "solved": res.get("ok"), "decision": res.get("decision"),
           "reason": res.get("reason", "")}
    print(json.dumps(out))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5002")
    ap.add_argument("--seed", type=int, default=5)
    run(ap.parse_args())
