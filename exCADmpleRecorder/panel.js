"use strict";

const $ = id => document.getElementById(id);
const player = $("audio");
let state;
let capture;
let busy = false;
let clipEnd = null;
let poll;
let stepRows = [];
const voicePlayer = new Audio();
let activeVoice = null;
let requestingMic = false;
let recordingSince = null;
let ticker;

function updateDraftBar() {
  if (state?.capturing) recordingSince ??= Date.now();
  else recordingSince = null;
  const pending = Boolean(state?.starting_capture || requestingMic);
  $("draft-bar").hidden = !pending && !state?.draft;
  $("draft-label").textContent = state?.capturing ? "● Recording"
    : pending ? "Starting microphone" : "Voice message ready";
  $("draft-time").textContent = recordingSince === null
    ? (state?.draft_duration_ms ? durationLabel(state.draft_duration_ms) : "")
    : Math.floor((Date.now() - recordingSince) / 1000) + " s";
  $("preview-draft").hidden = !state?.draft || pending ||
    (!state.capturing && !state.draft_duration_ms);
  $("preview-draft").textContent = (state?.native_microphone ? state.playing_voice === "draft"
    : activeVoice === "draft" && !voicePlayer.paused) ? "Stop"
    : state?.capturing ? "Stop and Preview" : "Preview";
  if (recordingSince !== null && !ticker) {
    ticker = setInterval(updateDraftBar, 250);
  } else if (recordingSince === null && ticker) {
    clearInterval(ticker);
    ticker = null;
  }
}

function updateVoiceBars() {
  for (const bar of document.querySelectorAll("button.voice-bar")) {
    const native = state?.native_microphone;
    const playing = native ? bar.dataset.key === String(state.playing_voice)
      : bar.dataset.key === activeVoice && !voicePlayer.paused;
    bar.textContent = (playing ? (native ? "■ Stop · " : "Pause · ") : "▶ Play · ") + bar.dataset.duration;
    bar.setAttribute("aria-label", (playing ? (native ? "Stop " : "Pause ") : "Play ") + bar.dataset.title);
    bar.setAttribute("aria-pressed", String(playing));
  }
  updateDraftBar();
}

voicePlayer.addEventListener("play", updateVoiceBars);
voicePlayer.addEventListener("pause", updateVoiceBars);
voicePlayer.addEventListener("ended", () => { activeVoice = null; updateVoiceBars(); });
voicePlayer.addEventListener("error", () => status("Could not play this message. Check its WAV file in the session folder.", true));

async function send(action, payload = {}) {
  const bridge = window.adsk;
  if (typeof bridge?.fusionSendData !== "function") {
    throw new Error("Fusion is not ready to connect yet.");
  }
  const raw = await bridge.fusionSendData(action, JSON.stringify(payload));
  const reply = JSON.parse(raw);
  if (!reply.ok) {
    const error = new Error(reply.error);
    if ("recording" in reply) error.state = reply;
    throw error;
  }
  return reply;
}

function status(message, error = false) {
  $("status").textContent = message;
  $("status").classList.toggle("error", error);
}

function timestamp(ms) {
  return (ms / 1000).toFixed(2) + " s";
}

function durationLabel(ms) {
  return Math.max(0.1, Math.round(ms / 100) / 10) + " s";
}

function updateButtons() {
  const active = Boolean(state?.recording);
  const draft = Boolean(state?.draft);
  const messages = state?.session?.mode === "messages";
  const locked = busy || Boolean(state?.transcribing);
  $("record").hidden = draft || (active && !messages);
  $("record").disabled = locked || !state;
  $("record").textContent = active ? "Record Next" : "Start Recording";
  $("send").hidden = !draft;
  $("send").disabled = locked || Boolean(state?.starting_capture);
  $("discard").hidden = !draft;
  $("discard").disabled = locked;
  $("end").hidden = !active;
  $("end").disabled = locked || draft;
  $("end").textContent = messages ? "End Session" : "Stop and Save";
  for (const id of ["history", "open", "wav", "transcribe"]) {
    $(id).disabled = locked || active || !state;
  }
  $("history").hidden = active;
  $("open").hidden = active;
  $("import-voice").disabled = locked || draft || !state || (active && !messages);
  $("preview-draft").disabled = busy;
  for (const button of document.querySelectorAll(".voice-transcribe, .bind-voice")) {
    button.disabled = locked || draft;
  }
}

