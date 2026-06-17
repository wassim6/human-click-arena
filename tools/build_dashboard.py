"""Build the static arena dashboard at docs/index.html (for GitHub Pages).

Reads:
    attacks/browser/results.json          (the click matrix)
    attacks/browser/defense_results.json  (rate-limit flood + puzzle solve)
    bypasses/*.md                         (the hall of fame)

Emits a single self-contained docs/index.html with the data embedded inline, so
it renders anywhere (GitHub Pages, file://) with no server and no external CDN.

    python tools/build_dashboard.py
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROWSER = os.path.join(ROOT, "attacks", "browser")

LAYERS = [
    {"name": "Fingerprint", "checks": "the navigator.webdriver automation flag",
     "where": "scorer.py",
     "note": "A free catch for naive automation. Any stealth plugin resets it to false, so it only ever stops the lazy bots."},
    {"name": "Behavioral", "checks": "the shape of the motion — curvature, easing-fit, timing regularity, sub-movements, tremor",
     "where": "scorer.py / features.py",
     "note": "Flags straight, eased or instant motion. Beaten only by genuinely humanized movement."},
    {"name": "Sub-pixel", "checks": "integer-only coordinates on a HiDPI display (dpr > 1)",
     "where": "scorer.py",
     "note": "Catches OS injectors and the WebDriver Actions API (integer coords). Disabled on 1x, where humans also hit integers."},
    {"name": "Proof-of-work", "checks": "a SHA-256 leading-zero-bits puzzle on every request",
     "where": "pow.py",
     "note": "Makes each attempt cost CPU. One click is free; a million clicks cost a botnet real money."},
    {"name": "Rate / reputation", "checks": "request volume per client over two time windows",
     "where": "reputation.py",
     "note": "> 3 in 5 min → challenge; > 10 in 30 min → blocked for an hour. Volume is what one humanized bot can't hide."},
    {"name": "Puzzle", "checks": "a slide-to-fit drag — alignment plus a live (non-teleport) drag",
     "where": "puzzle.py",
     "note": "The human-facing escalation. Raises cost and adds a real UX step; not unbeatable (the gap is visible)."},
]


def parse_bypasses():
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "bypasses", "*.md"))):
        base = os.path.basename(path)
        if base in ("README.md", "TEMPLATE.md"):
            continue
        t = open(path, encoding="utf-8").read()

        def g(pat, default=""):
            m = re.search(pat, t)
            return m.group(1).strip() if m else default

        name = g(r"#\s*Bypass:\s*(.+)")
        score = g(r"score:\s*([0-9.]+)")
        verdict = g(r"verdict:\s*(\w+)")
        status = g(r"##\s*Status:\s*(.+)") or "accepted"
        json_file = base[:-3] + ".json"
        out.append({
            "name": name or base,
            "handle": g(r"\*\*Handle:\*\*\s*(.+)"),
            "date": g(r"\*\*Date:\*\*\s*(.+)"),
            "tool": g(r"\*\*Tool\s*/\s*stack:\*\*\s*(.+)"),
            "score": float(score) if score else None,
            "verdict": verdict or "human",
            "status": status,
            "file": "bypasses/" + json_file
            if os.path.exists(os.path.join(ROOT, "bypasses", json_file)) else None,
            "md": "bypasses/" + base,
        })
    return out


def main():
    results = json.load(open(os.path.join(BROWSER, "results.json")))
    # The HiDPI (dpr=2) cross-section is kept in a separate file so a normal
    # `run_all.py` (dpr=1) never clobbers it. Merge it in if present.
    hidpi_path = os.path.join(BROWSER, "results_hidpi.json")
    if os.path.exists(hidpi_path):
        have = {(r["engine"], r["strategy"], r["stealth"], r["dpr"]) for r in results}
        for r in json.load(open(hidpi_path)):
            if (r["engine"], r["strategy"], r["stealth"], r["dpr"]) not in have:
                results.append(r)
    try:
        defense = json.load(open(os.path.join(BROWSER, "defense_results.json")))
    except FileNotFoundError:
        defense = {}

    data = {
        "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "repo": "wassim6/human-click-arena",
        "results": results,
        "defense": defense,
        "layers": LAYERS,
        "bypasses": parse_bypasses(),
    }

    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    out_dir = os.path.join(ROOT, "docs")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    # .nojekyll so GitHub Pages serves the file verbatim
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    print("wrote docs/index.html  (" + str(len(html)) + " bytes, "
          + str(len(results)) + " runs, " + str(len(data["bypasses"])) + " bypasses)")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>human-click-arena — dashboard</title>
<style>
  :root{
    --bg:#0e1116;--panel:#161b22;--panel2:#0d1117;--line:#30363d;--ink:#e6edf3;
    --muted:#8b949e;--accent:#2f81f7;--good:#3fb950;--bad:#f85149;--warn:#d29922;--pur:#a371f7;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
  a{color:var(--accent);text-decoration:none}
  header{padding:34px 24px 10px;max-width:1080px;margin:0 auto}
  h1{margin:0;font-size:26px;letter-spacing:-.2px}
  h1 .by{color:var(--muted);font-weight:500;font-size:15px}
  header p{color:var(--muted);max-width:75ch;margin:8px 0 0}
  nav{position:sticky;top:0;background:rgba(14,17,22,.92);backdrop-filter:blur(6px);
    border-bottom:1px solid var(--line);z-index:5}
  nav .in{max-width:1080px;margin:0 auto;padding:10px 24px;display:flex;gap:18px;flex-wrap:wrap}
  nav a{color:var(--muted);font-weight:600;font-size:14px}
  nav a:hover{color:var(--ink)}
  main{max-width:1080px;margin:0 auto;padding:8px 24px 60px}
  section{margin:34px 0}
  h2{font-size:19px;margin:0 0 4px;display:flex;align-items:center;gap:10px}
  h2 .tag{font:600 11px system-ui;color:var(--muted);border:1px solid var(--line);
    border-radius:20px;padding:2px 9px}
  .sub{color:var(--muted);margin:0 0 16px;font-size:14px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}
  .grid{display:grid;gap:14px}
  .g3{grid-template-columns:repeat(3,1fr)}
  .g2{grid-template-columns:repeat(2,1fr)}
  @media(max-width:820px){.g3,.g2{grid-template-columns:1fr}}
  table{width:100%;border-collapse:collapse;font-size:13.5px}
  th,td{padding:7px 9px;text-align:left;border-bottom:1px solid var(--line)}
  th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px}
  td.eng{font-weight:600}
  .badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:12px;font-weight:700}
  .b-human{background:rgba(63,185,80,.16);color:var(--good)}
  .b-suspicious{background:rgba(210,153,34,.16);color:var(--warn)}
  .b-bot{background:rgba(248,81,73,.15);color:var(--bad)}
  .score{font-variant-numeric:tabular-nums;color:var(--muted);font-size:12px;margin-left:6px}
  .caught{font-size:11px;color:var(--muted)}
  .legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:12.5px;margin-top:10px}
  .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle}
  .funnel{display:flex;flex-direction:column;gap:8px;align-items:center}
  .stage{border:1px solid var(--line);border-radius:10px;padding:11px 14px;text-align:center;
    background:linear-gradient(180deg,var(--panel),var(--panel2))}
  .stage b{display:block;font-size:14px}
  .stage span{color:var(--muted);font-size:12.5px}
  .tl{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px}
  .tl .c{width:34px;text-align:center;border-radius:7px;padding:7px 0;font-size:11px;font-weight:700;
    border:1px solid var(--line)}
  .tl .allow{background:rgba(63,185,80,.16);color:var(--good)}
  .tl .challenge{background:rgba(210,153,34,.16);color:var(--warn)}
  .tl .deny{background:rgba(248,81,73,.16);color:var(--bad)}
  .slider{position:relative;height:42px;background:var(--panel2);border:1px solid var(--line);
    border-radius:9px;margin-top:10px;overflow:hidden}
  .slider .gap{position:absolute;top:0;height:100%;width:34px;border:2px dashed var(--warn);
    box-sizing:border-box;border-radius:8px}
  .slider .handle{position:absolute;top:0;height:100%;width:34px;background:var(--accent);
    border-radius:8px;opacity:.92}
  .kv{display:flex;gap:18px;flex-wrap:wrap;color:var(--muted);font-size:13px;margin-top:10px}
  .kv b{color:var(--ink)}
  .hof{display:grid;gap:14px;grid-template-columns:repeat(2,1fr)}
  @media(max-width:820px){.hof{grid-template-columns:1fr}}
  .hof .card h3{margin:0 0 2px;font-size:15px}
  .hof .meta{color:var(--muted);font-size:12.5px;margin-bottom:8px}
  .pill{font:600 11px system-ui;border-radius:20px;padding:2px 9px;border:1px solid var(--line);
    color:var(--muted)}
  footer{max-width:1080px;margin:0 auto;padding:24px;color:var(--muted);font-size:12.5px;
    border-top:1px solid var(--line)}
  code{color:#79c0ff;background:#0b0f14;padding:1px 5px;border-radius:5px;font-size:12.5px}
</style>
</head>
<body>
<header>
  <h1>human-click-arena <span class="by">— defense dashboard</span></h1>
  <p>A transparent behavioral bot-detection arena, layer by layer. Every number below is a real run of
     <b>selenium / seleniumbase / puppeteer / playwright</b> (stealth &amp; non-stealth) against the
     detector, plus the rate-limit and slider-puzzle defenses. Built to be broken — and to get harder.</p>
</header>
<nav><div class="in">
  <a href="#matrix">Click matrix</a>
  <a href="#defense">Defense funnel</a>
  <a href="#layers">The 6 layers</a>
  <a href="#hof">Hall of fame</a>
  <a id="repolink" href="#">GitHub ↗</a>
</div></nav>
<main>
  <section id="matrix">
    <h2>Click matrix <span class="tag" id="m-count"></span></h2>
    <p class="sub">4 engines × 3 movement strategies × {plain, stealth}. Only one combination survives.</p>
    <div id="m-strats" class="grid g3"></div>
    <div class="legend">
      <span><i class="dot" style="background:var(--good)"></i>human (≥0.5)</span>
      <span><i class="dot" style="background:var(--warn)"></i>suspicious (0.3–0.5)</span>
      <span><i class="dot" style="background:var(--bad)"></i>bot (&lt;0.3)</span>
    </div>
    <div class="card" id="m-dpr2-card" style="margin-top:16px">
      <h3 style="margin:0 0 4px;font-size:15px">HiDPI sub-pixel tell — survivors on a 2× display (humanized + stealth)</h3>
      <p class="sub" style="margin:0 0 10px">Integer-only engines get caught even with a perfect human drag.</p>
      <div id="m-dpr2"></div>
    </div>
  </section>

  <section id="defense">
    <h2>Defense funnel</h2>
    <p class="sub">Each layer removes a class of attacker cheaply. No single one is enough; the stack is.</p>
    <div class="grid g2">
      <div class="card"><div class="funnel" id="d-funnel"></div></div>
      <div class="grid" style="gap:14px">
        <div class="card">
          <h3 style="margin:0 0 2px;font-size:15px">Rate limit — the bot trips reputation.py</h3>
          <p class="sub" style="margin:0">Same client, humanized trace + solved PoW every time. Stopped by volume alone.</p>
          <div class="tl" id="d-timeline"></div>
          <div class="kv" id="d-rl-kv"></div>
        </div>
        <div class="card">
          <h3 style="margin:0 0 2px;font-size:15px">Puzzle — humanized drag solves the slider</h3>
          <div class="slider" id="d-slider"><div class="gap"></div><div class="handle"></div></div>
          <div class="kv" id="d-pz-kv"></div>
        </div>
      </div>
    </div>
  </section>

  <section id="layers">
    <h2>The 6 layers</h2>
    <p class="sub">What each layer actually checks — and its honest limit.</p>
    <div id="l-cards" class="grid g3"></div>
  </section>

  <section id="hof">
    <h2>Hall of fame <span class="tag" id="h-count"></span></h2>
    <p class="sub">Inputs that were <b>not</b> a human hand yet scored <code>human</code>. Each one made the detector harder.</p>
    <div class="hof" id="h-cards"></div>
  </section>
</main>
<footer>
  Generated <span id="gen"></span> from <code>results.json</code> + <code>defense_results.json</code> +
  <code>bypasses/</code> by <code>tools/build_dashboard.py</code>. Re-run it to refresh. MIT.
</footer>
<script>
const DATA = __DATA__;
const ENG = ["selenium","seleniumbase","puppeteer","playwright"];
const STRAT = ["native","linear","humanized"];
const el = (t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const badge = v => `<span class="badge b-${v}">${v}</span>`;
const caughtBy = r => r.navigator_webdriver===true ? "fingerprint"
  : (r.verdict!=="human" ? "behavioral" : "passes ✓");

document.getElementById("gen").textContent = DATA.generatedAt;
document.getElementById("repolink").href = "https://github.com/"+DATA.repo;
document.getElementById("m-count").textContent = DATA.results.length + " runs";

// ---- click matrix (dpr=1), one card per strategy ----------------------------
const r1 = DATA.results.filter(r=>r.dpr===1);
const mstr = document.getElementById("m-strats");
STRAT.forEach(s=>{
  const card = el("div","card");
  card.appendChild(el("h3",null,`<span style="font-size:15px">${s}</span>`)).style.margin="0 0 8px";
  let rows = "<table><tr><th>Engine</th><th>plain</th><th>stealth</th></tr>";
  ENG.forEach(e=>{
    const plain = r1.find(r=>r.engine===e&&r.strategy===s&&!r.stealth);
    const ste   = r1.find(r=>r.engine===e&&r.strategy===s&&r.stealth);
    const cell = r => r ? `${badge(r.verdict)}<span class="score">${(+r.score).toFixed(2)}</span>`
      +`<div class="caught">${caughtBy(r)}</div>` : "—";
    rows += `<tr><td class="eng">${e}</td><td>${cell(plain)}</td><td>${cell(ste)}</td></tr>`;
  });
  rows += "</table>";
  card.appendChild(el("div",null,rows));
  mstr.appendChild(card);
});

// ---- dpr=2 humanized stealth (sub-pixel) ------------------------------------
const r2 = DATA.results.filter(r=>r.dpr===2 && r.stealth && r.strategy==="humanized");
let t2 = "<table><tr><th>Engine</th><th>int_coord_ratio</th><th>Verdict</th><th>Score</th></tr>";
ENG.forEach(e=>{const r=r2.find(x=>x.engine===e);if(!r)return;
  t2+=`<tr><td class="eng">${e}</td><td>${(+r.int_coord_ratio).toFixed(3)}</td>`
    +`<td>${badge(r.verdict)}</td><td class="score">${(+r.score).toFixed(2)}</td></tr>`;});
t2+="</table>";
if(r2.length===0){ document.getElementById("m-dpr2-card").style.display="none"; }
else { document.getElementById("m-dpr2").innerHTML = t2; }

// ---- defense funnel ---------------------------------------------------------
const passes = r1.filter(r=>r.verdict==="human").length;
const finger = r1.filter(r=>r.navigator_webdriver===true).length;
const funnelData = [
  ["Fingerprint", `removes all non-stealth automation — ${finger}/${r1.length} runs → bot 0.00`],
  ["Behavioral", "removes native (no movement) & linear (straight + tween)"],
  ["Sub-pixel", "removes integer-coordinate engines on HiDPI"],
  ["Proof-of-work", "taxes every attempt with CPU cost"],
  ["Rate / reputation", "blocks the repeat offender by volume"],
  ["Puzzle", `the last ${passes} survivors must solve a live drag`],
];
const fEl = document.getElementById("d-funnel");
funnelData.forEach((s,i)=>{
  const w = 100 - i*11;
  const d = el("div","stage",`<b>${s[0]}</b><span>${s[1]}</span>`);
  d.style.width = w+"%"; fEl.appendChild(d);
});

// ---- rate-limit timeline ----------------------------------------------------
const rl = (DATA.defense&&DATA.defense.rate_limit)||{};
const tl = document.getElementById("d-timeline");
(rl.timeline||[]).forEach(r=>{
  const cls = r.decision==="allow"?"allow":(r.decision==="challenge"?"challenge":"deny");
  tl.appendChild(el("div","c "+cls, r.i));
});
const lastRL = (rl.timeline||[]).slice(-1)[0]||{};
document.getElementById("d-rl-kv").innerHTML =
  `<span>allow → challenge → <b style="color:var(--bad)">blocked</b></span>`
  +`<span>stopped at request <b>#${lastRL.i||"?"}</b></span>`
  +`<span>state: <b>${lastRL.state||"?"}</b></span>`;

// ---- puzzle slider ----------------------------------------------------------
const pz = (DATA.defense&&DATA.defense.puzzle)||{};
if(pz.target!=null){
  const slider = document.getElementById("d-slider");
  const w = slider.clientWidth||520;
  slider.querySelector(".gap").style.left = (pz.target*(w-34))+"px";
  slider.querySelector(".handle").style.left = (pz.released*(w-34))+"px";
  document.getElementById("d-pz-kv").innerHTML =
    `<span>target <b>${(+pz.target).toFixed(3)}</b></span>`
    +`<span>released <b>${(+pz.released).toFixed(3)}</b></span>`
    +`<span>error <b>${(+pz.align_error).toFixed(4)}</b> (tol ${pz.tol})</span>`
    +`<span>${pz.solved?badge("human").replace("human","solved ✓"):badge("bot")}</span>`;
}

// ---- layers -----------------------------------------------------------------
const lc = document.getElementById("l-cards");
DATA.layers.forEach((L,i)=>{
  lc.appendChild(el("div","card",
    `<h3 style="margin:0 0 6px;font-size:15px">${i+1}. ${L.name}`
    +` <span class="pill">${L.where}</span></h3>`
    +`<div style="font-size:13.5px">Checks ${L.checks}.</div>`
    +`<div class="sub" style="margin:8px 0 0">${L.note}</div>`));
});

// ---- hall of fame -----------------------------------------------------------
const hof = [];
// submitted bypasses
(DATA.bypasses||[]).forEach(b=>hof.push({
  title:b.name, who:b.handle, date:b.date, tool:b.tool, score:b.score,
  verdict:b.verdict, status:b.status, link:b.md, source:"bypasses/"}));
// the harness runs that beat a layer (stealth + humanized = human)
r1.filter(r=>r.verdict==="human").forEach(r=>hof.push({
  title:`${r.engine} — humanized + stealth`, who:"harness", date:DATA.generatedAt.split(" ")[0],
  tool:`${r.engine} (${r.stealth_lib||"stealth"})`, score:r.score, verdict:r.verdict,
  status:"beats behavioral layer", link:null, source:"run_all.py"}));
if(pz.solved) hof.push({title:"slider puzzle solved", who:"harness",
  date:DATA.generatedAt.split(" ")[0], tool:"humanized drag (playwright)", score:null,
  verdict:"human", status:"beats puzzle layer", link:null, source:"run_defense.py"});

document.getElementById("h-count").textContent = hof.length + " entries";
const hc = document.getElementById("h-cards");
hof.forEach(b=>{
  const score = b.score!=null ? `<span class="score">score ${(+b.score).toFixed(2)}</span>` : "";
  const link = b.link ? ` · <a href="https://github.com/${DATA.repo}/blob/main/${b.link}">writeup ↗</a>` : "";
  hc.appendChild(el("div","card",
    `<h3>${b.title} ${badge(b.verdict)} ${score}</h3>`
    +`<div class="meta">by <b>${b.who||"?"}</b> · ${b.date||""} · <span class="pill">${b.source}</span></div>`
    +`<div style="font-size:13px">${b.tool||""}</div>`
    +`<div class="sub" style="margin:6px 0 0">${b.status}${link}</div>`));
});
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
