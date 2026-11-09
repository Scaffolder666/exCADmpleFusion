/* Node regression for the HiM reference playback's native frame clock.
   Run with: node tests/test_him_frame_clock.js */
"use strict";
const assert = require("node:assert/strict");
const { HiMFrameClock, initialFrames } = require("../ui/reference/frame_clock.js");

assert.equal(initialFrames(2000), 15);
assert.equal(initialFrames(10000), 75);
assert.equal(initialFrames(8000), 60);
const fast = new HiMFrameClock(8000);
const fastStep = fast.completed(5, 1);
assert.ok(fastStep > 0 && fastStep < 200, "initial frame step, no immediate jump");

const slow = new HiMFrameClock(8000);
slow.tick(500, 1);
assert.ok(slow.completed(500, 1) > fastStep,
          "slow Fusion recompute increases parameter progress per completed frame");
for (let i = 0; i < 90; i++) {
  fast.tick(133.34, 1);
  fast.completed(5, 1);
}
assert.equal(fast.travelled, 8000, "completed sequence reaches the real final value");

const resumed = new HiMFrameClock(8000, 4000);
assert.equal(resumed.travelled, 4000);
assert.ok(resumed.completed(100, 1) > 4000);
assert.ok(new HiMFrameClock(8000).interval(2) < new HiMFrameClock(8000).interval(1));
assert.throws(() => new HiMFrameClock(0), RangeError);
console.log("HiM adaptive frame-clock regression: PASS");
