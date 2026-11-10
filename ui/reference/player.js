/* Version A — History in Motion control panel (reference instance).
   Same tutorials and playback abilities as version B; different
   organisation: the example plays on the designer's own Fusion model in a
   second Fusion instance, whose canvas is the reference viewport.

   Playback follows HiM (Veuskens et al., SCF 2023):
   * no selection: the whole design process plays in order (the tutorial);
   * selecting geometry of the reference model runs HiM's filtering in
     Python and plays the matching steps newest first;
   * "Show more" follows the supporting sketches' faces (HiM show more);
   * step backward plays the current step in reverse;
   * each frame sets the feature's parameters in Fusion; the next frame is
     requested when the previous one has been computed, so the frame rate
     adapts to the model, as in HiM. */
"use strict";
const $ = (id) => document.getElementById(id);
const audio = $("audio");
const S = { tools: null, plan: [], shown: null,
  example: null, geometry: [], index: 0, clip: [], pos: 0, elapsed: 0, playing: false,
  direction: 1, continuous: true, speed: 1, filtered: false, changed: [], more: [], picked: null,
  last: 0, cue: -1, fresh: true, tags: {}, inFlight: false,
  frameClock: null, nextFrameAt: 0, epoch: 0, manualFrame: false,
  stepPending: false, stepRequest: 0, overviewPending: false, overviewInFlight: false,
  waitingForNarration: false, speechPending: false, speechToken: 0,
  stepClock: 0,           // time spent in this step (geometry AND narration), 1x content time
};

