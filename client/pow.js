/* Proof-of-work client: fetch a challenge, grind a nonce, return the solution.
 * Depends on sha256.js. The server verifies the result statelessly.
 *
 * This is the cost the attacker pays per attempt. One click = a few thousand
 * hashes (sub-second). A million clicks = a million times that.
 */
(function (global) {
  "use strict";

  async function fetchChallenge(bits) {
    const url = "/pow/challenge" + (bits ? "?bits=" + bits : "");
    const res = await fetch(url);
    return res.json();
  }

  function solve(challenge) {
    const salt = challenge.salt;
    const difficulty = challenge.difficulty;
    let nonce = 0;
    for (;;) {
      const d = sha256.bytes(salt + "." + nonce);
      if (sha256.leadingZeroBits(d) >= difficulty) return nonce;
      nonce++;
    }
  }

  async function obtain(bits) {
    const started = performance.now();
    const challenge = await fetchChallenge(bits);
    const nonce = solve(challenge);
    return {
      salt: challenge.salt,
      difficulty: challenge.difficulty,
      ts: challenge.ts,
      sig: challenge.sig,
      nonce: String(nonce),
      _ms: Math.round(performance.now() - started),
    };
  }

  global.pow = { fetchChallenge: fetchChallenge, solve: solve, obtain: obtain };
})(typeof window !== "undefined" ? window : globalThis);
