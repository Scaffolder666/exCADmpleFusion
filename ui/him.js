/* History in Motion control panel. Python owns the model and the clock; this
   page shows the filtered features (newest first), highlights the feature
   being animated and sends playback / edit commands. */
"use strict";
const $ = (id) => document.getElementById(id);
const state = { result: null, playback: null, open: null };
const LABELS = {
  ExtrudeFeature: "Extrude", RevolveFeature: "Revolve", FilletFeature: "Fillet",
  ChamferFeature: "Chamfer", HoleFeature: "Hole", ShellFeature: "Shell",
  CircularPatternFeature: "Circular pattern", RectangularPatternFeature: "Rectangular pattern",
  SweepFeature: "Sweep", OffsetFacesFeature: "Press pull", ThickenFeature: "Thicken",
  DraftFeature: "Draft", ThreadFeature: "Thread", CoilFeature: "Coil", MirrorFeature: "Mirror",
  CombineFeature: "Combine", SplitBodyFeature: "Split body", SplitFaceFeature: "Split face",
  LoftFeature: "Loft", MoveFeature: "Move",
};

function send(action, payload = {}) {
  if (!window.adsk || typeof window.adsk.fusionSendData !== "function") {
    setStatus("Open this panel inside Autodesk Fusion.", true);
    return Promise.resolve();
  }
  return Promise.resolve(window.adsk.fusionSendData(action, JSON.stringify(payload)))
    .catch((error) => setStatus(String(error), true));
}

function setStatus(message, error = false) {
  $("status").textContent = message;
  $("status").classList.toggle("error", !!error);
}

function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

function modeLabel(mode) {
  return mode === "parameter" ? "parameter animation" : mode === "fade" ? "fade / scale" : "no animation";
}

function renderDetails(item, position) {
  const box = el("div", { class: "details" });
  box.appendChild(el("div", {}, "Timeline #" + (item.timeline_index + 1) + " · " + item.role + " · " + modeLabel(item.mode)));
  if (item.parameters.length) {
    const table = el("table");
    for (const p of item.parameters) {
      const row = el("tr");
      row.appendChild(el("td", {}, p.name));
      const cell = el("td");
      const input = el("input", { value: p.expression, "aria-label": p.name });
      input.addEventListener("change", () =>
        send("him_set_parameter", { position, name: p.name, expression: input.value }));
      cell.appendChild(input);
      row.appendChild(cell);
      table.appendChild(row);
    }
    box.appendChild(table);
  }
  const actions = el("div", { class: "actions" });
  const edit = el("button", { type: "button" }, "Edit feature");
  edit.addEventListener("click", () => send("him_edit", { position }));
  const animate = el("button", { type: "button" }, "Animate this");
  animate.addEventListener("click", () => send("him_command", { name: "select", value: position }));
  actions.append(edit, animate);
  box.appendChild(actions);
  return box;
}

function render() {
  const list = $("features");
  list.textContent = "";
  const result = state.result;
  if (!result) return;
  const current = state.playback ? state.playback.position : -1;
  result.features.forEach((item, position) => {
    const li = el("li", { class: "feature" + (position === current ? " current" : ""), "data-kind": item.kind });
    const button = el("button", { class: "capsule", type: "button", "aria-expanded": String(state.open === position) });
    const name = el("span", { class: "name" }, item.name);
    if (item.level) name.appendChild(el("span", { class: "tag" }, "more ·" + item.level));
    if (item.mode === "none") name.appendChild(el("span", { class: "tag" }, "not animated"));
    button.append(name, el("span", { class: "meta" }, LABELS[item.kind] || item.kind));
    button.addEventListener("click", () => { state.open = state.open === position ? null : position; render(); });
    li.appendChild(button);
    const bar = el("div", { class: "progress" });
    const fill = el("span");
    if (position === current && state.playback) fill.style.width = Math.round(state.playback.progress * 100) + "%";
    bar.appendChild(fill);
    li.appendChild(bar);
    if (state.open === position) li.appendChild(renderDetails(item, position));
    list.appendChild(li);
  });
  const bases = $("bases");
  bases.textContent = "";
  for (const b of result.bases) {
    bases.appendChild(el("div", {}, "Built on " + b.name + (b.on_ground_plane ? " (ground plane)" : " (on a face)")));
  }
  $("showMore").hidden = !result.can_show_more;
}

function updatePlayback(playback) {
  state.playback = playback;
  $("playPause").innerHTML = playback.playing ? "&#10074;&#10074;" : "&#9654;";
  $("playPause").setAttribute("aria-label", playback.playing ? "Pause" : "Play");
  render();
}

$("playPause").addEventListener("click", () =>
  send("him_command", { name: state.playback && state.playback.playing ? "pause" : "play" }));
$("replay").addEventListener("click", () => send("him_command", { name: "replay" }));
$("forward").addEventListener("click", () => send("him_command", { name: "forward" }));
$("back").addEventListener("click", () => send("him_command", { name: "backward" }));
$("showMore").addEventListener("click", () => send("him_show_more"));
$("speed").addEventListener("input", () => { $("speedValue").textContent = $("speed").value; });
$("speed").addEventListener("change", () => send("him_command", { name: "speed", value: Number($("speed").value) }));
$("dim").addEventListener("change", () => send("him_command", { name: "dim", value: $("dim").checked }));
$("auto").addEventListener("change", () => send("him_command", { name: "auto", value: $("auto").checked }));

window.fusionJavaScriptHandler = {
  handle(action, raw) {
    try {
      const payload = JSON.parse(raw || "{}");
      if (action === "him_result") {
        state.result = payload;
        state.open = null;
        $("selection").textContent = payload.selection ? "Selected " + payload.selection.toLowerCase() : "";
        const n = payload.features.length;
        setStatus(n ? n + " relevant feature" + (n === 1 ? "" : "s") + ", newest first" +
          (payload.analysis_seconds !== undefined ? " · analysed in " + payload.analysis_seconds + " s" : "") +
          (payload.truncated ? " · search truncated" : "")
          : "No modeling features found for this geometry.");
        updatePlayback(payload.playback);
      } else if (action === "him_playback") {
        updatePlayback(payload);
      } else if (action === "status") {
        setStatus(payload.message, payload.error);
      }
    } catch (error) {
      setStatus(String(error), true);
    }
    return "OK";
  },
};
send("him_ready");