function featureTitle(operation) {
  return operation.features.map(feature => feature.name + " · " + feature.kind + " #" + feature.index).join(" / ");
}

function updateStepChoices(operations) {
  const select = $("step");
  const previous = $("match").hidden ? "" : select.value;
  select.replaceChildren();
  const pending = operations.filter(step => !step.voice);
  $("match").hidden = !state.draft || pending.length < 2;
  if (pending.length > 1) select.add(new Option("Link a Step Later", "later"));
  for (const operation of pending) {
    select.add(new Option(featureTitle(operation), String(operation.id)));
  }
  if (pending.some(operation => String(operation.id) === previous)) select.value = previous;
}

async function playVoice(voiceId) {
  if (state.native_microphone) {
    await act("play_voice", { step: voiceId });
    return;
  }
  try {
    const key = String(voiceId);
    if (activeVoice === key && !voicePlayer.paused) {
      voicePlayer.pause();
      return;
    }
    if (activeVoice !== key) voicePlayer.src = state.voices[key];
    activeVoice = key;
    await voicePlayer.play();
  } catch (error) {
    status(error.message, true);
  }
}

function addVoiceMessage(row, voiceId, voice, title) {
  const message = document.createElement("div");
  message.className = "voice-message";
  const bar = document.createElement("button");
  bar.className = "voice-bar";
  bar.dataset.key = String(voiceId);
  bar.dataset.duration = durationLabel(voice.duration_ms);
  bar.dataset.title = title;
  bar.onclick = () => playVoice(voiceId);
  const transcribe = document.createElement("button");
  transcribe.className = "voice-transcribe";
  transcribe.textContent = voice.transcript.length ? "Transcribe Again" : "Transcribe";
  transcribe.onclick = () => act("transcribe", { language: $("language").value, step: voiceId });
  message.append(bar, transcribe);
  row.append(message);
}

function renderUnassigned(data) {
  const messages = data?.unassigned_voices ?? [];
  $("loose-voices").hidden = !messages.length;
  $("voice-list").replaceChildren();
  if (!messages.length) return;
  const operations = data.operations.filter(operation => !operation.voice);
  for (const [index, { id, voice }] of messages.entries()) {
    const row = document.createElement("li");
    addVoiceMessage(row, id, voice, "Unlinked voice message " + (index + 1));
    const text = document.createElement("p");
    text.textContent = voice.transcript.map(cue => cue.text).join(" ");
    row.append(text);
    if (operations.length) {
      const select = document.createElement("select");
      select.setAttribute("aria-label", "Choose a modeling step");
      for (const operation of operations) {
        select.add(new Option(featureTitle(operation), String(operation.id)));
      }
      const bind = document.createElement("button");
      bind.className = "bind-voice";
      bind.textContent = "Link to Step";
      bind.onclick = () => act("bind_voice", { voice: id, step: Number(select.value) });
      const actions = document.createElement("div");
      actions.className = "actions";
      actions.append(select, bind);
      row.append(actions);
    }
    $("voice-list").append(row);
  }
}

