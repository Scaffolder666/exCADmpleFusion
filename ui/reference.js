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
};

function bridge(action, payload = {}) {
  if (!window.adsk || typeof window.adsk.fusionSendData !== "function") return Promise.resolve();
  return Promise.resolve(window.adsk.fusionSendData(action, JSON.stringify(payload))).then((reply) => { if (reply && reply !== "response" && reply !== "OK") { try { const data = JSON.parse(reply); if (data && data.error) status(data.error, true); } catch (_) {} } }).catch((e) => status(String(e), true));
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
  const tool = (item.tools || []).join(" ").toLowerCase();
  if (/cut|boolean|hole|window/.test(tool)) return "cut";
  if (/fillet|chamfer|round|bevel/.test(tool)) return "fillet";
  if (/pattern/.test(tool)) return "pattern";
  if (/mirror/.test(tool)) return "mirror";
  if (/revolve|rotate/.test(tool)) return "revolve";
  if (/move|proxy|insert/.test(tool)) return "move";
  if (/extrude/.test(tool)) return "extrude";
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
function setIndex(i) {
  if (i === S.index && S.example) return;
  S.index = i;
  S.cue = -1;
  stopSpeech();
  S.fresh = true;     // selected but not played yet: show the step's result
  bridge("set_step", { index: i });
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
function play(continuous = true) {
  if (!S.clip.length) return;
  if (S.direction > 0 && S.elapsed >= duration() && S.pos >= S.clip.length - 1) { replay(); return; }
  S.playing = true;
  S.cue = -1;
  S.fresh = false;
  S.continuous = continuous;
  S.last = performance.now();
  syncAudio(true);
  render();
}
function pause() {
  S.playing = false;
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
function selectStep(i) {
  const at = S.clip.indexOf(i);
  if (at < 0) { S.filtered = false; S.changed = []; S.more = []; setClip(false); }
  S.pos = S.clip.indexOf(i);
  setIndex(i);
  S.elapsed = 0;
  S.direction = 1;
  play(false);
}
function tick(now) {
  if (S.playing) {
    const dt = Math.max(0, now - S.last) * S.speed;
    S.last = now;
    S.elapsed += dt * S.direction;
    if (S.direction > 0 && S.elapsed >= duration()) {
      if (S.continuous && S.pos < S.clip.length - 1) {
        S.pos++;
        setIndex(S.clip[S.pos]);
        S.elapsed = 0;
        syncAudio(true);
      } else {
        S.elapsed = duration();
        S.playing = false;
        stopAudio();
      }
    } else if (S.direction < 0 && S.elapsed <= 0) {
      S.elapsed = 0;
      S.playing = false;
      S.direction = 1;
    } else {
      syncAudio(false);
    }
    render();
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
  play(true);       // HiM renders the clip immediately upon selection
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
      if (live && live.fallback) text += "visual fallback (" + live.fallback + ")";
      else if (p.mode === "parameter") text += "parameter animation: " + p.parameters.join(", ");
      else if (p.mode === "visual") text += "visual fade (no parameter to animate)";
      else text += "timeline state";
      line.appendChild(el("li", { class: p.mode + (live ? " live" : "") }, text));
    }
    box.appendChild(line);
  }
  const cues = item.cues || [];
  let active = -1;
  cues.forEach((c, i) => { if (c.at_ms <= S.elapsed) active = i; });
  {
    const list = el("ol", { class: "said" });
    cues.forEach((c, i) => {
      const li = el("li", { class: i === active ? "current" : (i < active ? "before" : "") }, c.label);
      li.addEventListener("click", (e) => { e.stopPropagation(); S.elapsed = c.at_ms; S.fresh = false; syncAudio(true); render(); });
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
  if (!S.fresh && !S.inFlight) {
    S.inFlight = true;
    bridge("ref_frame", { index: S.index, progress, elapsed: S.elapsed }).finally(() => { S.inFlight = false; });
  }
  $("play").innerHTML = S.playing ? "&#10074;&#10074;" : "&#9654;";
  $("play").setAttribute("aria-label", S.playing ? "Pause" : "Play");
  $("clock").textContent = secs(S.elapsed) + " / " + secs(duration());
  const mode = $("mode");
  mode.classList.toggle("filtered", S.filtered);
  $("modeText").textContent = S.filtered
    ? S.clip.length + " step(s) made or changed the selected geometry · newest first"
    : "Whole tutorial · " + steps().length + " steps";
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
      else if (action === "animation") { S.shown = payload; render(); }
      else if (action === "source") {
        const line = $("source");
        line.classList.toggle("recorded", !payload.live);
        S.plan = payload.live ? (payload.plan || []) : [];
        line.textContent = payload.live
          ? "Playing on the designer's model " + payload.file + (payload.unmatched && payload.unmatched.length
              ? " · not found in the model: " + payload.unmatched.join(", ") : "")
          : "No source model in this example: showing its recorded geometry. HiM selection needs the designer's .f3d.";
      } else if (action === "step") {
        const i = payload.index;
        if (typeof i === "number" && i >= 0 && i < steps().length) {
          if (payload.play) selectStep(i);
          else if (i !== S.index) { const at = S.clip.indexOf(i); if (at >= 0) S.pos = at; S.index = i; S.elapsed = 0; S.fresh = true; render(); }
        }
      } else if (action === "status") status(payload.message, payload.error);
    } catch (error) {
      status(String(error), true);
    }
    return "OK";
  },
};

/* ---------- controls ---------- */
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
