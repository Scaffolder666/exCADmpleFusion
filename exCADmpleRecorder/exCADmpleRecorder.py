"""Standalone Fusion add-in for recording and reviewing design narration."""

import base64
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import wave

import adsk.core
import adsk.fusion

from .session import FORMAT, VERSION, align_transcript, build_session, save_session

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SESSIONS = Path.home() / "Documents" / "exCADmpleRecordings"
COMMAND_ID = "Scaffolder_exCADmpleVoiceRecorder"
PALETTE_ID = COMMAND_ID + "_palette"
MAX_PCM_BYTES = 512 * 1024 * 1024
_app = _ui = _recorder = _palette = _definition = _control = None
_handlers = []
_palette_handlers = []


def timeline_features(collection):
    for index in range(collection.count):
        item = collection.item(index)
        if item.isGroup:
            yield from timeline_features(adsk.fusion.TimelineGroup.cast(item))
        elif item.entity:
            entity = item.entity
            yield {"index": item.index, "name": getattr(entity, "name", "") or "",
                   "kind": entity.objectType.rsplit("::", 1)[-1]}


def feature_counts(features):
    return Counter((item["name"], item["kind"]) for item in features)


class Recorder:
    def __init__(self):
        self.design = None
        self.folder = None
        self.data = None
        self.audio = None
        self.wav = None
        self.job = None
        self.issue = ""

    def now(self):
        return int((time.monotonic() - self.started) * 1000)

    def begin(self, rate):
        if self.design or self.job:
            raise ValueError("请先完成当前录制或转写。")
        design = adsk.fusion.Design.cast(_app.activeProduct)
        if not design or design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
            raise ValueError("请打开启用了设计历史记录的参数化设计。")
        folder = SESSIONS / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
        baseline = feature_counts(timeline_features(design.timeline))
        folder.mkdir(parents=True)
        self.folder = folder
        self.data = None
        self.audio = None
        self.audio_frames = 0
        self.operations = []
        self.baseline = baseline
        self.design_name = design.parentDocument.name
        self.issue = ""
        if rate is not None:
            self.wav = wave.open(str(folder / "voice.wav"), "wb")
            self.wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
            self.audio = {"file": "voice.wav", "offset_ms": 0, "sample_rate": rate}
        self.design = design
        self.started = time.monotonic()

    def append_audio(self, encoded, frame):
        if self.wav is None:
            raise ValueError("录音已结束。")
        if frame != self.audio_frames:
            raise ValueError("音频数据顺序异常。")
        pcm = base64.b64decode(encoded, validate=True)
        if not pcm or len(pcm) % 2 or len(pcm) > 512 * 1024:
            raise ValueError("无效的音频块。")
        if self.audio_frames * 2 + len(pcm) > MAX_PCM_BYTES:
            raise ValueError("录音已达到大小上限，请结束本次录制。")
        self.wav.writeframes(pcm)
        self.audio_frames += len(pcm) // 2

    def observe(self, command_id="", command_name=""):
        if not self.design or not self.design.isValid:
            return
        # The recording is tied to the originating Design. Other document
        # histories must never be associated with this recording.
        if _app.activeDocument != self.design.parentDocument:
            return
        when = self.now()
        features = list(timeline_features(self.design.timeline))
        current = feature_counts(features)
        added = current - self.baseline
        self.baseline = current
        recorded = []
        for item in reversed(features):
            key = item["name"], item["kind"]
            if added[key]:
                recorded.append(item)
                added[key] -= 1
        if recorded:
            self.operations.append({
                "at_ms": when, "command_id": command_id, "command": command_name,
                "features": list(reversed(recorded)),
            })

    def finish(self, interrupted=False):
        if not self.design:
            return
        try:
            self.observe()
        except (RuntimeError, ValueError) as error:
            self.issue = str(error)
        duration = self.now()
        self.design = None
        if self.wav is not None:
            self.wav.close()
            self.wav = None
            self.audio["duration_ms"] = round(self.audio_frames * 1000 / self.audio["sample_rate"])
            if not self.audio_frames:
                self.audio = None
        data = build_session(self.design_name, duration, self.operations, self.audio,
                             interrupted=interrupted)
        if self.issue:
            data["history_error"] = self.issue
        self.data = data
        save_session(self.folder, data)

    def open_session(self):
        path = choose_file("打开录制记录", "exCADmple session (*.json)")
        if not path:
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("format") != FORMAT or data.get("version") != VERSION:
            raise ValueError("请选择本插件生成的 session.json。")
        audio = data.get("audio")
        if audio and (audio.get("file") != "voice.wav" or not (path.parent / "voice.wav").is_file()):
            raise ValueError("请将 voice.wav 和 session.json 放在同一目录。")
        if path.name != "session.json":
            raise ValueError("请打开保存的 session.json。")
        self.folder, self.data, self.issue = path.parent, data, ""

    def import_wav(self, offset):
        if not self.data or self.data["audio"]:
            raise ValueError("请先结束无语音的时间轴录制。")
        path = choose_file("选取与操作同时录制的 WAV 文件", "WAV (*.wav)")
        if not path:
            return
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            duration = round(handle.getnframes() * 1000 / rate)
        if duration <= 0:
            raise ValueError("WAV 文件为空。")
        target = self.folder / "voice.wav"
        if path.resolve() != target.resolve():
            shutil.copyfile(path, target)
        self.data["audio"] = {
            "file": target.name, "offset_ms": offset, "duration_ms": duration, "sample_rate": rate,
        }
        save_session(self.folder, align_transcript(self.data))

    def transcribe(self, language):
        if not self.data or not self.data["audio"] or self.job:
            raise ValueError("需要已保存的音频，或等待当前转写结束。")
        python = Path.home() / ".venvs" / "excadmple-recorder" / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            raise ValueError("请先按 README 安装转写依赖。")
        output = self.folder / "transcript.json"
        log = self.folder / "transcription.log"
        self.issue = ""
        args = [str(python), str(REPO / "tools" / "transcribe.py"),
                str(self.folder / self.data["audio"]["file"]), "-o", str(output), "--format", "json",
                "--device", "cpu", "--model", "small"]
        if language:
            args.extend(["--language", language])
        with log.open("w", encoding="utf-8") as handle:
            self.job = subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT)

    def poll(self):
        status = self.job.poll() if self.job else None
        if status is None:
            return
        self.job = None
        if status:
            self.issue = "转写失败。请查看会话目录里的 transcription.log。"
            return
        self.data["transcript"] = json.loads((self.folder / "transcript.json").read_text(encoding="utf-8"))
        align_transcript(self.data)
        save_session(self.folder, self.data)

    def state(self):
        audio = self.data and self.data["audio"]
        return {
            "recording": self.design is not None, "transcribing": self.job is not None,
            "session": self.data, "folder": str(self.folder) if self.folder else "",
            "audio": (self.folder / audio["file"]).as_uri() if audio else None,
            "issue": self.issue,
        }


