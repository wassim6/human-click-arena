"""Build the static arena dashboard at docs/index.html (for GitHub Pages).

Reads:
    attacks/browser/results.json          (the click matrix, dpr=1)
    attacks/browser/results_hidpi.json    (the dpr=2 cross-section, optional)
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
    {"icon": "🪪", "name": "Fingerprint", "where": "scorer.py",
     "desc": "Reads the browser's own <code>navigator.webdriver</code> flag.",
     "thresh": "flag = true → instant bot"},
    {"icon": "✋", "name": "Behavioral", "where": "scorer.py",
     "desc": "Judges the <em>shape</em> of the motion — curves, timing, tremor, corrections.",
     "thresh": "human ≥ 0.50 · bot < 0.30"},
    {"icon": "🔬", "name": "Sub-pixel", "where": "scorer.py",
     "desc": "On a Retina screen, real pointers land between pixels; injectors don't.",
     "thresh": "dpr > 1 + all-integer → capped 0.22"},
    {"icon": "⛏️", "name": "Proof-of-work", "where": "pow.py",
     "desc": "Every request must burn a little CPU first. Cheap once, costly at scale.",
     "thresh": "SHA-256, 14–18 zero bits"},
    {"icon": "📊", "name": "Rate limit", "where": "reputation.py",
     "desc": "Counts how often one client knocks. Volume is what a bot can't hide.",
     "thresh": "> 3 / 5 min → challenge · > 10 / 30 min → ban"},
    {"icon": "🧩", "name": "Puzzle", "where": "puzzle.py",
     "desc": "A slide-to-fit drag when things look borderline.",
     "thresh": "align ≤ 6% + a real, live drag"},
]

TECHNIQUE = {
    "playwright": "curved Bézier path + jitter + overshoot, webdriver hidden by playwright-stealth",
    "puppeteer": "real ghost-cursor human movement + puppeteer-extra-stealth",
    "selenium": "humanized chained pointer moves + selenium-stealth",
    "seleniumbase": "UC (undetected) mode + a humanized drag",
}


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

        score = g(r"score:\s*([0-9.]+)")
        out.append({
            "name": g(r"#\s*Bypass:\s*(.+)") or base,
            "handle": g(r"\*\*Handle:\*\*\s*(.+)"),
            "date": g(r"\*\*Date:\*\*\s*(.+)"),
            "tool": g(r"\*\*Tool\s*/\s*stack:\*\*\s*(.+)"),
            "score": float(score) if score else None,
            "verdict": g(r"verdict:\s*(\w+)") or "human",
            "status": g(r"##\s*Status:\s*(.+)") or "accepted",
            "md": "bypasses/" + base,
        })
    return out


def main():
    results = json.load(open(os.path.join(BROWSER, "results.json")))
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
        "technique": TECHNIQUE,
        "bypasses": parse_bypasses(),
    }

    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    out_dir = os.path.join(ROOT, "docs")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    print("wrote docs/index.html  (" + str(len(html)) + " bytes, "
          + str(len(results)) + " runs, " + str(len(data["bypasses"])) + " bypasses)")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>human-click-arena — can a bot fake a human click?</title>
<style>
  :root{
    --bg:#0f1320;--panel:#171c2b;--panel2:#10131f;--line:#262d3f;--ink:#eef2f8;
    --muted:#9aa6bd;--accent:#4f8cff;--good:#46d17e;--bad:#ff6b6b;--warn:#f0b429;
    --gold:#ffd35c;--silver:#cdd6e6;--bronze:#e3a06b;
  }
  *{box-sizing:border-box}
  body{margin:0;background:radial-gradient(1200px 600px at 50% -200px,#1b2235,var(--bg));
    color:var(--ink);font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
  a{color:var(--accent);text-decoration:none}
  .wrap{max-width:960px;margin:0 auto;padding:0 22px}
  header{text-align:center;padding:54px 22px 18px}
  h1{margin:0;font-size:34px;letter-spacing:-.5px}
  header .tag{display:inline-block;margin:14px 0 0;color:var(--muted);font-size:17px;max-width:60ch}
  header .links{margin-top:16px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
  .btn{background:var(--panel);border:1px solid var(--line);border-radius:999px;
    padding:7px 16px;color:var(--ink);font-weight:600;font-size:14px}
  .btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
  section{margin:40px 0}
  h2{font-size:23px;margin:0 0 4px;text-align:center}
  .lead{color:var(--muted);text-align:center;margin:0 auto 22px;max-width:62ch}
  .stats{display:flex;gap:14px;justify-content:center;flex-wrap:wrap}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px 22px;
    text-align:center;min-width:120px}
  .stat b{display:block;font-size:30px;line-height:1}
  .stat span{color:var(--muted);font-size:13px}
  .podium{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;align-items:end}
  @media(max-width:760px){.podium{grid-template-columns:1fr}}
  .win{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:20px;
    text-align:center;position:relative}
  .win .medal{font-size:34px}
  .win .eng{font-size:20px;font-weight:700;margin:6px 0 2px;text-transform:capitalize}
  .win .how{color:var(--muted);font-size:13px;min-height:3.2em}
  .win .sc{font-size:38px;font-weight:800;margin-top:8px;font-variant-numeric:tabular-nums}
  .win .vd{color:var(--good);font-weight:700;font-size:13px}
  .win.r1{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold) inset;transform:translateY(-8px)}
  .win.r1 .sc{color:var(--gold)} .win.r2 .sc{color:var(--silver)} .win.r3 .sc{color:var(--bronze)}
  .pass{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:10px}
  .tagpill{background:rgba(70,209,126,.12);border:1px solid rgba(70,209,126,.35);color:var(--good);
    border-radius:999px;padding:6px 14px;font-weight:600;font-size:14px;text-transform:capitalize}
  .fails{display:grid;gap:14px}
  .failcard{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px 18px}
  .failcard h3{margin:0 0 2px;font-size:16px;display:flex;align-items:center;gap:9px}
  .failcard .why{color:var(--muted);font-size:13.5px;margin:0 0 12px}
  .row{display:flex;align-items:flex-start;gap:12px;padding:9px 0;border-top:1px solid var(--line)}
  .row .lbl{min-width:210px;font-weight:600;font-size:14px;text-transform:capitalize}
  .row .lbl small{display:block;color:var(--muted);font-weight:400;font-size:12px;text-transform:none}
  .row .reason{color:var(--muted);font-size:13px;flex:1}
  .badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}
  .b-human{background:rgba(70,209,126,.16);color:var(--good)}
  .b-suspicious{background:rgba(240,180,41,.16);color:var(--warn)}
  .b-bot{background:rgba(255,107,107,.15);color:var(--bad)}
  .sc-sm{color:var(--muted);font-variant-numeric:tabular-nums;font-size:12px;margin-left:4px}
  .chips{display:flex;gap:8px;flex-wrap:wrap}
  .chip{background:var(--panel2);border:1px solid var(--line);border-radius:999px;padding:4px 11px;
    font-size:12.5px;text-transform:capitalize}
  .layers{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
  @media(max-width:760px){.layers{grid-template-columns:1fr}}
  .layer{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px}
  .layer .ic{font-size:24px} .layer h3{margin:6px 0 4px;font-size:16px}
  .layer p{margin:0;color:var(--muted);font-size:13.5px}
  .layer .th{margin-top:9px;display:inline-block;background:var(--panel2);border:1px solid var(--line);
    border-radius:8px;padding:3px 9px;font-size:12px;color:var(--ink)}
  .two{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  @media(max-width:760px){.two{grid-template-columns:1fr}}
  .res{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px}
  .res h3{margin:0 0 8px;font-size:16px}
  .tl{display:flex;gap:4px;flex-wrap:wrap}
  .tl .c{width:30px;text-align:center;border-radius:7px;padding:6px 0;font-size:11px;font-weight:700;border:1px solid var(--line)}
  .tl .allow{background:rgba(70,209,126,.16);color:var(--good)}
  .tl .challenge{background:rgba(240,180,41,.16);color:var(--warn)}
  .tl .deny{background:rgba(255,107,107,.16);color:var(--bad)}
  .slider{position:relative;height:40px;background:var(--panel2);border:1px solid var(--line);
    border-radius:9px;margin:8px 0;overflow:hidden}
  .slider .gap{position:absolute;top:0;height:100%;width:30px;border:2px dashed var(--warn);
    box-sizing:border-box;border-radius:8px}
  .slider .handle{position:absolute;top:0;height:100%;width:30px;background:var(--accent);border-radius:8px}
  .muted{color:var(--muted);font-size:13px}
  .hof{display:grid;gap:14px;grid-template-columns:1fr 1fr}
  @media(max-width:760px){.hof{grid-template-columns:1fr}}
  .hof .layer h3{font-size:15px;margin:0 0 2px}
  details{margin-top:14px}
  details summary{cursor:pointer;color:var(--muted);font-weight:600;text-align:center}
  table{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}
  th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}
  th{color:var(--muted);font-size:11px;text-transform:uppercase}
  footer{text-align:center;color:var(--muted);font-size:13px;padding:30px 22px;border-top:1px solid var(--line);margin-top:40px}
  code{color:#9ec5ff;background:#0b0f1a;padding:1px 5px;border-radius:5px;font-size:13px}
</style>
</head>
<body>
<header>
  <h1>🖱️ human-click-arena</h1>
  <div class="tag">Can a bot fake a human click? We pit <b>selenium, seleniumbase, puppeteer &amp; playwright</b>
    against the detector — and show exactly who gets through and who gets caught.</div>
  <div class="links">
    <a class="btn primary" href="#top">🏆 Top attacks</a>
    <a class="btn" href="#caught">❌ Who got caught</a>
    <a class="btn" href="#defenses">🛡️ Defenses</a>
    <a class="btn" id="repolink" href="#">GitHub ↗</a>
  </div>
</header>
<div class="wrap">

  <section id="stats"><div class="stats" id="statrow"></div></section>

  <section id="top">
    <h2>🏆 Top 3 attacks</h2>
    <p class="lead">The three runs that most convincingly fooled the behavioral scorer. All of them needed
       <b>both</b> a humanized motion <b>and</b> a stealth plugin to hide the webdriver flag.</p>
    <div class="podium" id="podium"></div>
    <p class="lead" style="margin-top:22px">Everyone who got through (verdict <b>human</b>):</p>
    <div class="pass" id="passers"></div>
  </section>

  <section id="caught">
    <h2>❌ Who got caught — and why</h2>
    <p class="lead">Most attacks fail. Here's each one, grouped by what gave it away, with the detector's own reason.</p>
    <div class="fails" id="failgroups"></div>
  </section>

  <section id="defenses">
    <h2>🛡️ The 6 defenses</h2>
    <p class="lead">Each layer removes a kind of attacker cheaply. Together they form a funnel.</p>
    <div class="layers" id="layercards"></div>
    <div class="two" style="margin-top:16px">
      <div class="res">
        <h3>📊 Rate limit — caught by volume</h3>
        <p class="muted" style="margin:0 0 8px">A bot that passes <em>every</em> check still gets stopped if it repeats. Same client, over and over:</p>
        <div class="tl" id="d-timeline"></div>
        <p class="muted" id="d-rl"></p>
      </div>
      <div class="res">
        <h3>🧩 Puzzle — the bot solved it</h3>
        <p class="muted" style="margin:0">A humanized drag slides the handle into the gap:</p>
        <div class="slider" id="d-slider"><div class="gap"></div><div class="handle"></div></div>
        <p class="muted" id="d-pz"></p>
      </div>
    </div>
  </section>

  <section id="hof">
    <h2>🏅 Hall of fame</h2>
    <p class="lead">Attacks that beat a layer — kept as permanent regression tests. Add yours via a PR.</p>
    <div class="hof" id="hofcards"></div>
  </section>

  <details>
    <summary>See the full results table (all runs)</summary>
    <div id="fulltable"></div>
  </details>
</div>
<footer>
  Built from real runs by <code>tools/build_dashboard.py</code> · generated <span id="gen"></span> ·
  <a id="repolink2" href="#">github.com/wassim6/human-click-arena</a>
</footer>
<script>
const DATA=__DATA__;
const ENG=["selenium","seleniumbase","puppeteer","playwright"];
const el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const badge=v=>`<span class="badge b-${v}">${v}</span>`;
const fx=(v,d=2)=>v==null?"—":(+v).toFixed(d);
const cap=s=>s.charAt(0).toUpperCase()+s.slice(1);
const mode=r=>r.stealth?"stealth":"plain";
const label=r=>`${cap(r.engine)} · ${r.strategy}${r.dpr===2?" · 2× display":""}`;
document.getElementById("gen").textContent=DATA.generatedAt;
document.getElementById("repolink").href=document.getElementById("repolink2").href="https://github.com/"+DATA.repo;

const all=DATA.results;
const r1=all.filter(r=>r.dpr===1);

// ---- stats ------------------------------------------------------------------
const passed=r1.filter(r=>r.verdict==="human");
const stats=[
  [all.length,"attacks run"],
  [passed.length,"got through"],
  [r1.length-passed.length,"caught (dpr 1)"],
  ["6","defense layers"],
];
const sr=document.getElementById("statrow");
stats.forEach(s=>sr.appendChild(el("div","stat",`<b>${s[0]}</b><span>${s[1]}</span>`)));

// ---- top 3 ------------------------------------------------------------------
const winners=all.filter(r=>r.verdict==="human").sort((a,b)=>b.score-a.score);
const top3=[];const seen=new Set();
for(const w of winners){const k=w.engine;if(seen.has(k))continue;seen.add(k);top3.push(w);if(top3.length===3)break;}
const medals=["🥇","🥈","🥉"];
const pod=document.getElementById("podium");
top3.forEach((w,i)=>{
  pod.appendChild(el("div","win r"+(i+1),
    `<div class="medal">${medals[i]}</div>`
    +`<div class="eng">${w.engine}</div>`
    +`<div class="how">${DATA.technique[w.engine]||"humanized + stealth"}</div>`
    +`<div class="sc">${fx(w.score)}</div><div class="vd">verdict: human ✓</div>`));
});
const passEl=document.getElementById("passers");
[...new Set(passed.map(r=>r.engine))].forEach(e=>passEl.appendChild(el("span","tagpill",e)));

// ---- caught, grouped by what gave it away -----------------------------------
function reasonClass(r){
  if(r.navigator_webdriver===true) return "fingerprint";
  if(r.dpr>1 && (r.int_coord_ratio||0)>=0.98) return "subpixel";
  return "behavioral";
}
const GROUPS={
  fingerprint:{icon:"🪪",title:"The browser admitted it was a robot",
    why:"<code>navigator.webdriver</code> was <b>true</b> — every non-stealth run is caught here for free, no matter how good the mouse motion was."},
  behavioral:{icon:"✋",title:"The movement gave it away",
    why:"Stealth hid the flag, so these fell through to the motion scorer — a straight line, a clean easing curve, or no movement at all."},
  subpixel:{icon:"🔬",title:"Whole-pixel coordinates on a Retina screen",
    why:"On a 2× display real pointers report fractional pixels. Selenium &amp; seleniumbase use the integer-only W3C Actions API, so they're caught even with a perfect human drag."},
};
const caught=all.filter(r=>r.verdict!=="human");
const byGroup={fingerprint:[],behavioral:[],subpixel:[]};
caught.forEach(r=>byGroup[reasonClass(r)].push(r));
const fg=document.getElementById("failgroups");
["behavioral","subpixel","fingerprint"].forEach(key=>{
  const list=byGroup[key];if(!list.length)return;
  const g=GROUPS[key];
  const card=el("div","failcard",`<h3>${g.icon} ${g.title} <span class="muted">· ${list.length} runs</span></h3><p class="why">${g.why}</p>`);
  if(key==="fingerprint"){
    // identical reason -> just chip the runs
    const chips=el("div","chips");
    list.forEach(r=>chips.appendChild(el("span","chip",`${r.engine} · ${r.strategy}`)));
    card.appendChild(chips);
  }else{
    list.sort((a,b)=>a.engine.localeCompare(b.engine));
    list.forEach(r=>{
      card.appendChild(el("div","row",
        `<div class="lbl">${cap(r.engine)} ${badge(r.verdict)}<span class="sc-sm">${fx(r.score)}</span>`
        +`<small>${r.strategy} · ${mode(r)}${r.dpr===2?" · 2×":""}</small></div>`
        +`<div class="reason">${r.reason||""}</div>`));
    });
  }
  fg.appendChild(card);
});

// ---- layers -----------------------------------------------------------------
const lc=document.getElementById("layercards");
DATA.layers.forEach((L,i)=>lc.appendChild(el("div","layer",
  `<div class="ic">${L.icon}</div><h3>${i+1}. ${L.name}</h3><p>${L.desc}</p>`
  +`<span class="th">${L.thresh}</span>`)));

// ---- rate limit + puzzle ----------------------------------------------------
const rl=(DATA.defense&&DATA.defense.rate_limit)||{};
const tl=document.getElementById("d-timeline");
(rl.timeline||[]).forEach(r=>{
  const cls=r.decision==="allow"?"allow":(r.decision==="challenge"?"challenge":"deny");
  const c=el("div","c "+cls,r.i);c.title=`#${r.i} · ${r.decision}\n${r.reason||""}`;tl.appendChild(c);
});
const tlast=(rl.timeline||[]).slice(-1)[0]||{};
document.getElementById("d-rl").innerHTML=
  `<span style="color:var(--good)">allow</span> → <span style="color:var(--warn)">challenge</span> → `
  +`<span style="color:var(--bad)">blocked</span> at request <b>#${tlast.i||"?"}</b>.`;
const pz=(DATA.defense&&DATA.defense.puzzle)||{};
if(pz.target!=null){
  const sl=document.getElementById("d-slider");const w=520;
  sl.querySelector(".gap").style.left=(pz.target*(w-30))+"px";
  sl.querySelector(".handle").style.left=(pz.released*(w-30))+"px";
  document.getElementById("d-pz").innerHTML=
    `Target ${fx(pz.target,3)}, landed ${fx(pz.released,3)} (off by ${fx(pz.align_error,4)}). `
    +(pz.solved?'<b style="color:var(--good)">Solved ✓</b>':'<b style="color:var(--bad)">Failed</b>');
}

// ---- hall of fame -----------------------------------------------------------
const hof=[];
(DATA.bypasses||[]).forEach(b=>hof.push({title:b.name,who:b.handle,tool:b.tool,score:b.score,
  verdict:b.verdict,status:b.status,link:b.md}));
[...new Set(passed.map(r=>r.engine))].forEach(e=>{
  const r=passed.filter(x=>x.engine===e).sort((a,b)=>b.score-a.score)[0];
  hof.push({title:`${cap(e)} fools the scorer`,who:"harness",tool:DATA.technique[e],
    score:r.score,verdict:"human",status:"beats the behavioral layer",link:null});
});
if(pz.solved)hof.push({title:"Slider puzzle solved",who:"harness",tool:"humanized drag (playwright)",
  score:null,verdict:"human",status:"beats the puzzle layer",link:null});
const hc=document.getElementById("hofcards");
hof.forEach(b=>{
  const sc=b.score!=null?`<span class="sc-sm">score ${fx(b.score)}</span>`:"";
  const link=b.link?` · <a href="https://github.com/${DATA.repo}/blob/main/${b.link}">writeup ↗</a>`:"";
  hc.appendChild(el("div","layer",
    `<h3>${b.title} ${badge(b.verdict)} ${sc}</h3>`
    +`<p style="margin:4px 0 0">${b.tool||""}</p>`
    +`<p class="muted" style="margin:6px 0 0">by <b>${b.who}</b> · ${b.status}${link}</p>`));
});

// ---- full table -------------------------------------------------------------
let tb="<table><tr><th>Engine</th><th>Strategy</th><th>Mode</th><th>dpr</th><th>Verdict</th><th>Score</th></tr>";
all.slice().sort((a,b)=>(a.engine+a.strategy).localeCompare(b.engine+b.strategy)).forEach(r=>{
  tb+=`<tr><td>${cap(r.engine)}</td><td>${r.strategy}</td><td>${mode(r)}</td><td>${r.dpr}</td>`
    +`<td>${badge(r.verdict)}</td><td>${fx(r.score)}</td></tr>`;});
document.getElementById("fulltable").innerHTML=tb+"</table>";
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
