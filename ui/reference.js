/* Version A — History in Motion style tutorial.
   Same examples, reasoning and playback abilities as version B; different
   organisation: the example plays in its own interactive 3D viewport and a
   narrow vertical history panel controls it.

   Playback follows HiM (Veuskens et al., SCF 2023):
   * no selection: the whole design process plays in order (the tutorial);
   * clicking the reference model filters the history to the steps that made
     or changed that part, and plays them newest first, so the clip starts
     from the model the user is looking at;
   * "Show more" adds the steps those build on, one level per click;
   * step backward plays the current step in reverse;
   * geometry the current step did not change is drawn transparent. */
"use strict";
const $ = (id) => document.getElementById(id);
const audio = $("audio");
const S = {
  example: null, geometry: [], index: 0, clip: [], pos: 0, elapsed: 0, playing: false,
  direction: 1, continuous: true, speed: 1, filtered: false, changed: [], more: [], picked: null,
  last: 0, cue: -1, filterIndex: null, fresh: true,
};
let viewer = null;

function bridge(action, payload = {}) {
  if (!window.adsk || typeof window.adsk.fusionSendData !== "function") return Promise.resolve();
  return Promise.resolve(window.adsk.fusionSendData(action, JSON.stringify(payload))).catch((e) => status(String(e), true));
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
  const tool = ((item.operation && item.operation.tool) || "").toLowerCase();
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
  S.fresh = true;     // selected but not played yet: show the step's result
  bridge("set_step", { index: i });
}
function stopAudio() { audio.pause(); }
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
  S.fresh = false;
  S.continuous = continuous;
  S.last = performance.now();
  syncAudio(true);
  render();
}
function pause() {
  S.playing = false;
  stopAudio();
  if ("speechSynthesis" in window) speechSynthesis.cancel();
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

/* ---------- HiM filtering by picking the reference model ---------- */
function onPick(point) {
  if (!point || !S.filterIndex) return;
  // Compare only the steps up to the state on screen, as HiM does for the current model.
  const changed = ExcadmpleHistoryFilter.changedAt(S.filterIndex, point, S.index);
  if (!changed.length) { status("No step changed the geometry at that point."); return; }
  S.filtered = true;
  S.picked = point;
  S.changed = changed;
  S.more = [];
  setClip(false);
  S.elapsed = 0;
  S.direction = 1;
  status("");
  play(true);       // HiM renders the clip immediately upon selection
}
function showMore() {
  const more = ExcadmpleHistoryFilter.buildsOn(S.filterIndex, S.changed.concat(S.more));
  if (!more.length) { status("Nothing earlier to add: these steps build on no other step."); return; }
  S.more = S.more.concat(more);
  setClip(true);
  render();
}
function showAll() {
  S.filtered = false;
  S.changed = [];
  S.more = [];
  if (viewer) viewer.clearPick();
  setClip(true);
  render();
}

/* ---------- rendering ---------- */
function reasoningSource(item) {
  const src = String((item.reasoning || {}).source || "").toLowerCase();
  if (src === "think_aloud") return "Think-aloud while modeling";
  if (src === "mockup" || src === "demo" || src === "illustrative") return "Illustrative only";
  return src ? src : "Source not stated";
}
function stepName(id) {
  const i = steps().findIndex((s) => s.id === id);
  return i < 0 ? id : (i + 1) + " " + steps()[i].title;
}
function card(item) {
  const box = el("div", { class: "card" });
  if (item.goal) box.appendChild(el("div", {}, item.goal));
  const why = el("h4");
  why.append(el("span", {}, "Why this decision?"), el("span", { class: "src" }, reasoningSource(item)));
  box.appendChild(why);
  box.appendChild(el("blockquote", {}, (item.reasoning && item.reasoning.text) || "No reasoning recorded for this step."));
  const cues = item.cues || [];
  let active = -1;
  cues.forEach((c, i) => { if (c.at_ms <= S.elapsed) active = i; });
  if ($("captions").checked && active >= 0) box.appendChild(el("p", { class: "cue" }, "“" + cues[active].label + "”"));
  if (active !== S.cue) {
    S.cue = active;
    if (S.playing && active >= 0 && $("narration").checked && !(item.media && item.media.audio) && "speechSynthesis" in window) {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(cues[active].label);
      u.rate = Math.min(2, Math.max(0.5, S.speed));
      speechSynthesis.speak(u);
    }
  }
  const d = item.decision;
  if (d) {
    box.appendChild(el("h4", {}, "The decision"));
    box.appendChild(el("p", { class: "question" }, d.question));
    const ol = el("ol");
    for (const o of d.options || []) {
      const li = el("li", { class: o.chosen ? "chosen" : "" }, (o.chosen ? "✓ " : "") + o.label + (o.value ? " · " + o.value : ""));
      if (o.note) li.appendChild(el("small", {}, o.note));
      ol.appendChild(li);
    }
    box.appendChild(ol);
  }
  if (item.scope) {
    const p = el("p", { class: "scope" });
    p.append(el("b", {}, item.scope.kind === "general" ? "General practice" : "Specific to this designer's goal"),
             document.createTextNode(item.scope.note ? " — " + item.scope.note : ""));
    box.appendChild(p);
  }
  const said = item.depends_on || [];
  const derived = (item.depends_on_derived || []).filter((x) => !said.includes(x));
  if (said.length || derived.length) {
    const parts = [];
    if (said.length) parts.push("Builds on " + said.map(stepName).join(", ") + " (designer)");
    if (derived.length) parts.push("uses geometry from " + derived.map(stepName).join(", ") + " (CAD timeline)");
    box.appendChild(el("p", { class: "deps" }, parts.join("; ") + "."));
  }
  const op = item.operation || {};
  box.appendChild(el("h4", {}, "How it was modeled"));
  box.appendChild(el("div", {}, [op.tool, op.instruction].filter(Boolean).join(" — ")));
  if ((op.parameters || []).length) {
    const params = el("div", { class: "params" });
    for (const p of op.parameters) params.appendChild(el("span", {}, p.name + " " + p.value));
    box.appendChild(params);
  }
  if (d) {
    const compare = el("button", { class: "compare", type: "button" }, "Compare with my design & other examples →");
    compare.addEventListener("click", (e) => { e.stopPropagation(); bridge("compare_decision"); });
    box.appendChild(compare);
  }
  return box;
}
function render() {
  if (!S.example) return;
  const progress = Math.max(0, Math.min(1, S.elapsed / duration()));
  if (viewer) {
    viewer.setGhost($("ghost").checked);
    viewer.show(S.index, S.fresh ? 1 : progress, S.fresh ? null : S.elapsed);
  }
  $("play").innerHTML = S.playing ? "&#10074;&#10074;" : "&#9654;";
  $("play").setAttribute("aria-label", S.playing ? "Pause" : "Play");
  $("clock").textContent = secs(S.elapsed) + " / " + secs(duration());
  const mode = $("mode");
  mode.classList.toggle("filtered", S.filtered);
  $("modeText").textContent = S.filtered
    ? S.clip.length + " step(s) made or changed the picked part · newest first"
    : "Whole design process · " + steps().length + " steps";
  $("showMore").hidden = !S.filtered;
  $("showAll").hidden = !S.filtered;
  const rail = $("rail");
  rail.replaceChildren();
  S.clip.forEach((i) => {
    const item = steps()[i];
    const li = el("li", { class: "step" + (i === S.index ? " current" : ""), "data-kind": kindOf(item) });
    const button = el("button", { class: "capsule", type: "button" });
    const name = el("span", { class: "name" }, (i + 1) + "  " + item.title);
    if (S.filtered) name.appendChild(el("span", { class: "tag" }, S.changed.includes(i) ? "changed here" : "builds on"));
    button.append(name, el("span", { class: "meta" }, (item.operation && item.operation.tool) || ""));
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
  const brief = data.brief;
  $("brief").hidden = !brief;
  if (brief) {
    $("briefGoal").textContent = brief.goal;
    $("briefMore").textContent = [brief.users && "For " + brief.users,
      (brief.constraints || []).length && brief.constraints.join(" · "),
      data.designer && "Designer: " + data.designer].filter(Boolean).join(" — ");
  }
  render();
}
window.fusionJavaScriptHandler = {
  handle(action, raw) {
    try {
      const payload = JSON.parse(raw || "{}");
      if (action === "example") loadExample(payload);
      else if (action === "reference_geometry") {
        S.geometry = payload.steps || [];
        S.filterIndex = ExcadmpleHistoryFilter.buildIndex(
          S.geometry.map((g, i) => Object.assign({}, g, { id: steps()[i] ? steps()[i].id : String(i),
            depends_on: steps()[i] && steps()[i].depends_on, depends_on_derived: steps()[i] && steps()[i].depends_on_derived })));
        if (viewer) viewer.setExample(S.geometry);
        render();
      } else if (action === "library") {
        const select = $("exampleSwitch");
        select.replaceChildren();
        for (const item of payload.examples || []) {
          const o = el("option", { value: item.id }, item.title);
          if (item.active) o.selected = true;
          select.appendChild(o);
        }
        $("closeExample").disabled = (payload.examples || []).length <= 1;
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
$("showMore").addEventListener("click", showMore);
$("showAll").addEventListener("click", showAll);
$("resetView").addEventListener("click", () => viewer && viewer.resetView());
$("speed").addEventListener("input", () => { S.speed = Number($("speed").value); $("speedValue").textContent = S.speed + "×"; syncAudio(true); });
$("ghost").addEventListener("change", render);
$("captions").addEventListener("change", render);
$("narration").addEventListener("change", () => { if ("speechSynthesis" in window) speechSynthesis.cancel(); });
$("exampleSwitch").addEventListener("change", (e) => { pause(); bridge("switch_example", { id: e.target.value }); });
$("closeExample").addEventListener("click", () => { pause(); bridge("close_example", { id: $("exampleSwitch").value }); });
$("import").addEventListener("click", () => { pause(); bridge("open_package"); });
$("demo").addEventListener("click", () => { pause(); bridge("load_demo"); });
$("extractDraft").addEventListener("click", () => { pause(); bridge("extract_draft"); });

try {
  viewer = new window.ReferenceViewer($("viewer"));
  viewer.onPick = onPick;
} catch (error) {
  status("3D reference viewport unavailable: " + error.message, true);
}
requestAnimationFrame(tick);
bridge("ready");
