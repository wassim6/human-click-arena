/* human-click-arena — pointer trace collector.
 *
 * Records pointermove / pointerdown / pointerup into a trace that matches the
 * format the Python scorer expects:
 *   { events: [{type, x, y, t}], target: {x, y, r} }
 * Timestamps `t` are milliseconds from the first recorded event.
 *
 * This is the part you are welcome to read, fake, or replay. Have fun.
 */
(function (global) {
  "use strict";

  class TraceCollector {
    constructor() {
      this.reset();
    }

    reset() {
      this.events = [];
      this._t0 = null;
      this._lastNow = null;
      this.target = null;
      // A gap longer than this between moves starts a fresh gesture, so the
      // trace never accumulates minutes of unrelated wandering before a click.
      this.idleResetMs = 1000;
      return this;
    }

    _stamp(type, x, y) {
      const now = performance.now();
      if (type === "move" && this._lastNow !== null &&
          now - this._lastNow > this.idleResetMs) {
        this.events = [];          // long idle => new gesture
        this._t0 = null;
      }
      if (this._t0 === null) this._t0 = now;
      this._lastNow = now;
      this.events.push({
        type: type,
        x: Math.round(x * 100) / 100,
        y: Math.round(y * 100) / 100,
        t: Math.round((now - this._t0) * 100) / 100,
      });
    }

    /** Public: explicitly record an event (used to capture the click release,
     *  which can be missed when listeners are detached during event bubbling). */
    mark(type, x, y) {
      this._stamp(type, x, y);
      return this;
    }

    /** Begin recording over `el`. `target` = {x, y, r} the user must click. */
    attach(el, target) {
      this.reset();
      this.target = target || null;
      this._el = el;
      this._onMove = (e) => this._stamp("move", e.clientX, e.clientY);
      this._onDown = (e) => this._stamp("down", e.clientX, e.clientY);
      this._onUp = (e) => this._stamp("up", e.clientX, e.clientY);
      el.addEventListener("pointermove", this._onMove, { passive: true });
      el.addEventListener("pointerdown", this._onDown, { passive: true });
      el.addEventListener("pointerup", this._onUp, { passive: true });
      return this;
    }

    detach() {
      if (!this._el) return this;
      this._el.removeEventListener("pointermove", this._onMove);
      this._el.removeEventListener("pointerdown", this._onDown);
      this._el.removeEventListener("pointerup", this._onUp);
      this._el = null;
      return this;
    }

    /** Snapshot of the trace as a plain object (safe to JSON.stringify).
     *  `meta.dpr` lets the scorer use sub-pixel coordinates as a strong signal:
     *  on a HiDPI display (dpr > 1) real pointers report fractional pixels,
     *  while OS injectors (pyautogui) move to whole pixels only. */
    trace() {
      return {
        events: this.events.slice(),
        target: this.target,
        meta: {
          dpr: (typeof window !== "undefined" && window.devicePixelRatio) || 1,
          ua: (typeof navigator !== "undefined" && navigator.userAgent) || "",
          // Trivial automation tell: real browsers report false/undefined; a
          // WebDriver-controlled browser reports true (unless a stealth plugin
          // resets it). Only `true` is informative — false proves nothing.
          webdriver: (typeof navigator !== "undefined" && navigator.webdriver === true),
        },
      };
    }

    /** POST the trace to the scorer and resolve with the JSON result. */
    async score(endpoint) {
      const res = await fetch(endpoint || "/score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(this.trace()),
      });
      return res.json();
    }
  }

  global.TraceCollector = TraceCollector;
})(typeof window !== "undefined" ? window : this);
