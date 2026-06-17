/* Proof-of-work client: fetch a challenge, grind a nonce, return the solution.
 *
 * Default algorithm is Argon2id (memory-hard) via hash-wasm; this is the cost
 * the attacker pays per attempt and it resists GPUs/ASICs. If hash-wasm isn't
 * loaded — or its Argon2 output doesn't match the server (verified once via a
 * self-check) — it transparently falls back to SHA-256 (sha256.js), so the demo
 * can never silently deny everyone.
 */
(function (global) {
  "use strict";

  async function fetchChallenge(opts) {
    const q = [];
    if (opts && opts.bits) q.push("bits=" + opts.bits);
    if (opts && opts.alg) q.push("alg=" + opts.alg);
    const url = "/pow/challenge" + (q.length ? "?" + q.join("&") : "");
    return (await fetch(url)).json();
  }

  let _argonOk = null;        // null = unknown, then true/false (cached)

  async function argonWorks() {
    if (_argonOk !== null) return _argonOk;
    if (typeof hashwasm === "undefined" || !hashwasm.argon2id) { _argonOk = false; return false; }
    try {
      const salt = "selfcheck", nonce = "1", m = 8192, t = 2, p = 1;
      const local = await hashwasm.argon2id({
        password: nonce, salt: new TextEncoder().encode(salt),
        parallelism: p, iterations: t, memorySize: m, hashLength: 32, outputType: "hex",
      });
      const r = await (await fetch(
        `/pow/echo?alg=argon2id&salt=${salt}&nonce=${nonce}&m=${m}&t=${t}&p=${p}`)).json();
      _argonOk = (r.hex === local);
    } catch (e) { _argonOk = false; }
    return _argonOk;
  }

  async function digest(ch, nonce) {
    if (ch.alg === "argon2id") {
      return hashwasm.argon2id({
        password: String(nonce), salt: new TextEncoder().encode(ch.salt),
        parallelism: ch.p, iterations: ch.t, memorySize: ch.m, hashLength: 32,
        outputType: "binary",
      });
    }
    return sha256.bytes(ch.salt + "." + nonce);   // synchronous
  }

  async function solveChallenge(ch) {
    let nonce = 0;
    for (;;) {
      const d = await digest(ch, nonce);
      if (sha256.leadingZeroBits(d) >= ch.difficulty) return nonce;
      nonce++;
    }
  }

  async function obtain(bits) {
    const started = performance.now();
    const useArgon = await argonWorks();
    let ch = await fetchChallenge({ bits: bits, alg: useArgon ? undefined : "sha256" });
    if (ch.alg === "argon2id" && !useArgon) {        // server defaulted to argon2 but we can't
      ch = await fetchChallenge({ bits: bits, alg: "sha256" });
    }
    const nonce = await solveChallenge(ch);
    return {
      salt: ch.salt, alg: ch.alg, difficulty: ch.difficulty,
      m: ch.m, t: ch.t, p: ch.p, ts: ch.ts, sig: ch.sig,
      nonce: String(nonce), _ms: Math.round(performance.now() - started),
    };
  }

  global.pow = { fetchChallenge: fetchChallenge, solveChallenge: solveChallenge, obtain: obtain };
})(typeof window !== "undefined" ? window : globalThis);
