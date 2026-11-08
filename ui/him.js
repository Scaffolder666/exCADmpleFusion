/* Reasoning Reuse panel. Python owns the model, the examples and the
   notebook; this page renders three views and sends user decisions back:
   * From my model — the user's features (found by HiM) with matched example
     decisions, the user's own value next to the example's options, and
     adopt / adapt / not use / undecided + a note,
   * Across examples — the same question answered by different examples,
   * My notebook — recorded reuse decisions, exportable for research.
   The optional HiM inspect section animates the user's own features. */
"use strict";
const $ = (id) => document.getElementById(id);
const state = { view: null, him: null, playback: null, open: null, focus: null, expanded: {} };
const LABELS = {
  ExtrudeFeature: "Extrude", RevolveFeature: "Revolve", FilletFeature: "Fillet",
  ChamferFeature: "Chamfer", HoleFeature: "Hole", ShellFeature: "Shell",
  CircularPatternFeature: "Circular pattern", RectangularPatternFeature: "Rectangular pattern",
  SweepFeature: "Sweep", OffsetFacesFeature: "Press pull", ThickenFeature: "Thicken",
  DraftFeature: "Draft", ThreadFeature: "Thread", CoilFeature: "Coil", MirrorFeature: "Mirror",
  CombineFeature: "Combine", SplitBodyFeature: "Split body", SplitFaceFeature: "Split face",
  LoftFeature: "Loft", MoveFeature: "Move",
};
const STANCE_LABELS = { adopt: "Adopt", adapt: "Adapt", reject: "Not use", undecided: "Undecided" };
const LEVEL_LABELS = { strong: "type + name match", name: "name match", type: "same feature type" };

function send(action, payload = {}) {
  if (!window.adsk || typeof window.adsk.fusionSendData !== "function") {
    setStatus("Open this panel inside Autodesk Fusion.", true);
    return Promise.resolve();
  }
  return Promise.resolve(window.adsk.fusionSendData(action, JSON.stringify(payload)))
    .catch((error) => setStatus(String(error), true));
}
function setStatus(message, error = false) {
  $("status").textContent = message || "";
  $("status").classList.toggle("error", !!error);
}
function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}
function showTab(name) {
  for (const tab of document.querySelectorAll(".tabs button")) {
    const active = tab.dataset.panel === name;
    tab.setAttribute("aria-selected", String(active));
    $("panel-" + tab.dataset.panel).hidden = !active;
  }
}
for (const tab of document.querySelectorAll(".tabs button")) tab.addEventListener("click", () => showTab(tab.dataset.panel));

function illustrative(source) {
  return ["mockup", "demo"].includes(String(source || "").toLowerCase());
}

/* ---------- a decision card (used in "From my model") ---------- */
function decisionCard(match, feature) {
  const ref = match.ref;
  const card = el("article", { class: "decision" });
  if (state.focus && state.focus.example_id === ref.example_id && state.focus.step_id === ref.step_id) card.classList.add("focus");
  const from = el("div", { class: "from" });
  from.append(el("span", {}, ref.example_title + " · step " + (ref.step_index + 1) + " · " + ref.step_title),
              el("span", { class: "level " + match.level }, LEVEL_LABELS[match.level] || match.level));
  card.appendChild(from);
  card.appendChild(el("h3", {}, ref.question));
  if (ref.criteria.length) {
    const ul = el("ul", { class: "criteria", "aria-label": "Criteria the author considered" });
    for (const c of ref.criteria) ul.appendChild(el("li", {}, c));
    card.appendChild(ul);
  }
  const near = match.comparison && match.comparison.nearest_option;
  const ol = el("ol", { class: "choices" });
  for (const option of ref.options) {
    const li = el("li", { class: (option.chosen ? "chosen " : "") + (option.label === near ? "near" : "") },
      (option.chosen ? "✓ " : "") + option.label + (option.value ? " · " + option.value : ""));
    if (option.note) li.appendChild(el("small", {}, option.note));
    ol.appendChild(li);
  }
  card.appendChild(ol);
  if (match.comparison) {
    const c = match.comparison;
    const box = el("div", { class: "compare" });
    box.append(el("span", {}, "Your " + c.user_parameter + ": " + c.user_value +
      (c.user_expression && c.user_expression !== c.user_value ? " (" + c.user_expression + ")" : "") + " — example: " + c.example_value +
      (near ? ". Closest option: " + near : "")));
    if (c.note) box.appendChild(el("small", {}, c.note));
    card.appendChild(box);
  }
  if (ref.rationale) {
    const quote = el("blockquote", {}, ref.rationale);
    card.appendChild(quote);
    if (illustrative(ref.source)) card.appendChild(el("div", { class: "tag" }, "Illustrative reasoning — not a real designer's statement"));
  }
  card.appendChild(el("div", { class: "why" }, "Why suggested: " + match.reasons.join(" ")));
  card.appendChild(stanceEditor(ref, feature, match.stance, match.note));
  return card;
}

