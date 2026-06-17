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
      this.target = null;
      return this;
    }

    _stamp(type, x, y) {
      const now = performance.now();
      if (this._t0 === null) this._t0 = now;
      this.events.push({
        type: type,
        x: Math.round(x * 100) / 100,
        y: Math.round(y * 100) / 100,
        t: Math.round((now - this._t0) * 100) / 100,
      });
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

    /** Snapshot of the trace as a plain object (safe to JSON.stringify). */
    trace() {
      return { events: this.events.slice(), target: this.target };
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
