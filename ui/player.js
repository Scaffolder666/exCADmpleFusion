/* exCADmple's reference timeline is independent of Fusion's feature timeline. */
"use strict";

const $ = (id) => document.getElementById(id);
const state = { example: null, index: 0, elapsed: 0, playing: false, startedAt: 0, raf: 0, cueIndex: -1, links: {}, lastAnimationFrame: -Infinity, animationInFlight: false, filteredIndices: null };
const video = $("video"), audio = $("audio");
let spokenCue = -1;
function stopNarration() {
  spokenCue = -1;
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}
function speakCue(index) {
  if (!$("narrationEnabled").checked || audio.getAttribute("src") || video.getAttribute("src")) return;
  if (!("speechSynthesis" in window) || index < 0 || index === spokenCue) return;
  spokenCue = index;
  window.speechSynthesis.cancel();
  const text = step()?.cues?.[index]?.label;
  if (!text) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-US";
  utterance.rate = Math.max(0.5, Math.min(2, playbackSpeed()));
  window.speechSynthesis.speak(utterance);
}

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
function step() { return state.example?.steps[state.index] || null; }
function duration() { return step()?.duration_ms || 8000; }
function playbackSpeed() { return Number($("playbackSpeed").value) || 1; }
function stopMedia() {
  video.pause(); audio.pause();
  video.removeAttribute("src"); audio.removeAttribute("src");
  video.load(); audio.load();
}
function mediaMaster() {
  if (video.getAttribute("src")) return video;
  if (audio.getAttribute("src")) return audio;
  return null;
}
function playMedia() {
  if (!state.playing) return;
  for (const element of [video, audio]) {
    if (element.getAttribute("src")) {
      try {
        element.currentTime = state.elapsed / 1000;
        element.playbackRate = playbackSpeed();
        const promise = element.play();
        if (promise && promise.catch) promise.catch(() => setStatus("Media playback unavailable; the timeline still works.", true));
      } catch (_) { /* Metadata may not have loaded yet. */ }
    }
  }
}
function renderRail() {
  const rail = $("stepRail");
  rail.replaceChildren();
  if (!state.example) return;
  state.example.steps.forEach((item, i) => {
    if (state.filteredIndices && !state.filteredIndices.includes(i)) return;
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
    const labels = document.createElement("span");
    labels.className = "step-labels";
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = item.title;
    labels.appendChild(label);
    if (item.operation?.tool || item.goal) {
      const sub = document.createElement("span");
      sub.className = "step-goal";
      const values = (item.operation?.parameters || []).slice(0, 2)
        .map((p) => p.name + ": " + p.value).join(" · ");
      sub.textContent = [item.operation?.tool, values].filter(Boolean).join(" · ") || item.goal;
      labels.appendChild(sub);
    }
    const indicator = document.createElement("span");
    indicator.className = "step-indicator";
    indicator.textContent = i === state.index ? "VIEWING" : i < state.index ? "✓" : "›";
    const timing = document.createElement("span");
    timing.className = "step-duration";
    timing.textContent = secs(item.duration_ms || 8000);
    labels.appendChild(timing);
    button.append(num, labels, indicator);
    button.addEventListener("click", () => selectStep(i));
    rail.appendChild(button);
  });
  const active = [...rail.children].find(node => Number(node.dataset.stepIndex) === state.index);
  if (active) {
    // Keep the active history card visible without scrolling the details pane.
    const top = active.offsetTop - rail.offsetTop;
    if (top < rail.scrollTop) rail.scrollTop = top;
    else if (top + active.offsetHeight > rail.scrollTop + rail.clientHeight)
      rail.scrollTop = top + active.offsetHeight - rail.clientHeight;
  }
}
function classifyReasoning(current) {
  const note = current.reasoning || {};
  const raw = (note.text || "").trim();
  const source = String(note.source || "").toLowerCase();
  const demo = source === "mockup" || source === "demo" || /^(demo reasoning|mock reasoning|illustrative)/i.test(raw);
  if (!raw) return {label:"No recorded rationale", text:"No design reasoning is attached to this step yet.",
    explainer:"Model geometry alone does not reveal the author's original reasoning.", mock:false};
  if (demo) return {label:"Illustrative only", text:raw, mock:true,
    explainer:"Mockup text — not verified as a statement from the original designer."};
  if (source === "spoken" || source === "voice" || source === "transcript")
    return {label:"Voice / transcript", text:raw, mock:false, explainer:""};
  if (source === "meeting") return {label:"Meeting note", text:raw, mock:false, explainer:""};
  if (source === "email") return {label:"Email", text:raw, mock:false, explainer:""};
  if (source === "author" || source === "written") return {label:"Author note", text:raw, mock:false, explainer:""};
  return {label:"Source unspecified", text:raw, mock:false,
    explainer:"This explanation has no verified source label in the imported example."};
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
  $("geometryStatus").textContent = current.animation_available ? "3D animation available" :
    (current.has_geometry ? "3D step available" :
    (link?.available ? "Linked source geometry" :
     (state.example?.preview_data_uri ? "Final preview only" : "No step geometry")));
  $("geometryStatus").classList.toggle("none", !current.has_geometry && !link?.available && !current.animation_available);
}
function renderDetails() {
  const current = step();
  if (!current) return;
  $("stepCount").textContent = (state.index + 1) + " / " + state.example.steps.length;
  $("exampleSteps").textContent = state.example.steps.length + " design steps";
  $("stepEyebrow").textContent = "STEP " + String(state.index + 1).padStart(2,"0");
  $("stepTitle").textContent = current.title;
  $("stepGoal").textContent = current.goal || "";
  $("toolName").textContent = current.operation?.tool || "CAD";
  $("toolInstruction").textContent = current.operation?.instruction || "";
  const rationale = classifyReasoning(current);
  $("reasoning").textContent = rationale.text;
  $("reasonSource").textContent = rationale.label;
  $("reasonSource").classList.toggle("mock", rationale.mock);
  $("sourceExplainer").textContent = rationale.explainer;
  const hasStepGeometry = !!current.has_geometry;
  renderGeometryLink();
  $("showReference").disabled = !hasStepGeometry;
  $("showReference").title = hasStepGeometry ? "Toggle this step's read-only 3D reference" :
    "This step does not contain a verified 3D snapshot";
  const parameters = $("parameters");
  parameters.replaceChildren();
  (current.operation?.parameters || []).forEach((item) => {
    const badge = document.createElement("span");
    badge.className = "parameter";
    badge.append(document.createTextNode(item.name + " "));
    const strong = document.createElement("b");
    strong.textContent = String(item.value);
    badge.append(strong);
    parameters.appendChild(badge);
  });
  stopMedia();
  const media = current.media || {};
  if (media.video) video.src = media.video;
  if (media.audio) audio.src = media.audio;
  video.muted = !!media.audio;
  video.hidden = !media.video;
  const preview = !media.video && state.example?.preview_data_uri;
  $("finalPreview").hidden = !preview;
  if (preview) $("previewImage").src = preview;
  else $("previewImage").removeAttribute("src");
  $("noVideo").hidden = !!media.video || !!preview;
  $("mediaEvidence").textContent = [
    current.animation_available && "3D operation animation",
    media.video && "Video", media.audio && "Audio"
  ].filter(Boolean).join(" + ") || "Step metadata";
  if (!media.video && !preview) {
    $("noVideo").querySelector("strong").textContent = current.animation_available ?
      "3D operation animation in Fusion" : hasStepGeometry ?
      "3D reference in Fusion" : "No recorded visuals for this step";
    $("noVideo").querySelector("span").textContent = current.animation_available ?
      "Press Play or scrub to animate the reference geometry." : hasStepGeometry ?
      "Inspect the read-only step model in the CAD canvas." :
      "Import step snapshots or video to visualize the original operation.";
  }
  $("prev").disabled = state.index === 0;
  $("next").disabled = state.index >= state.example.steps.length - 1;
  renderRail();
  renderTime();
}
function renderTime() {
  const total = duration();
  $("clock").textContent = secs(state.elapsed) + " / " + secs(total);
  $("scrub").value = String(Math.floor(1000 * state.elapsed / total));
  $("scrub").setAttribute("aria-valuetext", secs(state.elapsed) + " of " + secs(total));
  const cues = step()?.cues || [];
  let active = -1;
  cues.forEach((cue, i) => { if (cue.at_ms <= state.elapsed) active = i; });
  $("cueText").hidden = !$("captionsEnabled").checked;
  if (active !== state.cueIndex) {
    state.cueIndex = active;
    if (state.playing) speakCue(active);
    $("cueText").textContent = active >= 0 ? cues[active].label : (step()?.operation?.instruction || "Inspect the author's actions.");
  }
}
function sendAnimationFrame(force = false) {
  const current = step();
  if (!current?.animation_available) return;
  const now = performance.now();
  if (state.animationInFlight || (!force && now - state.lastAnimationFrame < 145)) return;
  state.lastAnimationFrame = now;
  state.animationInFlight = true;
  const id = current.id;
  bridge("animation_frame", {step_id: id, progress: Math.max(0, Math.min(1, state.elapsed / duration()))})
    .finally(() => { state.animationInFlight = false; });
}
function pause() {
  stopNarration();
  state.playing = false;
  cancelAnimationFrame(state.raf);
  video.pause(); audio.pause();
  $("play").innerHTML = "▶ <span>Play</span>";
  $("play").setAttribute("aria-label", "Play");
}
function selectStep(index, keepPlaying = false) {
  if (!state.example || index < 0 || index >= state.example.steps.length) return;
  pause();
  state.index = index;
  state.elapsed = 0;
  state.cueIndex = -1;
  state.lastAnimationFrame = -Infinity;
  renderDetails();
  const next = bridge("set_step", {index});
  if (keepPlaying) next.then(() => { if (state.index === index) play(); });
}
function seek(ms) {
  state.elapsed = Math.max(0, Math.min(duration(), ms));
  state.startedAt = performance.now() - state.elapsed / playbackSpeed();
  for (const element of [video, audio]) {
    if (element.getAttribute("src")) {
      try { element.currentTime = state.elapsed / 1000; } catch (_) {}
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
  spokenCue = -1;
  if (state.cueIndex >= 0) speakCue(state.cueIndex);
  sendAnimationFrame(true);
  tick();
}
function tick() {
  if (!state.playing) return;
  // The HTML media clock is authoritative when available; otherwise use a
  // monotonic wall clock. Geometry only changes between steps, not at 60 fps.
  const master = mediaMaster();
  const mediaReady = master && master.readyState >= 2 && !master.paused;
  if (mediaReady && master.playbackRate !== playbackSpeed()) master.playbackRate = playbackSpeed();
  state.elapsed = mediaReady ? master.currentTime * 1000 : (performance.now() - state.startedAt) * playbackSpeed();
  state.elapsed = Math.max(0, state.elapsed);
  if (state.elapsed >= duration() - 30) {
    if ($("playbackScope").value === "all" && state.index < state.example.steps.length - 1) selectStep(state.index + 1, true);
    else {
      state.elapsed = duration();
      renderTime();
      pause();
      if (step()?.animation_available)
        bridge("animation_end", {step_id: step().id});
    }
    return;
  }
  if (video.getAttribute("src") && audio.getAttribute("src") && mediaReady &&
      Math.abs(audio.currentTime - video.currentTime) > 0.35 && audio.readyState >= 1) {
    audio.currentTime = video.currentTime;
  }
  renderTime();
  sendAnimationFrame();
  state.raf = requestAnimationFrame(tick);
}
function loadExample(data) {
  pause();
  state.example = data;
  state.links = {};
  state.filteredIndices = null;
  state.index = 0;
  state.elapsed = 0;
  state.cueIndex = -1;
  $("exampleTitle").textContent = data.title;
  $("exampleDescription").textContent = data.description || "Explore someone else's design decisions.";
  const containsSnapshots = data.steps.some((item) => item.has_geometry);
  $("exampleType").textContent = containsSnapshots ? "3D steps" :
    (data.preview_data_uri ? "Preview-based example" : "Metadata only");
  $("packageStatus").textContent = data.source_model_included ? "Source F3D in package" : "";
  renderDetails();
  setStatus(data.steps[0]?.has_geometry ?
    "Example loaded — read-only step geometry is available in Fusion." :
    "Example loaded — this step has no verified 3D intermediate state.");
}
window.fusionJavaScriptHandler = {
  handle(action, raw) {
    try {
      const payload = JSON.parse(raw);
      if (action === "example") loadExample(payload);
      else if (action === "links") {
        state.links = payload.by_step || {};
        renderGeometryLink();
      } else if (action === "history_filter") {
        state.filteredIndices = payload.indices || [];
        renderRail();
        if (state.filteredIndices.length) selectStep(state.filteredIndices[0]);
      } else if (action === "geometry_selection") {
        $("selectionStatus").textContent = payload.selected ? payload.kind + " selected in Fusion" : "Select a face, edge or vertex in Fusion.";
        $("entityFilter").value = payload.selected ? (payload.entity_id || "") : "";
      } else if (action === "step") {
        if (payload.index !== state.index && state.example) selectStep(payload.index);
      } else if (action === "status") setStatus(payload.message, payload.error);
      return "OK";
    } catch (error) {
      setStatus(String(error), true);
      return "ERROR";
    }
  }
};
function requestHistoryFilter(expand = false) {
  const entity_id = $("entityFilter").value.trim();
  if (!entity_id) { setStatus("Enter an authored geometry entity ID.", true); return; }
  bridge("filter_history", {entity_id, expand});
}
$("filterHistory").addEventListener("click", () => requestHistoryFilter(false));
$("showMoreHistory").addEventListener("click", () => requestHistoryFilter(true));
$("clearHistory").addEventListener("click", () => {
  state.filteredIndices = null;
  renderRail();
});
$("focusMode").addEventListener("change", (event) => {
  bridge("set_focus", {enabled: !!event.target.checked});
});
$("bindGeometry").addEventListener("click", () => bridge("link_selected"));
$("locateGeometry").addEventListener("click", () => bridge("locate_linked"));
$("removeGeometry").addEventListener("click", () => bridge("unlink_step"));
$("import").addEventListener("click", () => { pause(); bridge("open_package"); });
$("demo").addEventListener("click", () => { pause(); bridge("load_demo"); });
$("play").addEventListener("click", () => state.playing ? pause() : play());
$("replay").addEventListener("click", () => { if (step()) { pause(); seek(0); play(); } });
$("playbackScope").addEventListener("change", () => pause());
$("playbackSpeed").addEventListener("change", () => {
  state.startedAt = performance.now() - state.elapsed / playbackSpeed();
  for (const element of [video, audio]) element.playbackRate = playbackSpeed();
  if (state.playing && $("narrationEnabled").checked) {
    stopNarration();
    if (state.cueIndex >= 0) speakCue(state.cueIndex);
  }
});
$("captionsEnabled").addEventListener("change", () => {
  $("cueText").hidden = !$("captionsEnabled").checked;
});
$("narrationEnabled").addEventListener("change", () => {
  stopNarration();
  if (state.playing && state.cueIndex >= 0) speakCue(state.cueIndex);
});
// Keyboard navigation is scoped to the history list, so Fusion shortcuts remain untouched.
$("stepRail").addEventListener("keydown", (event) => {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  if (!state.example) return;
  event.preventDefault();
  const target = event.key === "Home" ? 0 : event.key === "End" ? state.example.steps.length - 1 :
    Math.max(0, Math.min(state.example.steps.length - 1, state.index + (event.key === "ArrowDown" ? 1 : -1)));
  selectStep(target);
  [...$("stepRail").children].find(node => Number(node.dataset.stepIndex) === target)?.focus();
});
$("prev").addEventListener("click", () => selectStep(state.index - 1));
$("next").addEventListener("click", () => selectStep(state.index + 1));
$("scrub").addEventListener("input", (e) => seek(duration() * Number(e.target.value) / 1000));
$("showReference").addEventListener("change", (e) => bridge("set_visible", {visible: e.target.checked}));
for (const element of [video, audio]) {
  element.addEventListener("error", () => {
    if (element.getAttribute("src")) setStatus("Couldn't load this example's media. CAD steps are still available.", true);
  });
}
bridge("ready");