function bridge(action, payload = {}) {
  if (!window.adsk || typeof window.adsk.fusionSendData !== "function") return Promise.resolve(false);
  return Promise.resolve(window.adsk.fusionSendData(action, JSON.stringify(payload))).then((reply) => {
    if (reply && reply !== "response" && reply !== "OK") {
      try {
        const data = JSON.parse(reply);
        if (data && (data.ok === false || data.error)) {
          status(data.error || (action + " failed"), true);
          return false;
        }
      } catch (_) { /* Some Fusion versions return a plain acknowledgement. */ }
    }
    return true;
  }).catch((error) => {
    status(String(error), true);
    return false;
  });
}
// Errors also go to the add-in's diagnostic log (logs/latest.log). Sent
// directly, never through bridge()/status(), so a failure cannot loop.
function clientLog(message) {
  try { window.adsk && window.adsk.fusionSendData && window.adsk.fusionSendData("client_log", JSON.stringify({ message: String(message) })); } catch (_) {}
}
window.addEventListener && window.addEventListener("error", (e) => clientLog("panel script error: " + (e.message || e) + " at " + (e.filename || "") + ":" + (e.lineno || "")));
window.addEventListener && window.addEventListener("unhandledrejection", (e) => clientLog("panel promise error: " + (e.reason && (e.reason.stack || e.reason))));
function status(message, error = false) {
  if (error) clientLog("panel status error: " + message);
  $("status").textContent = message || "";
  $("status").classList.toggle("error", !!error);
}
function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}
const steps = () => (S.example ? S.example.steps : []);
const step = () => steps()[S.index];
const duration = () => (step() && step().duration_ms) || 8000;
function narrationPending() {
  if (S.direction < 0) return false;
  if (S.speechPending) return true;
  const media = step()?.media;
  if (!media?.audio) return false;
  if (audio.dataset.src !== media.audio || audio.readyState < 1) return true;
  const offset = (media.offset_ms || 0) / 1000;
  // An offset points into a shared recording; otherwise the entire
  // per-step audio file must finish, even if CAD animation is shorter.
  const audioEnd = Number.isFinite(audio.duration)
    ? (offset > 0 || media.slice ? Math.min(audio.duration, offset + duration() / 1000) : audio.duration)
    : Infinity;
  return !audio.ended && audio.currentTime < audioEnd - 0.03;
}
// A step lasts as long as its geometry animation OR its narration,
// whichever is longer; the step's progress bar and the overall clock use it.
const WORDS_PER_MINUTE = 165;
function speechEstimateMs(item) {
  let end = 0;
  for (const cue of item.cues || []) {
    const words = String(cue.label || "").trim().split(/\s+/).filter(Boolean).length;
    if (words) end = Math.max(end, (cue.at_ms || 0) + words * 60000 / WORDS_PER_MINUTE + 400);
  }
  return end;
}
function narrationMs(index) {
  const item = steps()[index];
  if (!item) return 0;
  const media = item.media || {};
  if (media.audio) {
    if (index === S.index && audio.dataset.src === media.audio && Number.isFinite(audio.duration)) {
      const offset = (media.offset_ms || 0) / 1000;
      const length = offset > 0 || media.slice ? Math.min(audio.duration - offset, (item.duration_ms || 8000) / 1000)
                                : audio.duration;
      return Math.max(0, length * 1000);
    }
    return 0;
  }
  return "speechSynthesis" in window ? speechEstimateMs(item) : 0;   // read aloud only where available
}
function stepTotal(index) {
  const item = steps()[index];
  return Math.max((item && item.duration_ms) || 8000, narrationMs(index));
}
function stepProgress() {
  if (S.direction < 0) return Math.max(0, Math.min(1, S.elapsed / duration()));
  if (S.fresh && S.elapsed >= duration()) return 1;
  let p = S.stepClock / stepTotal(S.index);
  // Never show a finished bar while the geometry or the narration is still going.
  if (p >= 1 && (S.playing || S.waitingForNarration)) p = 0.99;
  return Math.max(0, Math.min(1, p));
}
function completeAfterNarration() {
  if (!S.playing || !S.waitingForNarration || narrationPending()) return;
  S.waitingForNarration = false;
  finishNativeStep();
}
function clipTiming() {
  let total = 0;
  const spans = S.clip.map((index, pos) => {
    const length = stepTotal(index);
    const span = {index, pos, start:total, length};
    total += length;
    return span;
  });
  const current = spans.find(span => span.index === S.index);
  const elapsed = current ? current.start + stepProgress() * current.length : 0;
  return {spans, total, elapsed};
}
function seekClip(fraction) {
  const {spans, total} = clipTiming();
  if (!spans.length || !Number.isFinite(fraction)) return;
  fraction = Math.max(0, Math.min(1, fraction));
  const time = fraction * total;
  const target = spans.find(span => time < span.start + span.length) || spans[spans.length - 1];
  S.playing = false;
  S.epoch++;
  S.pos = target.pos;
  setIndex(target.index, false);
  S.stepClock = Math.max(0, Math.min(target.length, time - target.start));
  S.elapsed = Math.min(steps()[target.index].duration_ms || 8000, S.stepClock);
  S.direction = 1;
  S.frameClock = null;
  S.cue = -1;
  S.waitingForNarration = false;
  S.fresh = fraction === 0 || fraction === 1;
  S.manualFrame = !S.fresh;
  S.overviewPending = S.fresh;
  stopAudio();
  stopSpeech();
  render();
}
function kindOf(item) {
  // Prefer the actual Fusion Feature type when the tutorial came from a
  // real .f3d Timeline; legacy snapshot examples still use tool labels.
  const sources = item.source_features || [];
  const recorded = sources.length ? sources[sources.length - 1].kind || "" : "";
  const tool = (recorded + " " + (item.tools || []).join(" ")).toLowerCase();
  if (/cut|boolean|hole|window/.test(tool)) return "cut";
  if (/fillet|chamfer|round|bevel/.test(tool)) return "fillet";
  if (/mirror/.test(tool)) return "mirror";
  if (/pattern/.test(tool)) return "pattern";
  if (/revolve|rotate/.test(tool)) return "revolve";
  if (/combine/.test(tool)) return "combine";
  if (/offset|shell|thicken|draft|sweep|loft/.test(tool)) return "modify";
  if (/move|proxy|transform/.test(tool)) return "move";
  if (/extrude/.test(tool)) return "extrude";
  if (/sketch/.test(tool)) return "sketch";
  if (/base|paste|import/.test(tool)) return "import";
  return "other";
}
function secs(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
}

