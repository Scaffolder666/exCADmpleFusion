/* Version B tutorial player. The tutorial's clock is independent of
   Fusion's feature timeline. Each step: title, tools used, what the designer
   said (synchronized with the recorded voice or synthetic speech), and the
   reference model + pointer drawn in the Fusion canvas. */
"use strict";

const $ = (id) => document.getElementById(id);
const state = { example: null, index: 0, elapsed: 0, playing: false, startedAt: 0, raf: 0, cueIndex: -1,
                links: {}, lastAnimationFrame: -Infinity, animationInFlight: false };
const video = $("video"), audio = $("audio");

function bridge(action, payload = {}) {
  if (!window.adsk || typeof window.adsk.fusionSendData !== "function") {
    setStatus("Open this player inside Autodesk Fusion.", true);
    return Promise.resolve();
  }
  try {
    return Promise.resolve(window.adsk.fusionSendData(action, JSON.stringify(payload)))
      .catch((error) => setStatus(String(error), true));
  } catch (error) {
    setStatus(String(error), true);
    return Promise.resolve();
  }
}
function setStatus(message, error = false) {
  $("status").textContent = message || "";
  $("status").classList.toggle("error", !!error);
}
function secs(ms) {
  const whole = Math.floor(Math.max(0, ms) / 1000);
  return String(Math.floor(whole / 60)).padStart(2, "0") + ":" + String(whole % 60).padStart(2, "0");
}
const step = () => state.example?.steps[state.index] || null;
const animationDuration = () => step()?.duration_ms || 8000;
const duration = () => {
  const media = mediaMaster();
  const recorded = media && Number.isFinite(media.duration) ? Math.max(0, media.duration - mediaOffset()) * 1000 : 0;
  return Math.max(animationDuration(), recorded);
};
const playbackSpeed = () => Number($("playbackSpeed").value) || 1;
const hasRecordedVoice = () => !!(audio.getAttribute("src") || video.getAttribute("src"));

/* ---------- voice: the recording, or synthetic speech of the transcript ---------- */
let spokenCue = -1;
let speechPending = false;
let speechGeneration = 0;
function stopNarration() {
  spokenCue = -1;
  speechPending = false;
  speechGeneration++;
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}
function speakCue(index) {
  if (!$("narrationEnabled").checked || hasRecordedVoice()) return;
  if (!("speechSynthesis" in window) || index < 0 || index === spokenCue) return;
  spokenCue = index;
  window.speechSynthesis.cancel();
  const generation = ++speechGeneration;
  const text = step()?.cues?.[index]?.label;
  if (!text) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = Math.max(0.5, Math.min(2, playbackSpeed()));
  speechPending = true;
  utterance.onend = utterance.onerror = () => { if (generation === speechGeneration) speechPending = false; };
  window.speechSynthesis.speak(utterance);
}
function mediaOffset() { return (step()?.media?.offset_ms || 0) / 1000; }
function mediaMaster() {
  if (video.getAttribute("src")) return video;
  if (audio.getAttribute("src")) return audio;
  return null;
}
function stopMedia() {
  video.pause(); audio.pause();
  video.removeAttribute("src"); audio.removeAttribute("src");
  video.load(); audio.load();
}
function playMedia() {
  if (!state.playing) return;
  for (const element of [video, audio]) {
    if (element.getAttribute("src")) {
      try {
        element.currentTime = mediaOffset() + state.elapsed / 1000;
        element.playbackRate = playbackSpeed();
        const promise = element.play();
        if (promise && promise.catch) promise.catch(() => setStatus("Media playback unavailable; the tutorial still plays.", true));
      } catch (_) { /* metadata may not have loaded yet */ }
    }
  }
}