function stanceEditor(ref, feature, current, note) {
  const wrap = el("div");
  const buttons = el("div", { class: "stances", role: "group", "aria-label": "What will you do with this reasoning?" });
  const text = el("textarea", { placeholder: "In my design… (why you adopt, adapt or don't use it)", "aria-label": "Your reasoning" });
  text.value = note || "";
  let chosen = current || null;
  for (const stance of ["adopt", "adapt", "reject", "undecided"]) {
    const b = el("button", { type: "button", "aria-pressed": String(stance === chosen) }, STANCE_LABELS[stance]);
    b.addEventListener("click", () => {
      chosen = stance;
      for (const other of buttons.children) other.setAttribute("aria-pressed", String(other === b));
    });
    buttons.appendChild(b);
  }
  const row = el("div", { class: "row" });
  const save = el("button", { type: "button", class: "primary" }, "Save to notebook");
  save.addEventListener("click", () => {
    if (!chosen) { setStatus("Choose adopt, adapt, not use or undecided first.", true); return; }
    send("reuse_record", { example_id: ref.example_id, step_id: ref.step_id,
      feature_key: feature ? feature.key : "", stance: chosen, note: text.value });
  });
  const watch = el("button", { type: "button" }, "▶ Watch in example");
  watch.addEventListener("click", () => send("reuse_watch", { example_id: ref.example_id, step_id: ref.step_id }));
  row.append(save, watch);
  wrap.append(buttons, text, row);
  return wrap;
}

/* ---------- views ---------- */
function renderMine() {
  const root = $("mine");
  root.replaceChildren();
  const view = state.view;
  if (!view || !view.features.length) {
    root.appendChild(el("div", { class: "empty" },
      "Select a face, edge or vertex of your own model. Features without matching decisions are still listed in the inspect section below."));
    return;
  }
  let shown = 0;
  for (const item of view.features) {
    const feature = item.feature;
    if (!item.matches.length) continue;
    shown++;
    const section = el("section", { class: "my-feature" });
    const header = el("header");
    header.append(el("span", { class: "chip", "data-kind": feature.kind }, feature.name),
                  el("span", { class: "role" }, (LABELS[feature.kind] || feature.kind) + " · " + feature.role));
    section.appendChild(header);
    const key = feature.key || feature.name;
    const strong = item.matches.filter((m) => m.level !== "type");
    const weak = item.matches.filter((m) => m.level === "type");
    const visible = state.expanded[key] ? item.matches : (strong.length ? strong : weak.slice(0, 1));
    for (const match of visible) section.appendChild(decisionCard(match, feature));
    const hidden = item.matches.length - visible.length;
    if (hidden > 0) {
      const more = el("button", { type: "button", class: "more" }, "+ " + hidden + " more decision(s) made with " + (LABELS[feature.kind] || feature.kind));
      more.addEventListener("click", () => { state.expanded[key] = true; renderMine(); });
      section.appendChild(more);
    }
    root.appendChild(section);
  }
  if (!shown) root.appendChild(el("div", { class: "empty" },
    "None of the open examples has a decision for these features. Try another face, or open more examples."));
}