/* ---------- clip and playback ---------- */
function buildClip() {
  if (!S.filtered) return steps().map((_, i) => i);
  return [...new Set(S.changed.concat(S.more))].sort((a, b) => b - a);   // newest first, as in HiM
}
function setClip(keepIndex) {
  S.clip = buildClip();
  const at = keepIndex ? S.clip.indexOf(S.index) : -1;
  S.pos = at >= 0 ? at : 0;
  if (S.clip.length) setIndex(S.clip[S.pos]);
}
function setIndex(i, preview = true) {
  if (i === S.index && S.example) return;
  S.index = i;
  S.shown = null;
  S.stepClock = 0;
  S.epoch++;              // stale native frame replies cannot move a new step
  S.frameClock = null;
  S.waitingForNarration = false;
  S.nextFrameAt = 0;
  S.manualFrame = false;
  // If the old native frame is still computing, request one final
  // overview AFTER it acknowledges, so it cannot overwrite the preview.
  S.overviewPending = preview && S.inFlight;
  S.cue = -1;
  stopSpeech();
  S.fresh = true;     // selected but not played yet: show the step's result
  S.stepPending = true;
  const request = ++S.stepRequest;
  bridge("set_step", { index: i, preview }).then((ok) => {
    if (request !== S.stepRequest) return;
    S.stepPending = false;
    if (!ok) {
      S.playing = false;
      S.fresh = true;
      stopAudio();
      stopSpeech();
    }
    if (S.playing || S.manualFrame || S.overviewPending) render();
  });
}
function stopAudio() { audio.pause(); }
function stopSpeech() {
  S.speechPending = false;
  S.speechToken++;
  if ("speechSynthesis" in window) speechSynthesis.cancel();
}
function speakCue(item, index) {
  if (!S.playing || S.direction < 0 || index < 0 || (item.media && item.media.audio) || !("speechSynthesis" in window)) return;
  stopSpeech();
  const cue = (item.cues || [])[index];
  if (!cue || !cue.label) return;
  const utterance = new SpeechSynthesisUtterance(cue.label);
  utterance.rate = Math.max(0.5, Math.min(2, S.speed));
  const token = ++S.speechToken;
  S.speechPending = true;
  utterance.onend = utterance.onerror = () => {
    if (token !== S.speechToken) return;
    S.speechPending = false;
    completeAfterNarration();
  };
  speechSynthesis.speak(utterance);
}
function syncAudio(force) {
  const media = step() && step().media;
  if (!media || !media.audio) { stopAudio(); return; }
  const want = (media.offset_ms || 0) / 1000 + S.elapsed / 1000;
  if (audio.dataset.src !== media.audio) { audio.src = media.audio; audio.dataset.src = media.audio; force = true; }
  if (!S.playing || S.direction < 0) { stopAudio(); return; }
  if (force || Math.abs(audio.currentTime - want) > 0.35) { try { audio.currentTime = want; } catch (_) {} }
  audio.playbackRate = S.speed;
  if (audio.paused && !audio.ended) audio.play().catch(() => {});
}
function resetNativeClock() {
  const travelled = S.direction > 0 ? S.elapsed : duration() - S.elapsed;
  S.frameClock = new HiMTiming.HiMFrameClock(duration(), travelled);
  S.nextFrameAt = 0;
  S.epoch++;
}
function play(continuous = true) {
  if (!S.clip.length) return;
  if (S.direction > 0 && S.elapsed >= duration() && S.pos >= S.clip.length - 1) { replay(); return; }
  S.playing = true;
  S.waitingForNarration = false;
  S.cue = -1;
  S.fresh = false;
  S.continuous = continuous;
  S.overviewPending = false;   // active reconstruction takes priority
  resetNativeClock();
  S.last = performance.now();
  syncAudio(true);
  render();
}
function pause() {
  S.playing = false;
  S.epoch++;
  // If pause interrupted an in-flight native frame, restore the requested
  // progress after its reply so the canvas does not run ahead of the rail.
  S.manualFrame = !S.fresh;
  stopAudio();
  stopSpeech();
  S.waitingForNarration = false;
  render();
}
function replay() {
  S.pos = 0;
  setIndex(S.clip[0]);
  S.elapsed = 0;
  S.direction = 1;
  play(true);
}
function forward() {
  if (!S.clip.length) return;
  if (S.elapsed >= duration() || S.direction < 0) {
    if (S.pos < S.clip.length - 1) { S.pos++; setIndex(S.clip[S.pos]); }
  }
  S.elapsed = 0;
  S.stepClock = 0;
  S.cue = -1;
  stopSpeech();
  S.direction = 1;
  play(false);
}
function backward() {
  if (!S.clip.length) return;
  if (S.elapsed <= 0 && S.pos > 0) {
    S.pos--;
    setIndex(S.clip[S.pos]);
    S.elapsed = duration();
  } else if (S.elapsed <= 0) {
    S.elapsed = duration();
  }
  S.direction = -1;
  play(false);
}
function selectStep(i, autoplay = false) {
  S.playing = false;
  S.manualFrame = false;
  S.waitingForNarration = false;
  stopAudio();
  stopSpeech();
  const at = S.clip.indexOf(i);
  if (at < 0) { S.filtered = false; S.changed = []; S.more = []; setClip(false); }
  S.pos = S.clip.indexOf(i);
  // Selecting a step shows it exactly as continuous playback reaches it:
  // the step's first frame, in the same look (no full-model detour).
  if (i === S.index) S.epoch++;
  else setIndex(i, false);
  S.elapsed = 0;
  S.stepClock = 0;
  S.direction = 1;
  S.fresh = false;
  S.overviewPending = false;
  S.manualFrame = true;
  if (autoplay) play(false);
  else render();
}
function finishNativeStep() {
  S.waitingForNarration = false;
  stopSpeech();
  if (S.direction > 0 && S.continuous && S.pos < S.clip.length - 1) {
    S.pos++;
    // Intermediate continuous-play transitions do not flash the fully
    // shaded overview between every pair of reconstructed features.
    setIndex(S.clip[S.pos], false);
    S.elapsed = 0;
    S.direction = 1;
    resetNativeClock();
    S.fresh = false;
    S.last = performance.now();
    syncAudio(true);
  } else {
    S.playing = false;
    S.direction = 1;
    S.fresh = true;     // do not send another native frame after playback
    S.frameClock = null;
    stopAudio();
    stopSpeech();
    if (S.pos >= S.clip.length - 1) {
      // End of the tutorial (or of a filtered clip): the COMPLETE shaded design.
      S.shown = null;
      S.overviewPending = true;
    }
    // A single step that finishes keeps its final frame, exactly as in
    // continuous playback.
    render();
  }
}
function tick(now) {
  if (S.playing) {
    if (S.waitingForNarration) completeAfterNarration();
    const dt = Math.max(0, now - S.last);
    S.last = now;
    // Wall-time is accounted for while Fusion recomputes a frame, but
    // progress is advanced ONLY when that frame has finished rendering.
    // Feature duration starts after Fusion acknowledges the Timeline
    // transition, not while a complex model is still loading that step.
    if (S.frameClock && !S.stepPending && !S.waitingForNarration) S.frameClock.tick(dt, S.speed);
    if (!S.stepPending && S.direction > 0) S.stepClock += dt * S.speed;
    // Do not rebuild up to 150 timeline cards at 60 FPS while the CAD
    // kernel is busy computing a single native animation frame.
    if (!S.inFlight) render(true);
  }
  requestAnimationFrame(tick);
}