/* ---------- rendering ---------- */
function renderRail() {
  const rail = $("stepRail");
  rail.replaceChildren();
  if (!state.example) return;
  state.example.steps.forEach((item, i) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.stepIndex = String(i);
    button.className = "step-card" + (i === state.index ? " active" : "") + (i < state.index ? " visited" : "");
    button.setAttribute("aria-current", i === state.index ? "step" : "false");
    button.setAttribute("aria-label", "Step " + (i + 1) + ": " + item.title);
    button.title = "Step " + (i + 1) + ": " + item.title;
    const num = document.createElement("span");
    num.className = "num";
    num.textContent = String(i + 1).padStart(2, "0");
    button.append(num);
    button.addEventListener("click", () => selectStep(i));
    rail.appendChild(button);
  });
  const active = [...rail.children].find((node) => Number(node.dataset.stepIndex) === state.index);
  if (active) {
    const left = active.offsetLeft - rail.offsetLeft;
    if (left < rail.scrollLeft) rail.scrollLeft = left;
    else if (left + active.offsetWidth > rail.scrollLeft + rail.clientWidth)
      rail.scrollLeft = left + active.offsetWidth - rail.clientWidth;
  }
}
function renderGeometryLink() {
  const current = step();
  if (!current) return;
  const link = state.links[current.id];
  const status = $("linkStatus");
  if (!link) {
    status.textContent = "Not linked";
    status.className = "geometry-link__status";
  } else if (!link.available) {
    status.textContent = "Linked in another design · " + link.label;
    status.className = "geometry-link__status unavailable";
  } else {
    status.textContent = link.kind + " · " + link.label;
    status.className = "geometry-link__status linked";
  }
  $("locateGeometry").disabled = !(link && link.available);
  $("removeGeometry").disabled = !link;
}
function renderSaid() {
  const list = $("said");
  list.replaceChildren();
  list.hidden = !$("captionsEnabled").checked;
  (step()?.cues || []).forEach((cue, i) => {
    const li = document.createElement("li");
    li.textContent = cue.label;
    li.dataset.cue = String(i);
    li.className = i === state.cueIndex ? "current" : (i < state.cueIndex ? "said-before" : "");
    li.addEventListener("click", () => seek(cue.at_ms));
    list.appendChild(li);
  });
  if (!(step()?.cues || []).length) list.appendChild(Object.assign(document.createElement("li"),
    { textContent: "Nothing was said in this step.", className: "empty" }));
}
function renderDetails() {
  const current = step();
  if (!current) return;
  $("stepCount").textContent = (state.index + 1) + " / " + state.example.steps.length;
  $("stepEyebrow").textContent = "STEP " + String(state.index + 1).padStart(2, "0");
  $("stepTitle").textContent = current.title;
  const tools = $("tools");
  tools.replaceChildren();
  for (const name of current.tools || []) {
    const chip = document.createElement("span");
    chip.className = "tool-tag";
    chip.textContent = name;
    tools.appendChild(chip);
  }
  renderGeometryLink();
  stopMedia();
  const media = current.media || {};
  if (media.video) video.src = media.video;
  if (media.audio) audio.src = media.audio;
  video.muted = !!media.audio;
  for (const element of [video, audio]) {
    element.onloadedmetadata = () => {
      if (element.getAttribute("src")) {
        renderTime();
        if (state.playing && element.paused) playMedia();
      }
    };
  }
  video.hidden = !media.video;
  $("noVideo").hidden = !!media.video;
  $("prev").disabled = state.index === 0;
  $("next").disabled = state.index >= state.example.steps.length - 1;
  state.cueIndex = -1;
  renderSaid();
  renderRail();
  renderTime();
}
function renderTime() {
  const total = duration();
  $("clock").textContent = secs(state.elapsed) + " / " + secs(total);
  $("scrub").value = String(Math.floor(1000 * state.elapsed / total));
  $("scrub").setAttribute("aria-valuetext", secs(state.elapsed) + " of " + secs(total));
  let active = -1;
  (step()?.cues || []).forEach((cue, i) => { if (cue.at_ms <= state.elapsed) active = i; });
  if (active !== state.cueIndex) {
    state.cueIndex = active;
    if (state.playing) speakCue(active);
    for (const li of $("said").children) {
      const i = Number(li.dataset.cue);
      li.className = i === active ? "current" : (i < active ? "said-before" : "");
    }
  }
}

/* ---------- playback ---------- */
function sendAnimationFrame(force = false) {
  const current = step();
  if (!current?.animation_available && !current?.pointer_available) return;
  const now = performance.now();
  if (state.animationInFlight || (!force && now - state.lastAnimationFrame < 145)) return;
  state.lastAnimationFrame = now;
  state.animationInFlight = true;
  bridge("animation_frame", { step_id: current.id, progress: Math.max(0, Math.min(1, state.elapsed / animationDuration())) })
    .finally(() => { state.animationInFlight = false; });
}
function pause() {
  if ("speechSynthesis" in window && window.speechSynthesis.speaking) window.speechSynthesis.pause();
  state.playing = false;
  cancelAnimationFrame(state.raf);
  video.pause(); audio.pause();
  $("play").innerHTML = "▶ <span>Play</span>";
  $("play").setAttribute("aria-label", "Play");
}
function selectStep(index, keepPlaying = false) {
  if (!state.example || index < 0 || index >= state.example.steps.length) return;
  pause();
  stopNarration();
  state.index = index;
  state.elapsed = 0;
  state.lastAnimationFrame = -Infinity;
  renderDetails();
  const next = bridge("set_step", { index });
  if (keepPlaying) next.then(() => { if (state.index === index) play(); });
}
function seek(ms) {
  stopNarration();
  state.elapsed = Math.max(0, Math.min(duration(), ms));
  state.startedAt = performance.now() - state.elapsed / playbackSpeed();
  for (const element of [video, audio]) {
    if (element.getAttribute("src")) {
      try { element.currentTime = mediaOffset() + state.elapsed / 1000; } catch (_) {}
    }
  }
  renderTime();
  sendAnimationFrame(true);
}
function play() {
  if (!step()) return;
  if (state.elapsed >= duration()) seek(0);
  state.playing = true;
  state.startedAt = performance.now() - state.elapsed / playbackSpeed();
  $("play").innerHTML = "Ⅱ <span>Pause</span>";
  $("play").setAttribute("aria-label", "Pause");
  playMedia();
  if ("speechSynthesis" in window && window.speechSynthesis.paused && speechPending)
    window.speechSynthesis.resume();
  else {
    stopNarration();
    if (state.cueIndex >= 0) speakCue(state.cueIndex);
  }
  sendAnimationFrame(true);
  tick();
}
function tick() {
  if (!state.playing) return;
  const master = mediaMaster();
  const mediaReady = master && master.readyState >= 2 && !master.paused;
  if (mediaReady && master.playbackRate !== playbackSpeed()) master.playbackRate = playbackSpeed();
  state.elapsed = mediaReady ? (master.currentTime - mediaOffset()) * 1000
                             : (performance.now() - state.startedAt) * playbackSpeed();
  state.elapsed = Math.max(0, state.elapsed);
  const mediaPending = master && master.getAttribute("src") &&
    (master.readyState < 1 || (!master.ended &&
      (!Number.isFinite(master.duration) || master.currentTime < master.duration - 0.03)));
  if (state.elapsed >= duration() - 30 && !mediaPending && !speechPending) {
    if ($("playbackScope").value === "all" && state.index < state.example.steps.length - 1) {
      selectStep(state.index + 1, true);
    } else {
      state.elapsed = duration();
      renderTime();
      pause();
      if (step()?.animation_available || step()?.pointer_available) bridge("animation_end", { step_id: step().id });
    }
    return;
  }
  state.elapsed = Math.min(state.elapsed, duration());
  renderTime();
  sendAnimationFrame();
  state.raf = requestAnimationFrame(tick);
}
function loadExample(data) {
  pause();
  state.example = data;
  state.links = {};
  state.index = 0;
  state.elapsed = 0;
  $("exampleTitle").textContent = data.title;
  renderDetails();
  setStatus(data.description || "");
}