function renderTopics() {
  const root = $("topics");
  root.replaceChildren();
  const topics = state.view ? state.view.topics : [];
  if (!topics.length) { root.appendChild(el("div", { class: "empty" }, "Open design examples to compare their decisions.")); return; }
  for (const topic of topics) {
    const section = el("section", { class: "topic" });
    if (state.focus && state.focus.topic === topic.topic) section.id = "focusTopic";
    section.appendChild(el("h3", {}, topic.question));
    const answers = el("div", { class: "answers" });
    for (const answer of topic.answers) {
      const card = el("div", { class: "answer" });
      card.appendChild(el("div", { class: "who" }, answer.example_title + " · step " + (answer.step_index + 1)));
      card.appendChild(el("div", { class: "pick" }, (answer.choice || "—") + (answer.value ? " · " + answer.value : "")));
      if (answer.note) card.appendChild(el("p", {}, answer.note));
      if (answer.rationale) card.appendChild(el("p", {}, "“" + answer.rationale + "”"));
      const ref = { example_id: answer.example_id, step_id: answer.step_id };
      const stance = entryStance(ref);
      const toggle = el("button", { type: "button", class: "more" },
        stance ? "Your stance: " + STANCE_LABELS[stance] + " — edit" : "Record my stance…");
      toggle.addEventListener("click", () => { toggle.replaceWith(stanceEditor(ref, null, stance, entryNote(ref))); });
      card.appendChild(toggle);
      answers.appendChild(card);
    }
    section.appendChild(answers);
    root.appendChild(section);
  }
  const focus = $("focusTopic");
  if (focus) focus.scrollIntoView({ block: "start" });
}
function entryFor(ref) {
  return (state.view?.notebook || []).find((e) => e.example_id === ref.example_id && e.step_id === ref.step_id && !e.user_feature_key);
}
function entryStance(ref) { return entryFor(ref)?.stance || null; }
function entryNote(ref) { return entryFor(ref)?.note || ""; }

function renderNotebook() {
  const view = state.view;
  const entries = view ? view.notebook : [];
  $("noteCount").textContent = String(entries.length);
  const summary = $("summary");
  summary.replaceChildren();
  if (view) for (const [stance, count] of Object.entries(view.summary)) summary.appendChild(el("span", {}, STANCE_LABELS[stance] + ": " + count));
  const root = $("notebook");
  root.replaceChildren();
  if (!entries.length) { root.appendChild(el("div", { class: "empty" }, "Nothing recorded yet. Save a stance on any decision.")); return; }
  for (const entry of [...entries].reverse()) {
    const card = el("article", { class: "entry" });
    card.appendChild(el("div", { class: "stance " + entry.stance }, STANCE_LABELS[entry.stance] || entry.stance));
    card.appendChild(el("p", {}, entry.question));
    card.appendChild(el("small", {}, entry.example_title + " · " + entry.step_title + " — chose: " + (entry.example_choice || "—")));
    if (entry.user_feature) card.appendChild(el("p", {}, "My feature: " + entry.user_feature + (entry.user_value ? " (" + entry.user_value + ")" : "")));
    if (entry.note) card.appendChild(el("p", {}, "“" + entry.note + "”"));
    card.appendChild(el("small", {}, entry.updated_at));
    const row = el("div", { class: "row" });
    const watch = el("button", { type: "button" }, "▶ Revisit");
    watch.addEventListener("click", () => send("reuse_watch", { example_id: entry.example_id, step_id: entry.step_id }));
    const remove = el("button", { type: "button" }, "Delete");
    remove.addEventListener("click", () => send("reuse_remove", { id: entry.id }));
    row.append(watch, remove);
    card.appendChild(row);
    root.appendChild(card);
  }
}

function renderView() { renderMine(); renderTopics(); renderNotebook(); }