/* ---------- HiM filtering (computed on the real model in Python) ---------- */
function applyFilter(result) {
  if (!result || !(result.steps || []).length) {
    status("No step of this example made the selected geometry.");
    return;
  }
  S.filtered = true;
  S.tags = result.tags || {};
  S.changed = result.steps.filter((i) => S.tags[i] !== "builds on");
  S.more = result.steps.filter((i) => S.tags[i] === "builds on");
  S.canMore = !!result.can_show_more;
  setClip(false);
  S.elapsed = 0;
  S.direction = 1;
  status("HiM: " + (result.features || []).length + " feature(s) made or changed the selection.");
  selectStep(S.index);  // Filtering selects context; Play starts reconstruction
}
function showAll() {
  S.filtered = false;
  S.changed = [];
  S.more = [];
  S.tags = {};
  setClip(true);
  bridge("clear_filter");
  render();
}

/* ---------- rendering ---------- */
function operationCueGroups(item, plan) {
  // Match reference_plan.frame_target: non-sketch features share step time
  // equally. This is a timing association, not an inferred design intention.
  const source = plan.length ? plan : (item.source_features || []).map(f => ({feature:f.name, kind:f.kind}));
  const animated = source.filter(p => p.kind !== "Sketch" && !(p.kind || "").startsWith("Construction"));
  const operations = animated.length ? animated : source;
  const groups = operations.map(p => ({ operation:p, cues:[] }));
  if (!groups.length) groups.push({ operation:null, cues:[] });
  (item.cues || []).forEach((cue, index) => {
    const slot = Math.max(0, Math.min(groups.length - 1,
      Math.floor(cue.at_ms / (item.duration_ms || 8000) * groups.length)));
    groups[slot].cues.push({cue, index});
  });
  return groups;
}
function card(item) {
  const box = el("div", { class: "card" });
  const cues = item.cues || [];
  let active = -1;
  cues.forEach((c, i) => { if (c.at_ms <= S.elapsed) active = i; });
  for (const group of operationCueGroups(item, S.plan[S.index] || [])) {
    const section = el("div", { class: "operation-transcript" });
    const operation = group.operation;
    // If the step itself is named Extrude1, its capsule already names it.
    if (operation && operation.feature !== item.title) {
      const live = S.shown && S.shown.step === S.index && S.shown.feature === operation.feature;
      section.appendChild(el("div", { class: "operation-name" + (live ? " live" : "") }, operation.feature));
    }
    const list = el("ol", { class: "said" });
    group.cues.forEach(({cue:c, index:i}) => {
      const li = el("li", { class: i === active ? "current" : (i < active ? "before" : "") }, c.label);
      li.addEventListener("click", (e) => { e.stopPropagation(); S.elapsed = c.at_ms; S.stepClock = c.at_ms; S.fresh = false; S.epoch++; S.manualFrame = true; resetNativeClock(); syncAudio(true); render(); });
      list.appendChild(li);
    });
    if (!group.cues.length) list.appendChild(el("li", {}, "No transcript available."));
    section.appendChild(list);
    box.appendChild(section);
  }
  // Where to find this step's tools in Fusion (path read from the toolbar).
  if (S.tools && S.tools.index === S.index) {
    if (S.tools.panel_error) box.appendChild(el("div", { class: "playback-note" },
      "Toolbar panel could not be added: " + S.tools.panel_error));
    for (const tool of S.tools.tools || []) {
      if (tool.error) { box.appendChild(el("div", { class: "playback-note" }, "Tool lookup failed: " + tool.error)); continue; }
      const row = el("div", { class: "tool-guide" + (tool.found ? "" : " missing") });
      row.appendChild(el("span", { class: "tool-path" },
        tool.found ? tool.path.join(" › ") : tool.label + " · " + (tool.hint || "not found in this workspace")));
      if (tool.found) {
        const use = el("button", { class: "tool-use", type: "button" }, "Use");
        use.addEventListener("click", (e) => { e.stopPropagation(); if (S.playing) pause(); bridge("use_tool", { label: tool.label }); });
        row.appendChild(use);
      }
      box.appendChild(row);
    }
  }
  // Keep actual runtime limitations visible, without repeating operation names.
  if (S.shown && S.shown.step === S.index) {
    const reason = S.shown.fallback || S.shown.context_fallback || S.shown.motion_note;
    if (reason) box.appendChild(el("div", { class: "playback-note" }, reason));
  }
  if (active !== S.cue) {
    S.cue = active;
    speakCue(item, active);
  }
  return box;
}

