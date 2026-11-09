/* Reference panel: a step's bar covers the whole step (geometry and
 * narration), and the play button is not rewritten on every frame (which
 * swallowed pause clicks). Fake Fusion bridge; not a Fusion test. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const { HiMFrameClock, initialFrames } = require("../ui/reference/frame_clock.js");

class El {
  constructor() { this.dataset = {}; this.style = { setProperty() {} }; this.classList = { toggle() {} };
    this.children = []; this.handlers = {}; this.value = 0; this.paused = true; this.innerHTMLWrites = 0; }
  set innerHTML(v) { this._html = v; this.innerHTMLWrites++; }
  get innerHTML() { return this._html || ""; }
  setAttribute() {} addEventListener(n, f) { this.handlers[n] = f; }
  append(...x) { this.children.push(...x); } appendChild(x) { this.children.push(x); return x; }
  replaceChildren(...x) { this.children = x; } querySelector() { return null; } scrollIntoView() {}
  pause() { this.paused = true; } play() { this.paused = false; return Promise.resolve(); }
}

(async () => {
  let now = 0;
  const els = new Map();
  const get = id => (els.has(id) ? els.get(id) : (els.set(id, new El()), els.get(id)));
  const spoken = [];
  const window = {
    adsk: { fusionSendData: () => Promise.resolve(JSON.stringify({ ok: true })) },
    speechSynthesis: { speak: u => spoken.push(u), cancel() {} },
  };
  const ctx = vm.createContext({
    window, document: { getElementById: get, createElement: () => new El() },
    performance: { now: () => now }, requestAnimationFrame() {},
    SpeechSynthesisUtterance: function (text) { this.text = text; },
    speechSynthesis: window.speechSynthesis,
    HiMTiming: { HiMFrameClock, initialFrames },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../ui/reference/player.js"), "utf8"), ctx);
  const value = e => vm.runInContext(e, ctx);
  const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };

  // 33 words at 165 wpm = 12 s, starting at 0.25 s: longer than the 8 s animation.
  const long = Array.from({ length: 33 }, (_, i) => "word" + i).join(" ");
  window.fusionJavaScriptHandler.handle("example", JSON.stringify({ title: "T", steps: [
    { id: "a", title: "Extrude1", duration_ms: 8000, cues: [{ at_ms: 250, label: long }] },
    { id: "b", title: "Fillet1", duration_ms: 8000, cues: [{ at_ms: 0, label: "short" }] }] }));
  await flush();
  assert.equal(Math.round(value("stepTotal(0)")), 250 + 12000 + 400, "narration sets the step length");
  assert.equal(value("stepTotal(1)"), 8000, "the animation sets it when narration is shorter");
  assert.equal(Math.round(value("clipTiming().total")), 12650 + 8000);

  value("play(true)");
  await flush();
  const button = get("play");
  const writes = button.innerHTMLWrites;
  for (let i = 0; i < 40; i++) { now += 50; value("tick(performance.now())"); await flush(); }
  assert.equal(button.innerHTMLWrites, writes, "the play button is not rewritten while playing");
  const p = value("stepProgress()");
  assert.ok(p > 0.14 && p < 0.18, "2 s into a 12.65 s step, not 2 s of 8 s: " + p);

  value("S.stepClock = 20000");
  assert.equal(value("stepProgress()"), 0.99, "never a full bar while the step is still playing");

  button.handlers.click();                                   // pause
  await flush();
  assert.equal(value("S.playing"), false);
  assert.equal(button.dataset.state, "play");
  const clock = value("S.stepClock");
  for (let i = 0; i < 5; i++) { now += 50; value("tick(performance.now())"); await flush(); }
  assert.equal(value("S.stepClock"), clock, "paused: the step clock stands still");
  console.log("Whole-step progress and stable play button: PASS");
})().catch(e => { console.error(e); process.exit(1); });
