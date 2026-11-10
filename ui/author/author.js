"use strict";
// Authoring panel. Python (core/authoring_fusion.py) owns the draft and
// sends its whole state after every change; this page only shows it and
// sends the designer's edits. The voice is recorded here (Web Audio) and
// streamed to Python in one-second chunks.
const $ = id => document.getElementById(id);
const audio = $("audio");
let S = null;                       // last state from Python
const V = { context: null, stream: null, node: null, source: null, flush: null,
            queue: Promise.resolve(), startedAt: 0, tick: null };
let slice = null;                   // {index, end_ms} while a step's recording plays
let pollTimer = null;

function send(action, payload) {
  if (!(window.adsk && typeof window.adsk.fusionSendData === "function")) return Promise.resolve(null);
  let result;
  try { result = window.adsk.fusionSendData(action, JSON.stringify(payload || {})); }
  catch (error) { return Promise.resolve(null); }
  return Promise.resolve(result).then(raw => {
    try { return raw ? JSON.parse(raw) : null; } catch (_) { return null; }
  });
}
function setStatus(message, error) {
  $("status").textContent = message || "";
  $("status").classList.toggle("error", !!error);
}
function log(message) { send("client_log", { message: String(message) }); }
window.addEventListener("error", e => log("author panel error: " + e.message + " @" + e.lineno));

function el(tag, attrs, text) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}
function clock(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
}
function kindOf(kind) {
  const k = (kind || "").toLowerCase();
  if (/hole|cut/.test(k)) return "cut";
  if (/fillet|chamfer/.test(k)) return "fillet";
  if (/mirror/.test(k)) return "mirror";
  if (/pattern/.test(k)) return "pattern";
  if (/revolve/.test(k)) return "revolve";
  if (/combine/.test(k)) return "combine";
  if (/offset|shell|thicken|draft|sweep|loft/.test(k)) return "modify";
  if (/move/.test(k)) return "move";
  if (/extrude/.test(k)) return "extrude";
  if (/sketch|construction/.test(k)) return "sketch";
  if (/base|paste|import/.test(k)) return "import";
  return "other";
}

// --- edits -------------------------------------------------------------------------------
function edit(action, payload) {
  send(action, payload).then(reply => { if (reply && reply.ok === false) setStatus(reply.error, true); });
}

// --- the steps ---------------------------------------------------------------------------
function renderStep(item, i, count) {
  const li = el("li", { class: "step" + (slice && slice.index === i ? " playing" : "") });
  const head = el("div", { class: "step-head" });
  head.append(el("b", {}, "Step " + (i + 1)), el("span", {}, clock(item.start_ms) + "–" + clock(item.end_ms)),
              el("span", { class: "grow" }));
  if (S.audio) {
    const play = el("button", { class: "play", type: "button", title: "Listen to this step" },
                    slice && slice.index === i ? "■" : "▶");
    play.addEventListener("click", () => playSlice(i));
    head.append(play);
  }
  li.append(head);

  const title = el("input", { class: "step-title", type: "text", placeholder: item.title,
                              "aria-label": "Title of step " + (i + 1) });
  title.value = item.title_edited ? item.title : "";
  title.addEventListener("change", () => edit("rename", { step: i, title: title.value }));
  li.append(title);

  const ops = el("div", { class: "ops" });
  item.features.forEach((f, k) => {
    if (k > 0) {
      const cut = el("button", { class: "cut-here", type: "button",
                                 title: "Split: start a new step at " + f.name }, "✂");
      cut.addEventListener("click", () => edit("split", { step: i, at: k }));
      ops.append(cut);
    }
    ops.append(el("span", { class: "op", "data-kind": kindOf(f.kind), title: f.kind }, f.name));
  });
  li.append(ops);

  if (item.sentences.length) {
    const said = el("ul", { class: "said" });
    item.sentences.forEach((s, k) => {
      const row = el("li");
      row.append(el("time", {}, clock(s.start_ms)), el("span", {}, s.text));
      if (k === 0 && i > 0) {
        const up = el("button", { class: "move", type: "button", title: "This belongs to the previous step" }, "↑ prev");
        up.addEventListener("click", () => edit("move_sentence", { step: i, direction: -1 }));
        row.append(up);
      }
      if (k === item.sentences.length - 1 && i < count - 1) {
        const down = el("button", { class: "move", type: "button", title: "This belongs to the next step" }, "↓ next");
        down.addEventListener("click", () => edit("move_sentence", { step: i, direction: 1 }));
        row.append(down);
      }
      said.append(row);
    });
    li.append(said);
  } else if (S.draft.has_transcript) {
    li.append(el("p", { class: "nothing" }, "Nothing was said during this step."));
  }

  const label = el("div", { class: "why-label" });
  label.append(el("span", {}, "Why (shown to learners)"));
  if (item.text_edited) {
    const back = el("button", { class: "link", type: "button" }, "Use what I said");
    back.addEventListener("click", () => edit("set_text", { step: i, text: null }));
    label.append(back);
  }
  const why = el("textarea", { class: "why" + (item.text_edited ? " edited" : ""), rows: "2",
                               placeholder: "Say or type why this step is done this way" });
  why.value = item.text;
  why.addEventListener("change", () => edit("set_text", { step: i, text: why.value }));
  li.append(label, why);
  return li;
}

