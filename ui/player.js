/* exCADmple's reference timeline is independent of Fusion's feature timeline. */
"use strict";

const $ = (id) => document.getElementById(id);
const state = { example: null, index: 0, elapsed: 0, playing: false, startedAt: 0, raf: 0, cueIndex: -1 };
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
function step() { return state.example?.steps[state.index] || null; }
function duration() { return step()?.duration_ms || 8000; }
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
    const button = document.createElement("button");
    button.type = "button";
    button.className = "step-card" + (i === state.index ? " active" : "");
    button.setAttribute("aria-current", i === state.index ? "step" : "false");
    button.setAttribute("aria-label", "Step " + (i + 1) + ": " + item.title);
    const num = document.createElement("span");
    num.className = "num";
    num.textContent = String(i + 1).padStart(2, "0");
    const labels = document.createElement("span");
    labels.className = "step-labels";
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = item.title;
    labels.appendChild(label);
    if (item.goal) {
      const sub = document.createElement("span");
      sub.className = "step-goal";
      sub.textContent = item.goal;
      labels.appendChild(sub);
    }
    const indicator = document.createElement("span");
    indicator.className = "step-indicator";
    indicator.textContent = i === state.index ? "VIEWING" : "›";
    button.append(num, labels, indicator);
    button.addEventListener("click", () => selectStep(i));
    rail.appendChild(button);
  });
  const active = rail.children[state.index];
  if (active) active.scrollIntoView({block:"nearest", inline:"nearest"});
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
  $("geometryStatus").textContent = hasStepGeometry ? "3D step available" :
    (state.example?.preview_data_uri ? "Final preview only" : "No step geometry");
  $("geometryStatus").classList.toggle("none", !hasStepGeometry);
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
  $("mediaEvidence").textContent = [media.video && "Video", media.audio && "Audio"]
    .filter(Boolean).join(" + ") || "Step metadata";
  if (!media.video && !preview) {
    $("noVideo").querySelector("strong").textContent = hasStepGeometry ?
      "3D reference in Fusion" : "No recorded visuals for this step";
    $("noVideo").querySelector("span").textContent = hasStepGeometry ?
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
  const cues = step()?.cues || [];
  let active = -1;
  cues.forEach((cue, i) => { if (cue.at_ms <= state.elapsed) active = i; });
  if (active !== state.cueIndex) {
    state.cueIndex = active;
    $("cueText").textContent = active >= 0 ? cues[active].label : (step()?.operation?.instruction || "Inspect the author's actions.");
  }
}
function pause() {
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
  renderDetails();
  bridge("set_step", {index});
  if (keepPlaying) play();
}
function seek(ms) {
  state.elapsed = Math.max(0, Math.min(duration(), ms));
  state.startedAt = performance.now() - state.elapsed;
  for (const element of [video, audio]) {
    if (element.getAttribute("src")) {
      try { element.currentTime = state.elapsed / 1000; } catch (_) {}
    }
  }
  renderTime();
}
function play() {
  if (!step()) return;
  if (state.elapsed >= duration()) seek(0);
  state.playing = true;
  state.startedAt = performance.now() - state.elapsed;
  $("play").innerHTML = "Ⅱ <span>Pause</span>";
  $("play").setAttribute("aria-label", "Pause");
  playMedia();
  tick();
}
function tick() {
  if (!state.playing) return;
  // The HTML media clock is authoritative when available; otherwise use a
  // monotonic wall clock. Geometry only changes between steps, not at 60 fps.
  const master = mediaMaster();
  const mediaReady = master && master.readyState >= 2 && !master.paused;
  state.elapsed = mediaReady ? master.currentTime * 1000 : performance.now() - state.startedAt;
  if (state.elapsed >= duration() - 30) {
    if (state.index < state.example.steps.length - 1) selectStep(state.index + 1, true);
    else { state.elapsed = duration(); renderTime(); pause(); }
    return;
  }
  if (video.getAttribute("src") && audio.getAttribute("src") && mediaReady &&
      Math.abs(audio.currentTime - video.currentTime) > 0.35 && audio.readyState >= 1) {
    audio.currentTime = video.currentTime;
  }
  renderTime();
  state.raf = requestAnimationFrame(tick);
}
function loadExample(data) {
  pause();
  state.example = data;
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
      else if (action === "step") {
        if (payload.index !== state.index && state.example) selectStep(payload.index);
      } else if (action === "status") setStatus(payload.message, payload.error);
      return "OK";
    } catch (error) {
      setStatus(String(error), true);
      return "ERROR";
    }
  }
};
$("import").addEventListener("click", () => { pause(); bridge("open_package"); });
$("demo").addEventListener("click", () => { pause(); bridge("load_demo"); });
$("play").addEventListener("click", () => state.playing ? pause() : play());
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
