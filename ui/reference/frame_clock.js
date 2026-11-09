/* Reference-viewport HiM frame pacing. Each new progress value is selected
 * only after Fusion has finished computing the preceding frame. */
(function (root) {
  "use strict";
  function initialFrames(durationMs) {
    const seconds = Math.max(2, Math.min(10, durationMs / 1000));
    return Math.round(15 + (seconds - 2) * (60 / 8));
  }
  class HiMFrameClock {
    constructor(durationMs, travelledMs = 0) {
      if (!Number.isFinite(durationMs) || durationMs <= 0) throw new RangeError("Invalid feature duration");
      this.duration = durationMs;
      this.travelled = Math.max(0, Math.min(durationMs, travelledMs));
      this.wall = this.travelled;
      this.initialStep = durationMs / initialFrames(durationMs);
    }
    tick(dtMs, speed = 1) {
      this.wall += Math.max(0, dtMs) * speed;
    }
    completed(frameMs, speed = 1) {
      const remaining = Math.max(0, this.duration - this.travelled);
      if (!remaining) return this.travelled;
      const cost = Math.max(this.initialStep, Math.max(0, frameMs) * speed);
      const budget = Math.max(0, this.duration - this.wall);
      const advance = budget <= cost ? remaining : remaining * cost / budget;
      this.travelled = Math.min(this.duration, this.travelled + Math.max(this.initialStep, advance));
      return this.travelled;
    }
    interval(speed = 1) {
      return this.initialStep / Math.max(0.01, speed);
    }
  }
  const api = { HiMFrameClock, initialFrames };
  root.HiMTiming = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