function renderSteps() {
  const list = $("steps");
  // Keep the text box being typed in: re-render only when nothing is focused there.
  const focused = document.activeElement;
  if (focused && list.contains(focused) && (focused.tagName === "TEXTAREA" || focused.tagName === "INPUT")) {
    focused.addEventListener("blur", () => setTimeout(renderSteps, 0), { once: true });
    return;
  }
  list.textContent = "";
  if (!S || !S.draft) return;
  const items = S.draft.steps;
  items.forEach((item, i) => {
    list.append(renderStep(item, i, items.length));
    if (i < items.length - 1) {
      const join = el("li", { class: "join" });
      const merge = el("button", { type: "button", title: "One reason covers both steps" }, "⤓ merge into one step");
      merge.addEventListener("click", () => edit("merge", { step: i }));
      join.append(merge);
      list.append(join);
    }
  });
}

function render() {
  if (!S) return;
  $("design").textContent = S.design || "";
  const recording = S.recording;
  $("record").classList.toggle("on", recording);
  $("recordLabel").textContent = recording ? "Stop" : "Record";
  $("voice").disabled = recording;
  $("prepare").hidden = recording;
  $("hint").textContent = recording
    ? (S.voice ? "Recording your voice and your modeling. Think aloud." : "Recording your modeling (no voice).")
    : (S.draft ? "Group the features into reasoning steps. One step can cover several operations."
               : "Press Record, then model in your design and say why you do what you do.");
  const hasDraft = !!S.draft && !recording;
  $("sources").hidden = !hasDraft;
  $("foot").hidden = !hasDraft;
  $("audioName").textContent = S.audio_name || "No recording";
  $("leadRow").hidden = S.audio_lead_s === null || S.audio_lead_s === undefined;
  if (document.activeElement !== $("lead") && S.audio_lead_s !== null) $("lead").value = S.audio_lead_s;
  $("transcribe").disabled = !S.audio || S.transcribing;
  $("transcriptState").textContent = S.transcribing ? "Transcribing…"
    : (S.draft && S.draft.has_transcript ? "Matched to the steps by time" : "None yet");
  if (document.activeElement !== $("title")) $("title").value = S.title || "";
  if (S.audio && audio.dataset.src !== S.audio) { audio.src = S.audio; audio.dataset.src = S.audio; }
  if (!S.audio) { audio.removeAttribute("src"); delete audio.dataset.src; }
  if (S.message !== undefined) setStatus(S.message, /fail|cannot|could not|no longer|error/i.test(S.message || ""));
  clearInterval(pollTimer);
  pollTimer = S.transcribing ? setInterval(() => send("transcribe_poll"), 2000) : null;
  renderSteps();
}

// --- listening to one step ---------------------------------------------------------------
function playSlice(i) {
  if (slice && slice.index === i) { audio.pause(); slice = null; renderSteps(); return; }
  const item = S.draft.steps[i];
  slice = { index: i, end_ms: item.end_ms };
  try { audio.currentTime = item.start_ms / 1000; } catch (_) {}
  audio.play().catch(error => { slice = null; setStatus("Cannot play the recording: " + error.message, true); });
  renderSteps();
}
audio.addEventListener("timeupdate", () => {
  if (slice && audio.currentTime * 1000 >= slice.end_ms) { audio.pause(); slice = null; renderSteps(); }
});
audio.addEventListener("ended", () => { slice = null; renderSteps(); });
audio.addEventListener("loadedmetadata", () => {
  if (Number.isFinite(audio.duration)) send("audio_duration", { duration_ms: Math.round(audio.duration * 1000) });
});

