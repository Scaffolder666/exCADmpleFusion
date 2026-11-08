/* End-to-end reference-panel state regression, using a fake Fusion bridge.
 * This checks the important full -> feature -> full presentation contract.
 * It is not an Autodesk Fusion geometry or native recomputation test.
 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const { HiMFrameClock, initialFrames } = require("../ui/him_frame_clock.js");

class MockElement {
  constructor() {
    this.dataset = {};
    this.style = { setProperty(name, value) { this[name] = value; } };
    this.classList = { toggle() {} };
    this.children = [];
    this.handlers = {};
    this.value = 0;
    this.paused = true;
  }
  setAttribute() {}
  addEventListener(name, fn) { this.handlers[name] = fn; }
  append(...x) { this.children.push(...x); }
  appendChild(x) { this.children.push(x); return x; }
  replaceChildren(...x) { this.children = x; }
  querySelector() { return null; }
  scrollIntoView() {}
  pause() { this.paused = true; }
  play() { this.paused = false; return Promise.resolve(); }
}

async function main() {
  let now = 0;
  const controls = new Map();
  const get = id => {
    if (!controls.has(id)) controls.set(id, new MockElement());
    return controls.get(id);
  };
  const document = { getElementById: get, createElement: () => new MockElement() };
  const calls = [];
  const window = {
    adsk: {
      fusionSendData(action, json) {
        calls.push({ action, payload: JSON.parse(json) });
        return Promise.resolve(JSON.stringify({ ok: true }));
      },
    },
  };
  const context = vm.createContext({
    window, document, performance: { now: () => now },
    requestAnimationFrame() {},
    HiMTiming: { HiMFrameClock, initialFrames },
  });
  const source = fs.readFileSync(path.join(__dirname, "../ui/reference.js"), "utf8");
  vm.runInContext(source, context, { filename: "reference.js" });
  const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };
  const count = action => calls.filter(c => c.action === action).length;
  const value = expr => vm.runInContext(expr, context);

  window.fusionJavaScriptHandler.handle("example", JSON.stringify({
    title: "Two feature tutorial",
    steps: [
      { id: "a", title: "Extrude1", duration_ms: 2000,
        tools: ["Extrude"], cues: [{ at_ms: 250, label: "Why the base is needed" }] },
      { id: "b", title: "Mirror1", duration_ms: 2000,
        tools: ["Mirror"], cues: [{ at_ms: 250, label: "Why symmetry may be useful" }] },
    ],
  }));
  await flush();
  assert.equal(count("ref_frame"), 0,
    "Before Play, the entire shaded model should be shown; no native frame requested");
  assert.equal(value("S.fresh"), true);

  const scrub = get("scrub");
  scrub.handlers.input({ currentTarget: { value: "50" } });
  await flush();
  assert.equal(calls.filter(c => c.action === "ref_frame").at(-1).payload.progress, 0.5);
  assert.equal(value("S.playing"), false);

  scrub.handlers.input({ currentTarget: { value: "100" } });
  await flush();
  assert.equal(count("ref_overview"), 1, "Scrub 100% must restore full model");
  assert.equal(value("S.fresh"), true);

  scrub.handlers.input({ currentTarget: { value: "0" } });
  await flush();
  assert.equal(count("ref_overview"), 2, "Scrub 0% must restore full model");

  vm.runInContext("play(true)", context);
  for (let i = 0; i < 210; i++) {
    now += 25;
    vm.runInContext("tick(performance.now())", context);
    await flush();
  }
  assert.equal(value("S.playing"), false);
  assert.equal(value("S.index"), 1);
  assert.equal(value("S.fresh"), true);
  assert.equal(count("ref_overview"), 3,
    "Finishing both steps must restore the complete model");
  assert.deepEqual(calls.filter(c => c.action === "set_step").map(c => c.payload.index), [0, 1]);
  assert.deepEqual(calls.filter(c => c.action === "set_step").map(c => c.payload.preview),
                   [true, false], "Only the initial step previews the full solid model; continuous Feature playback does not flash the overview");
  // Selection is navigation, including re-selecting the current step.
  let frames = count("ref_frame");
  value("selectStep(0)");
  await flush();
  assert.equal(value("S.playing"), false);
  assert.equal(value("S.fresh"), true);
  assert.equal(count("ref_frame"), frames);
  value("selectStep(0)");
  await flush();
  assert.equal(count("ref_frame"), frames);
  assert.equal(calls.at(-1).action, "ref_overview");

  // Filtering must not animate before Play either.
  value('applyFilter({steps:[1], tags:{1:"changed here"}, features:["Mirror1"]})');
  await flush();
  assert.equal(value("S.playing"), false);
  assert.equal(count("ref_frame"), frames);

  // Selecting a step during an expensive native frame cannot let its old
  // acknowledgement restart playback or overwrite the final overview.
  let release;
  window.adsk.fusionSendData = (action, json) => {
    calls.push({action, payload: JSON.parse(json)});
    if (action === "ref_frame") return new Promise(resolve => { release = resolve; });
    return Promise.resolve(JSON.stringify({ok:true}));
  };
  scrub.handlers.input({currentTarget:{value:"50"}});
  assert.equal(value("S.inFlight"), true);
  value("selectStep(1)");
  await flush();
  frames = count("ref_frame");
  release(JSON.stringify({ok:true}));
  await flush();
  assert.equal(value("S.playing"), false);
  assert.equal(count("ref_frame"), frames);
  assert.equal(calls.at(-1).action, "ref_overview");
  console.log("Reference full/focus/full, selection, filtering and delayed scrubbing: PASS");
}
main().catch(error => { console.error(error); process.exitCode = 1; });

