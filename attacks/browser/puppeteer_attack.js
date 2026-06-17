/* Drive the harness with Puppeteer and score the resulting click.
 *
 * Usage:
 *   node puppeteer_attack.js --strategy native|linear|humanized \
 *       [--stealth] [--dpr 1] [--url http://127.0.0.1:5001] [--save DIR]
 *
 * Strategies:
 *   native     -> page.click(target): one hop + click (what most scrapers do).
 *   linear     -> page.mouse.move(target,{steps}): straight, evenly-timed glide.
 *   humanized  -> ghost-cursor: real human-like Bezier movement library.
 *
 * --stealth uses puppeteer-extra + puppeteer-extra-plugin-stealth (patches
 * navigator.webdriver, chrome.runtime, WebGL vendor, etc.). It does NOT change
 * pointer trajectories, so the behavioral score should match the plain run.
 *
 * The Chromium binary is taken from $CHROME_PATH (a shared Playwright build here).
 */
"use strict";

function arg(name, def) {
  const i = process.argv.indexOf("--" + name);
  if (i === -1) return def;
  const v = process.argv[i + 1];
  return v && !v.startsWith("--") ? v : true;
}

const STRATEGY = arg("strategy", "native");
const STEALTH = process.argv.includes("--stealth");
// --headed shows a real window; --slowmo N adds N ms before each devtools action
// so you can watch the cursor. slowmo inflates timing features but does NOT
// affect the int_coord_ratio / sub-pixel tell.
const HEADED = process.argv.includes("--headed");
const SLOWMO = parseInt(arg("slowmo", "0"), 10) || 0;
const DPR = parseFloat(arg("dpr", "1"));
const URL = arg("url", "http://127.0.0.1:5001");
const SAVE = arg("save", "");
const EXEC = process.env.CHROME_PATH ||
  require("path").join(process.env.HOME,
    ".cache/ms-playwright/chromium-1223/chrome-linux/chrome");

const START = { x: 140, y: 170 };

function getPuppeteer() {
  if (STEALTH) {
    const { addExtra } = require("puppeteer-extra");
    const pptr = addExtra(require("puppeteer-core"));
    pptr.use(require("puppeteer-extra-plugin-stealth")());
    return { pptr, lib: "puppeteer-extra-stealth" };
  }
  return { pptr: require("puppeteer-core"), lib: "off" };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const { pptr, lib } = getPuppeteer();
  const launchArgs = ["--no-sandbox", "--window-size=1200,760"];
  if (!HEADED) launchArgs.push("--disable-gpu");  // GPU off only matters headless
  const browser = await pptr.launch({
    headless: HEADED ? false : "new", executablePath: EXEC,
    slowMo: SLOWMO,
    args: launchArgs,
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 760, deviceScaleFactor: DPR });
  await page.goto(URL, { waitUntil: "load" });
  await page.waitForFunction("window.__HCA_READY === true");
  const webdriver = await page.evaluate(() => navigator.webdriver);

  const spec = await page.evaluate(() => window.HCA.setup(840, 520));
  const tx = spec.x, ty = spec.y;

  if (STRATEGY === "native") {
    await page.click("#target");
  } else if (STRATEGY === "linear") {
    await page.mouse.move(START.x, START.y);
    await sleep(50);
    await page.mouse.move(tx, ty, { steps: 28 });
    await page.mouse.down();
    await sleep(50);
    await page.mouse.up();
  } else if (STRATEGY === "humanized") {
    const { createCursor } = require("ghost-cursor");
    const cursor = createCursor(page, START);
    await cursor.move("#target", { moveDelay: 30, randomizeMoveDelay: true });
    await cursor.click("#target");
  }

  await page.evaluate(([x, y]) => window.HCA.mark("up", x, y), [tx, ty]);
  const trace = await page.evaluate(() => window.HCA.trace());
  await browser.close();

  const res = await fetch(URL + "/score", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(trace),
  }).then((r) => r.json());

  const out = {
    engine: "puppeteer", stealth: STEALTH, stealth_lib: lib, strategy: STRATEGY,
    dpr: DPR, navigator_webdriver: webdriver, verdict: res.verdict, score: res.score,
    subscores: res.subscores || {},
    n_move_events: res.features.n_move_events, directness: res.features.directness,
    easing_r2: res.features.easing_r2, dt_cv: res.features.dt_cv,
    int_coord_ratio: res.features.int_coord_ratio, reason: res.reason || "",
  };
  console.log(JSON.stringify(out));

  if (SAVE) {
    const fs = require("fs"), path = require("path");
    fs.mkdirSync(SAVE, { recursive: true });
    const tag = `puppeteer_${STRATEGY}_${STEALTH ? "stealth" : "plain"}_dpr${DPR}`;
    fs.writeFileSync(path.join(SAVE, tag + ".json"), JSON.stringify(trace, null, 1));
  }
}

main().catch((e) => { console.error("ERR", e.message); process.exit(1); });
