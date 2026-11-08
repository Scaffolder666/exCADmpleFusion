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
const S = { plan: [], shown: null,
  example: null, geometry: [], index: 0, clip: [], pos: 0, elapsed: 0, playing: false,
  direction: 1, continuous: true, speed: 1, filtered: false, changed: [], more: [], picked: null,
  last: 0, cue: -1, fresh: true, tags: {}, inFlight: false,
  frameClock: null, nextFrameAt: 0, epoch: 0, manualFrame: false,
  stepPending: false, stepRequest: 0, overviewPending: false, overviewInFlight: false,
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
function status(message, error = false) {
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
  S.epoch++;              // stale native frame replies cannot move a new step
  S.frameClock = null;
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
function stopSpeech() { if ("speechSynthesis" in window) speechSynthesis.cancel(); }
function speakCue(item, index) {
  if (!S.playing || S.direction < 0 || index < 0 || (item.media && item.media.audio) || !("speechSynthesis" in window)) return;
  stopSpeech();
  const cue = (item.cues || [])[index];
  if (!cue || !cue.label) return;
  const utterance = new SpeechSynthesisUtterance(cue.label);
  utterance.rate = Math.max(0.5, Math.min(2, S.speed));
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
  if (audio.paused) audio.play().catch(() => {});
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
  stopAudio();
  stopSpeech();
  const at = S.clip.indexOf(i);
  if (at < 0) { S.filtered = false; S.changed = []; S.more = []; setClip(false); }
  S.pos = S.clip.indexOf(i);
  // Re-selecting the current step must also restore overview.
  if (i === S.index) {
    S.epoch++;
    S.fresh = true;
    S.overviewPending = true;
  } else setIndex(i);
  S.elapsed = 0;
  S.direction = 1;
  if (autoplay) play(false);
  else render();
}
function finishNativeStep() {
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
    S.shown = null;
    stopAudio();
    stopSpeech();
    // The final clip item might not be the source model's final feature
    // (e.g. a face-filtered clip). Restore the COMPLETE shaded design.
    S.overviewPending = true;
    render();
  }
}
function tick(now) {
  if (S.playing) {
    const dt = Math.max(0, now - S.last);
    S.last = now;
    // Wall-time is accounted for while Fusion recomputes a frame, but
    // progress is advanced ONLY when that frame has finished rendering.
    // Feature duration starts after Fusion acknowledges the Timeline
    // transition, not while a complex model is still loading that step.
    if (S.frameClock && !S.stepPending) S.frameClock.tick(dt, S.speed);
    // Do not rebuild up to 150 timeline cards at 60 FPS while the CAD
    // kernel is busy computing a single native animation frame.
    if (!S.inFlight) render();
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
function card(item) {
  const box = el("div", { class: "card" });
  if ((item.tools || []).length) {
    const tools = el("div", { class: "params" });
    for (const name of item.tools) tools.appendChild(el("span", {}, name));
    box.appendChild(tools);
  }
  const plan = S.plan[S.index] || [];
  if (plan.length) {
    // How the designer's model shows this step: native parameter animation,
    // a visual fallback, or the timeline state only.
    const line = el("ul", { class: "anim" });
    for (const p of plan) {
      const live = S.shown && S.shown.step === S.index && S.shown.feature === p.feature ? S.shown : null;
      let text = p.feature + " · ";
      if (live && live.mode === "instant") {
        text += "appears immediately · actual Fusion geometry" +
                (live.wireframe ? " · ghost wireframe context" :
                  " · shaded context (" + (live.context_fallback || "exact isolation unavailable") + ")");
        if (live.fallback) text += " (" + live.fallback + ")";
      }
      else if (live && live.fallback) text += "visual fallback (" + live.fallback + ")";
      else if (live && live.wireframe && live.mode === "parameter")
        text += "native reconstruction · ghost wireframe · " + (live.parameters || []).join(", ");
      else if (live && live.wireframe && live.mode === "visual")
        text += "ghost wireframe · feature fade (no suitable numeric parameter)";
      else if (live && live.mode === "parameter")
        text += "native reconstruction · translucent context (" +
                (live.context_fallback || "exact isolation unavailable") + ") · " +
                (live.parameters || []).join(", ");
      else if (p.mode === "parameter") text += "parameter animation: " + p.parameters.join(", ");
      else if (p.mode === "instant") text += "instant appearance (no numeric parameter)";
      else if (p.mode === "visual") text += "visual fade (legacy inspect mode)";
      else text += "timeline state";
      line.appendChild(el("li", { class: p.mode + (live ? " live" : "") }, text));
    }
    box.appendChild(line);
  }
  const cues = item.cues || [];
  let active = -1;
  cues.forEach((c, i) => { if (c.at_ms <= S.elapsed) active = i; });
  {
    const label = el("div", { class: "explanation-label" },
      "Why this decision? · Reasoning / transcript");
    box.appendChild(label);
    const list = el("ol", { class: "said" });
    cues.forEach((c, i) => {
      const li = el("li", { class: i === active ? "current" : (i < active ? "before" : "") }, c.label);
      li.addEventListener("click", (e) => { e.stopPropagation(); S.elapsed = c.at_ms; S.fresh = false; S.epoch++; S.manualFrame = true; resetNativeClock(); syncAudio(true); render(); });
      list.appendChild(li);
    });
    if (!cues.length) list.appendChild(el("li", {}, "Nothing was said in this step."));
    box.appendChild(list);
  }
  if (active !== S.cue) {
    S.cue = active;
    speakCue(item, active);
  }
  return box;
}
function render() {
  if (!S.example) return;
  const progress = Math.max(0, Math.min(1, S.elapsed / duration()));
  $("scrub").value = Math.round(progress * 200) / 2;
  $("scrubValue").textContent = Math.round(progress * 100) + "%";
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
  const due = (S.playing && performance.now() >= S.nextFrameAt) || S.manualFrame;
  if (!S.fresh && !S.inFlight && !S.stepPending && !S.overviewInFlight && due) {
    const index = S.index, epoch = S.epoch;
    const sentProgress = progress, direction = S.direction;
    const sentAt = performance.now();
    S.inFlight = true;
    S.manualFrame = false;
    bridge("ref_frame", { index, progress: sentProgress, elapsed: S.elapsed }).then((ok) => {
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
          finishNativeStep();
        } else {
          const travelled = S.frameClock.completed(renderedAt - sentAt, S.speed);
          S.elapsed = direction > 0 ? travelled : duration() - travelled;
          S.nextFrameAt = sentAt + S.frameClock.interval(S.speed);
        }
      }
      // Paused/manual scrubbing and rapid step changes need a fresh frame,
      // but never dispatch overlapping expensive Fusion recomputations.
      if (S.manualFrame || S.playing || S.overviewPending) render();
    });
  }
  $("play").innerHTML = S.playing ? "&#10074;&#10074;" : "&#9654;";
  $("play").setAttribute("aria-label", S.playing ? "Pause" : "Play");
  $("clock").textContent = secs(S.elapsed) + " / " + secs(duration());
  const mode = $("mode");
  mode.classList.toggle("filtered", S.filtered);
  mode.hidden = !S.filtered;
  $("modeText").textContent = S.filtered
    ? S.clip.length + " relevant steps · newest first" : "";
  $("showMore").hidden = !S.filtered || !S.canMore;
  $("showAll").hidden = !S.filtered;
  const rail = $("rail");
  rail.replaceChildren();
  S.clip.forEach((i) => {
    const item = steps()[i];
    const li = el("li", { class: "step" + (i === S.index ? " current" : ""), "data-kind": kindOf(item) });
    const button = el("button", { class: "capsule", type: "button" });
    const name = el("span", { class: "name" }, (i + 1) + "  " + item.title);
    if (S.filtered) name.appendChild(el("span", { class: "tag" }, S.tags[i] || "changed here"));
    button.append(name, el("span", { class: "meta" }, (item.tools || []).join(" · ")));
    button.addEventListener("click", () => selectStep(i));
    li.appendChild(button);
    const bar = el("div", { class: "progress" });
    const fill = el("span");
    if (i === S.index) fill.style.width = Math.round(progress * 100) + "%";
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
            S.index = i; S.elapsed = 0; S.frameClock = null;
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
  const pct = Math.max(0, Math.min(100, Number(event.currentTarget.value)));
  S.playing = false;             // scrubbing takes precedence over autoplay
  S.epoch++;                     // ignore obsolete native frame replies
  S.elapsed = duration() * pct / 100;
  S.frameClock = null;
  S.cue = -1;
  S.fresh = pct === 0 || pct === 100;
  S.manualFrame = !S.fresh;
  S.overviewPending = S.fresh;   // endpoints always show the COMPLETE model
  stopAudio();
  stopSpeech();
  render();
});
$("play").addEventListener("click", () => (S.playing ? pause() : play(true)));
$("replay").addEventListener("click", replay);
$("forward").addEventListener("click", forward);
$("back").addEventListener("click", backward);
$("showMore").addEventListener("click", () => bridge("show_more"));
$("showAll").addEventListener("click", showAll);
$("fit").addEventListener("click", () => bridge("fit_view"));
$("speed").addEventListener("input", () => { S.speed = Number($("speed").value); $("speedValue").textContent = S.speed + "×"; syncAudio(true); });
$("import").addEventListener("click", () => { pause(); bridge("open_package"); });
$("demo").addEventListener("click", () => { pause(); bridge("load_demo"); });
$("extractDraft").addEventListener("click", () => { pause(); bridge("extract_draft"); });

requestAnimationFrame(tick);
bridge("ready");