// light: called from the playback loop. The step list is rebuilt only when
// what it shows changed (step, clip, filter, current sentence, live
// operation); otherwise only the progress bar moves.
function railKey() {
  const item = steps()[S.index];
  let active = -1;
  ((item && item.cues) || []).forEach((c, i) => { if (c.at_ms <= S.elapsed) active = i; });
  const shown = S.shown && S.shown.step === S.index
    ? [S.shown.feature, S.shown.fallback, S.shown.context_fallback, S.shown.motion_note] : null;
  return JSON.stringify([S.index, S.clip, S.filtered, S.tags, active, shown, S.tools,
                         (S.plan[S.index] || []).length]);
}
function render(light = false) {
  if (!S.example) return;
  const progress = Math.max(0, Math.min(1, S.elapsed / duration()));   // geometry: drives frames
  const shownProgress = stepProgress();                                 // the whole step: shown on the bar
  const timing = clipTiming();
  const overall = timing.total ? timing.elapsed / timing.total : 0;
  $("scrub").value = Math.round(overall * 200) / 2;
  $("scrubValue").textContent = Math.round(overall * 100) + "%";
  // A full-model request must not race an unfinished native recompute.
  if (S.overviewPending && !S.inFlight && !S.stepPending && !S.overviewInFlight) {
    S.overviewPending = false;
    S.overviewInFlight = true;
    bridge("ref_overview").then((ok) => {
      S.overviewInFlight = false;
      if (ok && S.fresh) status("Full model · all geometry visible");
      if (S.overviewPending || S.manualFrame || S.playing) render();
    });
  }
  const due = (S.playing && !S.waitingForNarration && performance.now() >= S.nextFrameAt) || S.manualFrame;
  if (!S.fresh && !S.inFlight && !S.stepPending && !S.overviewInFlight && due) {
    const index = S.index, epoch = S.epoch;
    const sentProgress = progress, direction = S.direction;
    const sentAt = performance.now();
    S.inFlight = true;
    S.manualFrame = false;
    // settle: paused or scrubbing, so Fusion recomputes the real model here.
    bridge("ref_frame", { index, progress: sentProgress, elapsed: S.elapsed, auto_focus: $("autoFocus").checked,
                          settle: !S.playing }).then((ok) => {
      const renderedAt = performance.now();
      S.inFlight = false;
      if (!ok && epoch === S.epoch) {
        S.playing = false;
        S.manualFrame = false;
        stopAudio();
        stopSpeech();
      }
      if (ok && epoch === S.epoch && index === S.index && S.playing && S.frameClock) {
        const atEnd = direction > 0 ? sentProgress >= 1 : sentProgress <= 0;
        if (atEnd) {
          // The final native frame is acknowledged before step transitions.
          if (narrationPending()) {
            S.elapsed = duration();
            S.waitingForNarration = true;
            S.nextFrameAt = Infinity;
          } else finishNativeStep();
        } else {
          const travelled = S.frameClock.completed(renderedAt - sentAt, S.speed);
          S.elapsed = direction > 0 ? travelled : duration() - travelled;
          S.nextFrameAt = sentAt + S.frameClock.interval(S.speed);
        }
      }
      // Paused/manual scrubbing and rapid step changes need a fresh frame,
      // but never dispatch overlapping expensive Fusion recomputations.
      if (S.manualFrame || S.playing || S.overviewPending) render(S.playing && !S.manualFrame);
    });
  }
  // Rewriting the button on every frame swallowed clicks that landed on the
  // icon (the pressed element was replaced before the mouse came up).
  const playState = S.playing ? "pause" : "play";
  if ($("play").dataset.state !== playState) {
    $("play").dataset.state = playState;
    $("play").innerHTML = '<span class="control-icon ' + playState + '-icon" aria-hidden="true"></span>';
    $("play").setAttribute("aria-label", S.playing ? "Pause" : "Play");
  }
  $("clock").textContent = secs(timing.elapsed) + " / " + secs(timing.total);
  const mode = $("mode");
  mode.classList.toggle("filtered", S.filtered);
  mode.hidden = !S.filtered;
  $("modeText").textContent = S.filtered
    ? S.clip.length + " relevant steps · newest first" : "";
  $("showMore").hidden = !S.filtered || !S.canMore;
  $("showAll").hidden = !S.filtered;
  const rail = $("rail");
  const key = railKey();
  const fill = light && key === S.railKey ? rail.querySelector(".step.current .progress span") : null;
  if (fill) {
    fill.style.width = Math.round(shownProgress * 100) + "%";
    return;
  }
  S.railKey = key;
  rail.replaceChildren();
  S.clip.forEach((i) => {
    const item = steps()[i];
    const li = el("li", { class: "step" + (i === S.index ? " current" : ""), "data-kind": kindOf(item) });
    li.style.setProperty("--kind", ["#2f7d5b", "#7c4dce", "#0e7490", "#c26a12", "#b4236a"][i % 5]);
    const button = el("button", { class: "capsule", type: "button" });
    const name = el("span", { class: "name" }, (i + 1) + "  " + item.title);
    if (S.filtered) name.appendChild(el("span", { class: "tag" }, S.tags[i] || "changed here"));
    button.appendChild(name);
    button.addEventListener("click", () => selectStep(i));
    li.appendChild(button);
    const bar = el("div", { class: "progress" });
    const fill = el("span");
    if (i === S.index) fill.style.width = Math.round(shownProgress * 100) + "%";
    bar.appendChild(fill);
    li.appendChild(bar);
    if (i === S.index) li.appendChild(card(item));
    rail.appendChild(li);
  });
  const current = rail.querySelector(".current");
  if (current && S.playing) current.scrollIntoView({ block: "nearest" });
}