function render(next) {
  if (state && state.folder !== next.folder) {
    voicePlayer.pause();
    activeVoice = null;
  }
  state = next;
  const data = state.session;
  const hasAudio = Boolean(state.audio);
  const messages = data?.mode === "messages";
  $("review").hidden = !data || (state.recording && !messages);
  $("attach").hidden = hasAudio || messages;
  $("transcription").hidden = !hasAudio && !messages;
  $("transcribe").hidden = messages;
  updateStepChoices(data?.operations ?? []);
  renderUnassigned(data);
  player.hidden = !hasAudio;
  if (state.audio !== player.getAttribute("src")) {
    player.pause();
    clipEnd = null;
    if (hasAudio) player.src = state.audio;
    else player.removeAttribute("src");
    player.load();
  }
  stepRows = [];
  $("steps").replaceChildren();
  if (data) {
    $("design").textContent = data.design;
    $("folder").textContent = state.folder;
    for (const operation of data.operations) {
      const row = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = featureTitle(operation);
      const timing = document.createElement("p");
      timing.textContent = messages ? "Completed at " + timestamp(operation.at_ms)
        : timestamp(operation.start_ms) + " – " + timestamp(operation.end_ms) +
          " (detected at " + timestamp(operation.at_ms) + ")";
      timing.title = operation.command || operation.command_id;
      const text = document.createElement("p");
      text.textContent = (operation.voice?.transcript ?? operation.transcript ?? [])
        .map(cue => cue.text).join(" ");
      row.append(title, timing);
      if (operation.voice) addVoiceMessage(row, operation.id, operation.voice, featureTitle(operation) + " voice message");
      else if (messages) text.textContent = "No voice message yet";
      row.append(text);
      if (hasAudio && operation.audio_clip) {
        const { start_ms, end_ms } = operation.audio_clip;
        const button = document.createElement("button");
        button.textContent = "Play Clip";
        button.onclick = async () => {
          try {
            player.currentTime = start_ms / 1000;
            clipEnd = end_ms / 1000;
            await player.play();
          } catch (error) {
            clipEnd = null;
            status(error.message, true);
          }
        };
        row.append(button);
      }
      stepRows.push({ row, operation });
      $("steps").append(row);
    }
    $("unassigned").textContent = data.unassigned_transcript.length
      ? "Unmatched transcript: " + data.unassigned_transcript.map(cue => cue.text).join(" ")
      : "";
  }
  updateVoiceBars();
  const message = state.issue || (state.transcribing ? "Transcribing on this computer…"
    : state.starting_capture ? "On first use, click Allow when macOS requests microphone access."
    : state.capturing ? "Finish the modeling step, then click Send Voice Message."
    : state.draft ? "Preview or send this voice message."
    : state.recording ? (messages ? "Click Record Next to continue, or end the session." : "Tracking modeling steps.")
    : data ? (data.interrupted ? "Recording was interrupted. Received audio and steps were saved." :
      data.operations.length || data.unassigned_voices?.length
        ? "Session saved. Click a voice bar to listen." : "Session saved. No new modeling steps were detected.")
    : "Open a parametric design, then start recording.");
  status(message, Boolean(state.issue));
  $("status").classList.toggle("recording", state.capturing && !state.issue);
  updateButtons();
  updateDraftBar();
  const needsPoll = state.transcribing || state.starting_capture || state.playing_voice !== null;
  if (needsPoll && !poll) {
    poll = setInterval(() => act("state"), 500);
  } else if (!needsPoll && poll) {
    clearInterval(poll);
    poll = null;
  }
}

player.addEventListener("timeupdate", () => {
  if (clipEnd !== null && player.currentTime >= clipEnd) {
    player.pause();
    clipEnd = null;
  }
  const data = state?.session;
  if (!data?.audio) return;
  const time = player.currentTime * 1000 + data.audio.offset_ms;
  for (const { row, operation } of stepRows) {
    row.classList.toggle("active", operation.start_ms <= time && time < operation.end_ms);
  }
});
player.addEventListener("ended", () => { clipEnd = null; });
player.addEventListener("pause", () => { clipEnd = null; });

function encodePCM(samples) {
  const data = new DataView(new ArrayBuffer(samples.length * 2));
  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    data.setInt16(i * 2, Math.round(sample * 32767), true);
  }
  return btoa(String.fromCharCode(...new Uint8Array(data.buffer)));
}

async function closeCapture() {
  const current = capture;
  capture = null;
  if (!current) return null;
  if (current.processor) {
    current.processor.onaudioprocess = null;
    current.processor.disconnect();
  }
  current.stream?.getTracks().forEach(track => track.stop());
  if (current.context && current.context.state !== "closed") {
    current.context.close().catch(() => {});
  }
  await current.queue;
  return current.error;
}

async function withinTime(promise, delay, message) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(message)), delay);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