/* ---------- messages from Fusion ---------- */
window.fusionJavaScriptHandler = {
  handle(action, raw) {
    try {
      const payload = JSON.parse(raw);
      if (action === "example") loadExample(payload);
      else if (action === "links") {
        state.links = payload.by_step || {};
        renderGeometryLink();
      } else if (action === "step") {
        if (payload.play && state.example) selectStep(payload.index, true);
        else if (payload.index !== state.index && state.example) selectStep(payload.index);
      } else if (action === "status") setStatus(payload.message, payload.error);
      return "OK";
    } catch (error) {
      setStatus(String(error), true);
      return "ERROR";
    }
  },
};

/* ---------- controls ---------- */
$("import").addEventListener("click", () => { pause(); bridge("open_package"); });
$("demo").addEventListener("click", () => { pause(); bridge("load_demo"); });
$("extractDraft").addEventListener("click", () => { pause(); bridge("extract_draft"); });
$("collapse").addEventListener("click", () => {
  const collapsed = document.body.classList.toggle("collapsed");
  $("collapse").setAttribute("aria-pressed", String(collapsed));
  $("collapse").textContent = collapsed ? "▴" : "▾";
});
$("play").addEventListener("click", () => (state.playing ? pause() : play()));
$("replay").addEventListener("click", () => { if (step()) { pause(); seek(0); play(); } });
$("prev").addEventListener("click", () => selectStep(state.index - 1));
$("next").addEventListener("click", () => selectStep(state.index + 1));
$("scrub").addEventListener("input", (e) => seek(duration() * Number(e.target.value) / 1000));
$("playbackScope").addEventListener("change", () => pause());
$("playbackSpeed").addEventListener("change", () => {
  state.startedAt = performance.now() - state.elapsed / playbackSpeed();
  for (const element of [video, audio]) element.playbackRate = playbackSpeed();
  if (state.playing && $("narrationEnabled").checked) { stopNarration(); speakCue(state.cueIndex); }
});
$("captionsEnabled").addEventListener("change", renderSaid);
$("narrationEnabled").addEventListener("change", () => { stopNarration(); if (state.playing) speakCue(state.cueIndex); });
$("focusMode").addEventListener("change", (event) => bridge("set_focus", { enabled: !!event.target.checked }));
$("bindGeometry").addEventListener("click", () => bridge("link_selected"));
$("locateGeometry").addEventListener("click", () => bridge("locate_linked"));
$("removeGeometry").addEventListener("click", () => bridge("unlink_step"));
$("showReference").addEventListener("change", (e) => bridge("set_visible", { visible: e.target.checked }));
$("stepRail").addEventListener("keydown", (event) => {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) || !state.example) return;
  event.preventDefault();
  const last = state.example.steps.length - 1;
  const target = event.key === "Home" ? 0 : event.key === "End" ? last :
    Math.max(0, Math.min(last, state.index + (event.key === "ArrowRight" ? 1 : -1)));
  selectStep(target);
});
for (const element of [video, audio]) {
  element.addEventListener("error", () => {
    if (element.getAttribute("src")) setStatus("Couldn't load this tutorial's recording.", true);
  });
}
bridge("ready");