/* ---------- HiM inspect section ---------- */
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
      input.addEventListener("change", () => send("him_set_parameter", { position, name: p.name, expression: input.value }));
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
  animate.disabled = !(state.him && state.him.inspect);
  actions.append(edit, animate);
  box.appendChild(actions);
  return box;
}
function renderHiM() {
  const list = $("features");
  list.textContent = "";
  const result = state.him;
  if (!result) return;
  const current = state.playback ? state.playback.position : -1;
  result.features.forEach((item, position) => {
    const li = el("li", { class: "feature" + (position === current && result.inspect ? " current" : ""), "data-kind": item.kind });
    const button = el("button", { class: "capsule", type: "button", "aria-expanded": String(state.open === position) });
    const name = el("span", { class: "name" }, item.name);
    if (item.level) name.appendChild(el("span", { class: "tagline" }, "more ·" + item.level));
    if (item.mode === "none") name.appendChild(el("span", { class: "tagline" }, "not animated"));
    button.append(name, el("span", { class: "meta" }, LABELS[item.kind] || item.kind));
    button.addEventListener("click", () => { state.open = state.open === position ? null : position; renderHiM(); });
    li.appendChild(button);
    const bar = el("div", { class: "progress" });
    const fill = el("span");
    if (position === current && state.playback && result.inspect) fill.style.width = Math.round(state.playback.progress * 100) + "%";
    bar.appendChild(fill);
    li.appendChild(bar);
    if (state.open === position) li.appendChild(renderDetails(item, position));
    list.appendChild(li);
  });
  const bases = $("bases");
  bases.textContent = "";
  for (const b of result.bases) bases.appendChild(el("div", {}, "Built on " + b.name + (b.on_ground_plane ? " (ground plane)" : " (on a face)")));
  $("showMore").hidden = !result.can_show_more;
  for (const id of ["back", "playPause", "replay", "forward"]) $(id).disabled = !result.inspect;
  $("inspectMode").checked = !!result.inspect;
}
function updatePlayback(playback) {
  state.playback = playback;
  $("playPause").innerHTML = playback.playing ? "&#10074;&#10074;" : "&#9654;";
  $("playPause").setAttribute("aria-label", playback.playing ? "Pause" : "Play");
  renderHiM();
}

$("playPause").addEventListener("click", () => send("him_command", { name: state.playback && state.playback.playing ? "pause" : "play" }));
$("replay").addEventListener("click", () => send("him_command", { name: "replay" }));
$("forward").addEventListener("click", () => send("him_command", { name: "forward" }));
$("back").addEventListener("click", () => send("him_command", { name: "backward" }));
$("showMore").addEventListener("click", () => send("him_show_more"));
$("speed").addEventListener("input", () => { $("speedValue").textContent = $("speed").value; });
$("speed").addEventListener("change", () => send("him_command", { name: "speed", value: Number($("speed").value) }));
$("dim").addEventListener("change", () => send("him_command", { name: "dim", value: $("dim").checked }));
$("auto").addEventListener("change", () => send("him_command", { name: "auto", value: $("auto").checked }));
$("inspectMode").addEventListener("change", () => {
  if (state.him) state.him.inspect = $("inspectMode").checked;
  send("him_command", { name: "inspect", value: $("inspectMode").checked });
  renderHiM();
});
$("exportJson").addEventListener("click", () => send("reuse_export", { format: "json" }));
$("exportCsv").addEventListener("click", () => send("reuse_export", { format: "csv" }));
$("importExample").addEventListener("click", () => send("reuse_import"));

window.fusionJavaScriptHandler = {
  handle(action, raw) {
    try {
      const payload = JSON.parse(raw || "{}");
      if (action === "reuse_view") {
        state.view = payload;
        state.focus = payload.focus || null;
        $("selection").textContent = payload.selection ? "Selected " + payload.selection.toLowerCase() + " in your model" : "Select a face, edge or vertex of your model.";
        renderView();
        if (payload.focus) showTab("topics");
        else if (payload.selection) {
          const matched = payload.features.filter((f) => f.matches.length).length;
          setStatus(payload.features.length + " feature(s) made this geometry · " + matched + " with example decisions");
        }
      } else if (action === "him_result") {
        state.him = payload;
        state.open = null;
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
