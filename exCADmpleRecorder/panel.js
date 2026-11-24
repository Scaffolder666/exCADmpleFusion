"use strict";

const $ = id => document.getElementById(id);
const player = $("audio");
let state;
let capture;
let busy = false;
let clipEnd = null;
let poll;
let stepRows = [];

async function send(action, payload = {}) {
  const raw = await window.adsk.fusionSendData(action, JSON.stringify(payload));
  const reply = JSON.parse(raw);
  if (!reply.ok) throw new Error(reply.error);
  return reply;
}

function status(message, error = false) {
  $("status").textContent = message;
  $("status").classList.toggle("error", error);
}

function timestamp(ms) {
  return (ms / 1000).toFixed(2) + " s";
}

function updateButtons() {
  const recording = Boolean(state?.recording);
  const locked = busy || Boolean(state?.transcribing);
  $("record").disabled = locked || !state;
  $("record").textContent = recording ? "停止并保存" : "录制语音与建模";
  for (const id of ["history", "open", "wav", "transcribe"]) {
    $(id).disabled = locked || recording || !state;
  }
}

function render(next) {
  state = next;
  const data = state.session;
  const hasAudio = Boolean(state.audio);
  $("review").hidden = !data || state.recording;
  $("attach").hidden = hasAudio;
  $("transcription").hidden = !hasAudio;
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
      title.textContent = operation.features.map(feature =>
        feature.name + " · " + feature.kind + " #" + feature.index).join(" / ");
      const timing = document.createElement("p");
      timing.textContent = timestamp(operation.start_ms) + " – " + timestamp(operation.end_ms) +
        "（检测于 " + timestamp(operation.at_ms) + "）";
      timing.title = operation.command || operation.command_id;
      const text = document.createElement("p");
      text.textContent = operation.transcript.map(cue => cue.text).join(" ");
      row.append(title, timing, text);
      if (hasAudio && operation.audio_clip) {
        const { start_ms, end_ms } = operation.audio_clip;
        const button = document.createElement("button");
        button.textContent = "播放此段";
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
      ? "未匹配的转写：" + data.unassigned_transcript.map(cue => cue.text).join(" ")
      : "";
  }
  const message = state.issue || (state.recording
    ? "录制中。请边建模边说出你的设计理由。"
    : state.transcribing ? "正在本机转写…"
    : data ? (data.interrupted ? "录制中断，已保存收到的数据。" :
      data.operations.length ? "已保存。点击操作可试听对应语音。" : "已保存，未检测到新增建模操作。")
    : "打开一个参数化设计，然后开始录制。");
  status(message, Boolean(state.issue));
  updateButtons();
  if (state.transcribing && !poll) {
    poll = setInterval(() => act("state"), 2000);
  } else if (!state.transcribing && poll) {
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
  current.stream.getTracks().forEach(track => track.stop());
  if (current.context) await current.context.close();
  await current.queue;
  return current.error;
}

async function startCapture() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Fusion 面板无法访问麦克风。可仅记录建模，再导入同步录制的 WAV。");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
  const current = capture = { stream, queue: Promise.resolve(), frames: 0, error: null };
  let started = false;
  try {
    const Context = window.AudioContext || window.webkitAudioContext;
    const context = current.context = new Context();
    await context.resume();
    const processor = current.processor = context.createScriptProcessor(4096, 1, 1);
    const source = context.createMediaStreamSource(stream);
    const reply = await send("start", { rate: context.sampleRate });
    started = true;
    processor.onaudioprocess = event => {
      const samples = event.inputBuffer.getChannelData(0);
      const pcm = encodePCM(samples);
      const frame = current.frames;
      current.frames += samples.length;
      current.queue = current.queue.then(async () => {
        if (!current.error) await send("audio", { pcm, frame });
      }).catch(error => {
        current.error = error;
        if (capture === current && !busy) act("stop", { interrupted: true });
      });
    };
    source.connect(processor);
    processor.connect(context.destination);
    return reply;
  } catch (error) {
    await closeCapture();
    if (started) render(await send("stop", { interrupted: true }));
    throw error;
  }
}

async function act(action, body = {}) {
  if (busy) return;
  busy = true;
  updateButtons();
  try {
    if (action === "microphone") {
      render(await startCapture());
    } else if (action === "stop") {
      const error = await closeCapture();
      render(await send("stop", { interrupted: Boolean(error) || body.interrupted }));
      if (error) status("音频录制中断：" + error.message, true);
    } else {
      render(await send(action, body));
    }
  } catch (error) {
    status(error.message, true);
  } finally {
    busy = false;
    updateButtons();
  }
}

$("record").onclick = () => act(state.recording ? "stop" : "microphone");
$("history").onclick = () => act("start");
$("open").onclick = () => act("open");
$("wav").onclick = () => act("import_wav", { offset_ms: Math.round($("offset").valueAsNumber * 1000) || 0 });
$("transcribe").onclick = () => act("transcribe", { language: $("language").value });
window.fusionJavaScriptHandler = {
  handle(action) {
    if (action === "release_microphone") closeCapture().catch(error => status(error.message, true));
    if (action === "refresh") act("state");
    return "OK";
  },
};
window.addEventListener("pagehide", () => {
  if (capture) capture.stream.getTracks().forEach(track => track.stop());
});
act("state");