def choose_file(title, pattern):
    dialog = _ui.createFileDialog()
    dialog.title = title
    dialog.filter = pattern
    if dialog.showOpen() == adsk.core.DialogResults.DialogOK:
        return Path(dialog.filename)
    return None


class CommandTerminated(adsk.core.ApplicationCommandEventHandler):
    def notify(self, args):
        if not _recorder.design:
            return
        try:
            definition = _ui.commandDefinitions.itemById(args.commandId)
            _recorder.observe(args.commandId, definition.name if definition else "")
        except Exception as error:
            _recorder.issue = str(error)


class PanelMessage(adsk.core.HTMLEventHandler):
    def notify(self, args):
        action = args.action
        if action == "response":
            return
        r = _recorder
        try:
            body = json.loads(args.data or "{}")
            if action == "start":
                rate = body.get("rate")
                if rate is not None and (type(rate) is not int or not 8000 <= rate <= 96000):
                    raise ValueError("不支持的采样率。")
                r.begin(rate)
            elif action == "audio":
                r.append_audio(body["pcm"], body["frame"])
                args.returnData = '{"ok": true}'
                return
            elif action == "stop":
                r.finish(interrupted=bool(body.get("interrupted")))
            elif action in ("open", "import_wav", "transcribe"):
                if r.design or r.job:
                    raise ValueError("请先完成当前录制或转写。")
                if action == "open":
                    r.open_session()
                elif action == "import_wav":
                    r.import_wav(int(body["offset_ms"]))
                else:
                    if body["language"] not in ("", "zh", "en"):
                        raise ValueError("请选择有效的转写语言。")
                    r.transcribe(body["language"])
            elif action == "state":
                r.poll()
            else:
                raise ValueError("未知操作：" + action)
            args.returnData = json.dumps({"ok": True, **r.state()})
        except Exception as error:
            args.returnData = json.dumps({"ok": False, "error": str(error), **r.state()})


