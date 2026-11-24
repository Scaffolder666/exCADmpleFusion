"""Standalone Fusion add-in for recording and reviewing design narration."""

import base64
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import wave

import adsk.core
import adsk.fusion

from .mac_audio import MacAudio
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
        self.draft = None
        self.wav = None
        self.mac_audio = None
        self.job = None
        self.playback = None
        self.issue = ""
        self.panel_directory = None

    def panel_url(self):
        if self.panel_directory is None:
            template = (ROOT / "panel.html").read_text(encoding="utf-8")
            script = (ROOT / "panel.js").read_text(encoding="utf-8")
            self.panel_directory = tempfile.TemporaryDirectory(prefix="excadmple-recorder-")
            html = Path(self.panel_directory.name) / "panel.html"
            html.write_text(template.replace("<!-- PANEL_SCRIPT -->", f"<script>{script}</script>"),
                            encoding="utf-8")
        return (Path(self.panel_directory.name) / "panel.html").as_uri()

    def now(self):
        return int((time.monotonic() - self.started) * 1000)

    def begin(self, messages=False):
        if self.design or self.job:
            raise ValueError("Finish the current recording or transcription first.")
        design = adsk.fusion.Design.cast(_app.activeProduct)
        if not design or design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
            raise ValueError("Open a parametric design with design history enabled.")
        folder = SESSIONS / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
        baseline = feature_counts(timeline_features(design.timeline))
        folder.mkdir(parents=True)
        self.stop_voice_playback()
        self.folder = folder
        self.operations = []
        self.draft = None
        self.baseline = baseline
        self.design_name = design.parentDocument.name
        self.issue = ""
        self.design = design
        self.started = time.monotonic()
        self.data = build_session(self.design_name, 0, [])
        if messages:
            self.data["mode"] = "messages"

    def prepare_voice(self):
        if self.draft:
            raise ValueError("Send or cancel the current voice message first.")
        if not self.design:
            self.begin(messages=True)
        if self.data.get("mode") != "messages":
            raise ValueError("End the current modeling session first.")
        if _app.activeDocument != self.design.parentDocument:
            raise ValueError("Switch back to the design for this recording session.")
        self.stop_voice_playback()
        self.issue = ""

    def start_mac_voice(self):
        app = ROOT / "exCADmple Microphone.app"
        if not app.is_dir():
            raise ValueError("Run the macOS microphone setup command in the README first.")
        self.prepare_voice()
        self.mac_audio = MacAudio(app, self.folder)
        self.draft = {"start_ms": self.now(), "sample_rate": 16000}

    def start_voice(self, rate):
        self.prepare_voice()
        self.wav = wave.open(str(self.folder / ".voice-pending.wav"), "wb")
        self.wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        self.audio_frames = 0
        self.draft = {"start_ms": self.now(), "sample_rate": rate}

    def seal_voice(self):
        if self.mac_audio is not None:
            duration = self.mac_audio.finish(self.folder / ".voice-pending.wav")
            self.mac_audio = None
            self.draft["duration_ms"] = duration
        if self.wav is not None:
            self.wav.close()
            self.wav = None
            self.draft["duration_ms"] = round(self.audio_frames * 1000 / self.draft["sample_rate"])

    def discard_voice(self):
        if self.playback and self.playback[0] == "draft":
            self.stop_voice_playback()
        if self.mac_audio is not None:
            audio, self.mac_audio = self.mac_audio, None
            try:
                audio.finish()
            except ValueError:
                pass
        self.seal_voice()
        if self.draft:
            (self.folder / ".voice-pending.wav").unlink(missing_ok=True)
            self.draft = None

    def send_voice(self, operation_id):
        try:
            self.observe()
        except (RuntimeError, ValueError) as error:
            self.data["history_error"] = str(error)
        self.seal_voice()
        if not self.draft or not self.draft["duration_ms"]:
            self.discard_voice()
            raise ValueError("This recording contains no audio. Please record it again.")
        if self.playback and self.playback[0] == "draft":
            self.stop_voice_playback()
        pending = [step for step in self.operations if not step.get("voice")]
        if len(pending) == 1 and operation_id is None:
            operation_id = pending[0]["id"]
        target = next((step for step in pending if step["id"] == operation_id), None)
        messages = self.data.setdefault("unassigned_voices", [])
        voice_id = uuid.uuid4().hex
        file = "voice-{}.wav".format(target["id"] if target is not None else voice_id)
        pending_path = self.folder / ".voice-pending.wav"
        final_path = self.folder / file
        pending_path.replace(final_path)
        voice = {**self.draft, "file": file, "transcript": []}
        if target is None:
            messages.append({"id": voice_id, "voice": voice})
        else:
            target["voice"] = voice
        try:
            self.save_messages()
        except OSError:
            if target is None:
                messages.pop()
            else:
                target.pop("voice")
            final_path.replace(pending_path)
            raise
        self.draft = None
        self.issue = ""

    def bind_voice(self, voice_id, operation_id):
        if not self.data or self.job:
            raise ValueError("Wait for the current transcription to finish.")
        self.observe()
        operations = self.operations if self.design else self.data["operations"]
        target = next((step for step in operations if step["id"] == operation_id
                       and not step.get("voice")), None)
        messages = self.data.get("unassigned_voices", [])
        source = next((item for item in messages if item["id"] == voice_id), None)
        if target is None or source is None:
            raise ValueError("Choose an unlinked voice message and a modeling step without audio.")
        self.stop_voice_playback()
        voice = source["voice"]
        old_path = self.folder / voice["file"]
        new_path = self.folder / "voice-{}.wav".format(operation_id)
        old_path.replace(new_path)
        target["voice"] = {**voice, "file": new_path.name}
        position = messages.index(source)
        messages.pop(position)
        try:
            if self.design:
                self.save_messages()
            else:
                save_session(self.folder, self.data)
        except OSError:
            messages.insert(position, source)
            target.pop("voice")
            new_path.replace(old_path)
            raise

    def import_voice(self):
        if self.draft or self.job or (self.design and self.data.get("mode") != "messages"):
            raise ValueError("Finish the current recording or transcription first.")
        path = choose_file("Import Voice Message", "WAV (*.wav)")
        if path is None:
            return
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            duration = round(handle.getnframes() * 1000 / rate)
        if duration <= 0:
            raise ValueError("The WAV file is empty.")
        if not self.design:
            self.begin(messages=True)
        pending_path = self.folder / ".voice-pending.wav"
        shutil.copyfile(path, pending_path)
        self.draft = {"start_ms": self.now(), "sample_rate": rate, "duration_ms": duration}
        self.send_voice("later")

    def save_messages(self, interrupted=False):
        self.data.update(duration_ms=self.now(), operations=self.operations, interrupted=interrupted)
        save_session(self.folder, self.data)

    def append_audio(self, encoded, frame):
        if self.wav is None:
            raise ValueError("Recording has already ended.")
        if frame != self.audio_frames:
            raise ValueError("Audio arrived out of order.")
        pcm = base64.b64decode(encoded, validate=True)
        if not pcm or len(pcm) % 2 or len(pcm) > 512 * 1024:
            raise ValueError("Invalid audio data.")
        if self.audio_frames * 2 + len(pcm) > MAX_PCM_BYTES:
            raise ValueError("This recording has reached the size limit. Please end the recording.")
        self.wav.writeframes(pcm)
        self.audio_frames += len(pcm) // 2

    def observe(self, command_id="", command_name=""):
        if not self.design or not self.design.isValid:
            return
        # Read only the pinned design, even when Fusion returns a different
        # Python wrapper for its document during a command event.
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
                "id": len(self.operations) + 1, "at_ms": when,
                "command_id": command_id, "command": command_name,
                "features": list(reversed(recorded)),
            })

    def finish(self, interrupted=False):
        if not self.design:
            return
        try:
            self.observe()
        except (RuntimeError, ValueError) as error:
            self.issue = str(error)
        if self.draft and not interrupted:
            raise ValueError("Send or cancel this voice message before ending the session.")
        if interrupted and self.draft and self.data.get("mode") == "messages":
            try:
                self.send_voice("later")
            except ValueError:
                self.discard_voice()
        if self.data.get("mode") == "messages":
            self.save_messages(interrupted)
        else:
            self.data = build_session(self.design_name, self.now(), self.operations,
                                      interrupted=interrupted)
            save_session(self.folder, self.data)
        self.design = None

    def open_session(self):
        path = choose_file("Open Recording Session", "exCADmple session (*.json)")
        if not path:
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("format") != FORMAT or data.get("version") != VERSION:
            raise ValueError("Select a session.json created by exCADmple Recorder.")
        audio = data.get("audio")
        if audio and (audio.get("file") != "voice.wav" or not (path.parent / "voice.wav").is_file()):
            raise ValueError("Keep voice.wav and session.json in the same folder.")
        for step in data["operations"]:
            if "voice" in step:
                expected = "voice-{}.wav".format(int(step["id"]))
                if step["voice"]["file"] != expected or not (path.parent / expected).is_file():
                    raise ValueError("Keep the session audio files and session.json in the same folder.")
        for item in data.get("unassigned_voices", []):
            voice_id = uuid.UUID(hex=item["id"]).hex
            expected = "voice-{}.wav".format(voice_id)
            if item["voice"]["file"] != expected or not (path.parent / expected).is_file():
                raise ValueError("Keep the unlinked WAV files and session.json in the same folder.")
        if path.name != "session.json":
            raise ValueError("Open the saved session.json file.")
        self.stop_voice_playback()
        self.folder, self.data, self.issue = path.parent, data, ""

    def import_wav(self, offset):
        if not self.data or self.data["audio"]:
            raise ValueError("Finish a modeling-only session before importing its audio.")
        path = choose_file("Select the WAV Recorded During Modeling", "WAV (*.wav)")
        if not path:
            return
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            duration = round(handle.getnframes() * 1000 / rate)
        if duration <= 0:
            raise ValueError("The WAV file is empty.")
        target = self.folder / "voice.wav"
        if path.resolve() != target.resolve():
            shutil.copyfile(path, target)
        self.data["audio"] = {
            "file": target.name, "offset_ms": offset, "duration_ms": duration, "sample_rate": rate,
        }
        save_session(self.folder, align_transcript(self.data))

    def find_voice(self, voice_id):
        if self.data is None:
            return None
        if isinstance(voice_id, int):
            return next((step.get("voice") for step in self.data["operations"]
                         if step["id"] == voice_id), None)
        return next((item["voice"] for item in self.data.get("unassigned_voices", [])
                     if item["id"] == voice_id), None)

    def transcribe(self, language, operation_id=None):
        if not self.data or self.job or self.draft:
            raise ValueError("Send the voice message or wait for the current transcription to finish.")
        voice = self.data["audio"] if operation_id is None else self.find_voice(operation_id)
        if not voice:
            raise ValueError("Save a voice message first.")
        python = Path.home() / ".venvs" / "excadmple-recorder" / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            raise ValueError("Install the transcription dependency using the README instructions.")
        output = self.folder / ("transcript.json" if operation_id is None
                                else "transcript-{}.json".format(operation_id))
        log = output.with_suffix(".log")
        self.issue = ""
        # Fusion embeds Python. Its environment can point a separate Python
        # installation at Fusion's standard library before the script runs.
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith("PYTHON") and key != "__PYVENV_LAUNCHER__"}
        args = [str(python), "-E", str(REPO / "tools" / "transcribe.py"),
                str(self.folder / voice["file"]), "-o", str(output), "--format", "json",
                "--device", "cpu", "--model", "small"]
        if language:
            args.extend(["--language", language])
        with log.open("w", encoding="utf-8") as handle:
            self.job = subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT, env=env)
        self.job_output = output
        self.job_voice = None if operation_id is None else voice

    def toggle_voice_playback(self, operation_id):
        if sys.platform != "darwin":
            raise ValueError("This playback method is for macOS.")
        self.poll_voice_playback()
        current = self.playback
        if current and current[0] == operation_id:
            self.stop_voice_playback()
            return
        if operation_id == "draft" and self.draft:
            self.seal_voice()
            voice = {"file": ".voice-pending.wav"} if self.draft["duration_ms"] else None
        else:
            voice = self.find_voice(operation_id)
        if not voice:
            raise ValueError("Choose a saved voice message.")
        path = self.folder / voice["file"]
        if not path.is_file():
            raise ValueError("Could not find the WAV file for this message.")
        self.stop_voice_playback()
        self.issue = ""
        try:
            process = subprocess.Popen(
                ["/usr/bin/afplay", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as error:
            raise ValueError("Could not start the Mac audio player.") from error
        self.playback = operation_id, process

    def stop_voice_playback(self):
        current, self.playback = self.playback, None
        if current and current[1].poll() is None:
            current[1].terminate()

    def poll_voice_playback(self):
        if self.playback is None:
            return
        operation_id, process = self.playback
        result = process.poll()
        if result is not None:
            self.playback = None
            if result:
                self.issue = "Could not play this message. Check the WAV file and your Mac sound output."

    def poll(self):
        self.poll_voice_playback()
        if self.mac_audio is not None:
            error = self.mac_audio.error()
            if error:
                self.discard_voice()
                self.issue = error
        status = self.job.poll() if self.job else None
        if status is None:
            return
        self.job = None
        if status:
            self.issue = "Transcription failed. In the session folder, check " + self.job_output.with_suffix(".log").name
            return
        cues = json.loads(self.job_output.read_text(encoding="utf-8"))
        if self.job_voice is None:
            self.data["transcript"] = cues
            align_transcript(self.data)
        else:
            self.job_voice["transcript"] = cues
        save_session(self.folder, self.data)

    def state(self):
        audio = self.data and self.data["audio"]
        session = self.data
        if self.design and self.data.get("mode") == "messages":
            session = {**self.data, "operations": self.operations}
        voices = {
            step["id"]: (self.folder / step["voice"]["file"]).as_uri()
            for step in session["operations"] if step.get("voice")
        } if session else {}
        if session:
            voices.update({
                item["id"]: (self.folder / item["voice"]["file"]).as_uri()
                for item in session.get("unassigned_voices", [])
            })
        if self.draft and self.draft.get("duration_ms"):
            voices["draft"] = (self.folder / ".voice-pending.wav").as_uri()
        return {
            "recording": self.design is not None, "transcribing": self.job is not None,
            "session": session, "folder": str(self.folder) if self.folder else "",
            "voices": voices, "native_microphone": sys.platform == "darwin",
            "playing_voice": self.playback[0] if self.playback else None,
            "capturing": self.wav is not None or (self.mac_audio is not None and self.mac_audio.ready()),
            "starting_capture": self.mac_audio is not None and not self.mac_audio.ready(),
            "draft": self.draft is not None,
            "draft_duration_ms": self.draft.get("duration_ms") if self.draft else None,
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
            before = len(_recorder.operations)
            _recorder.observe(args.commandId, definition.name if definition else "")
            if len(_recorder.operations) != before and _palette and _palette.isValid:
                _palette.sendInfoToHTML("refresh", "{}")
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
                r.begin()
            elif action == "start_mac_voice":
                if sys.platform != "darwin":
                    raise ValueError("This recording method is for macOS.")
                r.start_mac_voice()
            elif action == "start_voice":
                rate = body.get("rate")
                if type(rate) is not int or not 8000 <= rate <= 96000:
                    raise ValueError("Unsupported audio sample rate.")
                r.start_voice(rate)
            elif action == "send_voice":
                r.send_voice(body.get("step"))
            elif action == "discard_voice":
                r.discard_voice()
            elif action == "play_voice":
                r.toggle_voice_playback(body.get("step"))
            elif action == "seal_voice":
                r.seal_voice()
            elif action == "bind_voice":
                r.bind_voice(body["voice"], body["step"])
            elif action == "import_voice":
                r.import_voice()
            elif action == "audio":
                r.append_audio(body["pcm"], body["frame"])
                args.returnData = '{"ok": true}'
                return
            elif action == "stop":
                r.finish(interrupted=bool(body.get("interrupted")))
            elif action in ("open", "import_wav", "transcribe"):
                if (r.design and action != "transcribe") or r.job:
                    raise ValueError("Finish the current recording or transcription first.")
                if action == "open":
                    r.open_session()
                elif action == "import_wav":
                    r.import_wav(int(body["offset_ms"]))
                else:
                    if body["language"] not in ("", "zh", "en"):
                        raise ValueError("Choose a supported transcription language.")
                    r.transcribe(body["language"], body.get("step"))
            elif action == "state":
                r.poll()
            else:
                raise ValueError("Unknown action: " + action)
            args.returnData = json.dumps({"ok": True, **r.state()})
        except Exception as error:
            args.returnData = json.dumps({"ok": False, "error": str(error), **r.state()})


def interrupt_recording():
    try:
        _recorder.stop_voice_playback()
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
        if _palette and _palette.isValid:
            _palette.isVisible = True
            _palette.sendInfoToHTML("refresh", "{}")
            return
        _palette_handlers.clear()
        _palette = _ui.palettes.add2(PALETTE_ID, "exCADmple Voice Recorder",
                                     _recorder.panel_url(), True, True, True, 420, 540)
        message, closed = PanelMessage(), PanelClosed()
        _palette.incomingFromHTML.add(message)
        _palette.closed.add(closed)
        _palette_handlers.extend((message, closed))
        _palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
        _palette.setMinimumSize(320, 260)
        _palette.setSize(420, 540)


def run(_context):
    global _app, _ui, _recorder, _definition, _control
    _app = adsk.core.Application.get()
    _ui = _app.userInterface
    _recorder = Recorder()
    show, terminated, workspace = ShowPanel(), CommandTerminated(), WorkspaceChanging()
    _definition = _ui.commandDefinitions.addButtonDefinition(
        COMMAND_ID, "exCADmple Voice Recorder", "Record voice messages and link them to modeling steps")
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
        _ui.messageBox("Switch to the Design workspace and run exCADmpleRecorder again.")


def stop(_context):
    global _recorder, _palette, _definition, _control
    try:
        if _recorder:
            _recorder.stop_voice_playback()
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
        if _recorder and _recorder.panel_directory:
            _recorder.panel_directory.cleanup()
        _handlers.clear()
        _palette_handlers.clear()
        _recorder = _palette = _definition = _control = None