/* ---------- messages from Fusion ---------- */
function loadExample(data) {
  pause();
  S.example = data;
  S.filtered = false; S.changed = []; S.more = []; S.picked = null;
  S.epoch++;
  S.frameClock = null;
  S.shown = null;
  S.plan = [];
  S.index = -1;
  S.elapsed = 0;
  S.direction = 1;
  setClip(false);
  $("title").textContent = data.title;
  render();
}
window.fusionJavaScriptHandler = {
  handle(action, raw) {
    try {
      const payload = JSON.parse(raw || "{}");
      if (action === "example") loadExample(payload);
      else if (action === "filter") applyFilter(payload);
      else if (action === "tools") { S.tools = payload; render(); }
      else if (action === "pause") { if (S.playing) pause(); }
      else if (action === "animation") {
        S.shown = payload;
        if (payload.mode === "error" && payload.step === S.index) {
          S.playing = false;
          S.epoch++;
          S.manualFrame = false;
          stopAudio();
          stopSpeech();
          status("Native HiM frame failed: " + (payload.fallback || "Fusion recomputation error"), true);
        }
        render();
      }
      else if (action === "source") {
        S.plan = payload.live ? (payload.plan || []) : [];
      } else if (action === "step") {
        const i = payload.index;
        if (typeof i === "number" && i >= 0 && i < steps().length) {
          if (payload.play) selectStep(i, true);
          else if (i !== S.index) {
            const at = S.clip.indexOf(i);
            if (at >= 0) S.pos = at;
            S.epoch++;
            S.index = i; S.elapsed = 0; S.stepClock = 0; S.frameClock = null;
            S.shown = null; S.fresh = true; S.playing = false;
            S.manualFrame = false;
            stopAudio(); stopSpeech();
            render();
          }
        }
      } else if (action === "status") {
        if (!/^unknown action:\s*response$/i.test(String(payload.message || "").trim())) status(payload.message, payload.error);
      }
    } catch (error) {
      status(String(error), true);
    }
    return "OK";
  },
};

/* ---------- controls ---------- */
$("scrub").addEventListener("input", (event) => {
  if (!S.example || !S.clip.length) return;
  seekClip(Number(event.currentTarget.value) / 100);
});
$("play").addEventListener("click", () => (S.playing ? pause() : play(true)));
$("replay").addEventListener("click", replay);
$("forward").addEventListener("click", forward);
$("back").addEventListener("click", backward);
$("showMore").addEventListener("click", () => bridge("show_more"));
$("showAll").addEventListener("click", showAll);
$("autoFocus").addEventListener("change", () => bridge("ref_auto_focus", { enabled: $("autoFocus").checked }));
$("speed").addEventListener("input", () => { S.speed = Number($("speed").value); $("speedValue").textContent = S.speed + "×"; syncAudio(true); });
$("import").addEventListener("click", () => { pause(); bridge("open_package"); });
$("demo").addEventListener("click", () => { pause(); bridge("load_demo"); });

audio.addEventListener("ended", completeAfterNarration);
audio.addEventListener("loadedmetadata", () => {
  if (S.playing && !S.waitingForNarration) syncAudio(true);
  completeAfterNarration();
});
requestAnimationFrame(tick);
bridge("ready");