async function startCapture() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Fusion could not access the microphone.");
  }
  const current = capture = { stream: null, queue: Promise.resolve(), frames: 0, error: null };
  let started = false;
  try {
    status("Waiting for the microphone. Click Allow if prompted.");
    const Context = window.AudioContext || window.webkitAudioContext;
    const context = current.context = new Context();
    // Request both from the original click while the panel has user activation.
    const resumed = context.resume();
    resumed.catch(() => {});
    const media = navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } }).then(stream => {
      if (capture !== current) {
        stream.getTracks().forEach(track => track.stop());
        throw new Error("Recording was canceled.");
      }
      current.stream = stream;
      return stream;
    });
    const stream = await withinTime(media, 12000, "The microphone did not respond.");
    status("Starting recording.");
    await withinTime(resumed, 4000, "Fusion could not start its audio engine.");
    if (capture !== current) throw new Error("Recording was canceled.");
    const processor = current.processor = context.createScriptProcessor(4096, 1, 1);
    const source = context.createMediaStreamSource(stream);
    const reply = await send("start_voice", { rate: context.sampleRate });
    started = true;
    if (capture !== current) throw new Error("Recording was canceled.");
    processor.onaudioprocess = event => {
      const samples = event.inputBuffer.getChannelData(0);
      const pcm = encodePCM(samples);
      const frame = current.frames;
      current.frames += samples.length;
      current.queue = current.queue.then(async () => {
        if (!current.error) await send("audio", { pcm, frame });
      }).catch(error => {
        current.error = error;
        if (capture === current && !busy) act("discard_voice", { error: error.message });
      });
    };
    source.connect(processor);
    processor.connect(context.destination);
    return reply;
  } catch (error) {
    if (capture === current) await closeCapture();
    if (started) render(await send("discard_voice"));
    if (error.name === "NotAllowedError") {
      throw new Error("Fusion does not have microphone access.");
    }
    throw error;
  }
}

async function act(action, body = {}) {
  if (busy) return;
  busy = true;
  updateButtons();
  try {
    if (action === "microphone") {
      requestingMic = true;
      updateDraftBar();
      render(await (state.native_microphone ? send("start_mac_voice") : startCapture()));
    } else if (action === "preview") {
      const error = await closeCapture();
      if (error) {
        render(await send("discard_voice"));
        throw error;
      }
      if (state.native_microphone) {
        render(await send("play_voice", { step: "draft" }));
      } else {
        render(await send("seal_voice"));
        if (state.draft_duration_ms) await playVoice("draft");
      }
    } else if (action === "send_voice" || action === "discard_voice") {
      if (activeVoice === "draft") {
        voicePlayer.pause();
        activeVoice = null;
      }
      const error = await closeCapture();
      render(await send(error ? "discard_voice" : action, body));
      if (error) status("Recording was interrupted. Please record it again. " + error.message, true);
    } else {
      const next = await send(action, body);
      // Keep the current controls and focus intact when a playback poll has no news.
      if (action !== "state" || JSON.stringify(next) !== JSON.stringify(state)) render(next);
    }
  } catch (error) {
    if (error.state) render(error.state);
    status(error.message, true);
  } finally {
    requestingMic = false;
    busy = false;
    updateButtons();
    updateDraftBar();
  }
}

// Fusion's Qt web view can run the page before it exposes the bridge, and
// before the Python add-in has attached the incoming message handler.
async function connect() {
  if (state || busy) return;
  busy = true;
  updateButtons();
  $("reconnect").hidden = true;
  status("Connecting to Fusion…");
  try {
    for (let attempt = 0; attempt < 30; attempt++) {
      if (typeof window.adsk?.fusionSendData === "function") {
        let timeout;
        try {
          const reply = await Promise.race([
            send("state"),
            new Promise((_, reject) => {
              timeout = setTimeout(() => reject(new Error("Fusion did not respond")), 350);
            }),
          ]);
          render(reply);
          return;
        } catch (_) {
          // Only the read-only state request is safe to repeat at startup.
        } finally {
          clearTimeout(timeout);
        }
      }
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    status("Could not connect to Fusion. Retry, or stop and run the add-in again.", true);
    $("reconnect").hidden = false;
  } finally {
    busy = false;
    updateButtons();
  }
}

$("reconnect").onclick = connect;
$("record").onclick = () => act("microphone");
$("send").onclick = () => {
  const choice = $("step").value;
  act("send_voice", { step: choice === "later" ? "later" : Number(choice) || null });
};
$("preview-draft").onclick = () => act("preview");
$("import-voice").onclick = () => act("import_voice");
$("discard").onclick = () => act("discard_voice");
$("end").onclick = () => act("stop");
$("history").onclick = () => act("start");
$("open").onclick = () => act("open");
$("wav").onclick = () => act("import_wav", { offset_ms: Math.round($("offset").valueAsNumber * 1000) || 0 });
$("transcribe").onclick = () => act("transcribe", { language: $("language").value });
window.fusionJavaScriptHandler = {
  handle(action) {
    if (action === "release_microphone") closeCapture().catch(error => status(error.message, true));
    if (action === "refresh") {
      if (state) act("state");
      else connect();
    }
    return "OK";
  },
};
window.addEventListener("pagehide", () => {
  closeCapture().catch(() => {});
});
connect();