// --- recording ---------------------------------------------------------------------------
// The voice is captured as 16-bit PCM and saved by Python as a WAV file:
// unlike MediaRecorder's WebM, a WAV can be seeked to any step's start.
function pcmToBase64(samples) {
  const bytes = new Uint8Array(samples.buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}
async function startVoice() {
  if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) {
    throw new Error("this Fusion panel cannot use the microphone");
  }
  V.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true } });
  const Context = window.AudioContext || window.webkitAudioContext;
  let context;
  try { context = new Context({ sampleRate: 16000 }); } catch (_) { context = new Context(); }
  V.context = context;
  const source = context.createMediaStreamSource(V.stream);
  const node = context.createScriptProcessor(4096, 1, 1);
  let pending = [], count = 0;
  const flush = () => {
    if (!count) return;
    const out = new Int16Array(count);
    let at = 0;
    for (const part of pending) { out.set(part, at); at += part.length; }
    pending = []; count = 0;
    const data = pcmToBase64(out);
    V.queue = V.queue.then(() => send("audio_chunk", { data })).catch(error => log("audio chunk failed: " + error));
  };
  node.onaudioprocess = event => {
    const input = event.inputBuffer.getChannelData(0);
    const samples = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) samples[i] = Math.max(-1, Math.min(1, input[i])) * 0x7fff;
    pending.push(samples); count += samples.length;
    if (count >= context.sampleRate) flush();           // about one chunk per second
  };
  V.flush = flush;
  V.node = node; V.source = source;
  V.queue = send("audio_start", { mime: "audio/wav", rate: context.sampleRate });
  await V.queue;
  source.connect(node);
  node.connect(context.destination);                    // a ScriptProcessor only runs when connected
}
async function stopVoice() {
  if (!V.context) return;
  try { V.source.disconnect(); V.node.disconnect(); } catch (_) {}
  V.flush();
  await V.queue;                                        // every chunk is in Python
  V.stream.getTracks().forEach(t => t.stop());
  try { await V.context.close(); } catch (_) {}
  V.context = null; V.stream = null; V.node = null; V.source = null;
}
async function toggleRecord() {
  $("record").disabled = true;
  try {
    if (S && S.recording) {
      await stopVoice();
      clearInterval(V.tick);
      await send("record_stop");
    } else {
      const reply = await send("record_start");
      if (reply && reply.ok === false) { setStatus(reply.error, true); return; }
      V.startedAt = performance.now();
      clearInterval(V.tick);
      V.tick = setInterval(() => { $("timer").textContent = clock(performance.now() - V.startedAt); }, 250);
      if ($("voice").checked) {
        try { await startVoice(); }
        catch (error) {
          setStatus("Microphone not available (" + (error.message || error) + "). Your modeling is still "
                    + "recorded; record your voice with another app and import it afterwards.", true);
          log("microphone: " + (error.message || error));
        }
      }
    }
  } finally {
    $("record").disabled = false;
  }
}

// --- wiring ------------------------------------------------------------------------------
$("record").addEventListener("click", toggleRecord);
$("prepare").addEventListener("click", () => edit("prepare"));
$("importAudio").addEventListener("click", () => edit("import_audio"));
$("applyLead").addEventListener("click", () => edit("audio_lead", { seconds: Number($("lead").value) || 0 }));
$("importTranscript").addEventListener("click", () => edit("import_transcript"));
$("transcribe").addEventListener("click", () => edit("transcribe"));
$("title").addEventListener("change", () => edit("set_title", { title: $("title").value }));
// No confirm(): Fusion panels may not show browser dialogs. Ask for a second click.
let regroupArmed = null;
$("regroup").addEventListener("click", () => {
  if (regroupArmed) {
    clearTimeout(regroupArmed); regroupArmed = null;
    $("regroup").textContent = "Regroup";
    edit("regroup");
    return;
  }
  $("regroup").textContent = "Click again: merges, titles and texts are lost";
  regroupArmed = setTimeout(() => { regroupArmed = null; $("regroup").textContent = "Regroup"; }, 4000);
});
$("preview").addEventListener("click", () => edit("preview"));
$("save").addEventListener("click", () => edit("save"));

window.fusionJavaScriptHandler = {
  handle(action, raw) {
    try {
      const data = JSON.parse(raw || "{}");
      if (action === "state") { S = data; render(); }
    } catch (error) {
      log("author panel handler: " + error);
    }
    return "OK";
  },
};
send("ready");