def interrupt_recording():
    if _recorder.design:
        try:
            _recorder.finish(interrupted=True)
        finally:
            if _palette and _palette.isValid:
                _palette.sendInfoToHTML("release_microphone", "{}")


class PanelClosed(adsk.core.UserInterfaceGeneralEventHandler):
    def notify(self, _args):
        interrupt_recording()


class WorkspaceChanging(adsk.core.WorkspaceEventHandler):
    def notify(self, _args):
        interrupt_recording()


class ShowPanel(adsk.core.CommandCreatedEventHandler):
    def notify(self, _args):
        global _palette
        if not _palette or not _palette.isValid:
            _palette_handlers.clear()
            html = ROOT / "panel.html"
            stamp = max(p.stat().st_mtime_ns for p in (html, ROOT / "panel.js"))
            _palette = _ui.palettes.add2(PALETTE_ID, "exCADmple · 语音录制",
                                         html.as_uri() + "?v=" + str(stamp), False, True, True, 390, 680)
            message, closed = PanelMessage(), PanelClosed()
            _palette.incomingFromHTML.add(message)
            _palette.closed.add(closed)
            _palette_handlers.extend((message, closed))
        _palette.isVisible = True
        _palette.sendInfoToHTML("refresh", "{}")


def run(_context):
    global _app, _ui, _recorder, _definition, _control
    _app = adsk.core.Application.get()
    _ui = _app.userInterface
    _recorder = Recorder()
    show, terminated, workspace = ShowPanel(), CommandTerminated(), WorkspaceChanging()
    _definition = _ui.commandDefinitions.addButtonDefinition(
        COMMAND_ID, "exCADmple · 语音录制", "录制语音并与建模时间轴对齐")
    _definition.commandCreated.add(show)
    _ui.commandTerminated.add(terminated)
    _ui.workspacePreActivate.add(workspace)
    _handlers.extend((show, terminated, workspace))
    for panel_id in ("SolidScriptsAddinsPanel", "ToolsScriptsAddinsPanel"):
        panel = _ui.allToolbarPanels.itemById(panel_id)
        if panel:
            _control = panel.controls.addCommand(_definition)
            break
    if not _control:
        _ui.messageBox("请切换到设计工作区后重新运行 exCADmpleRecorder。")


def stop(_context):
    global _recorder, _palette, _definition, _control
    try:
        if _recorder:
            _recorder.finish(interrupted=True)
            if _recorder.job and _recorder.job.poll() is None:
                _recorder.job.terminate()
    finally:
        if _ui and _handlers:
            _ui.commandTerminated.remove(_handlers[1])
            _ui.workspacePreActivate.remove(_handlers[2])
        for item in (_palette, _control, _definition):
            if item and item.isValid:
                item.deleteMe()
        _handlers.clear()
        _palette_handlers.clear()
        _recorder = _palette = _definition = _control = None
