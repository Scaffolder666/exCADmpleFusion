"""Fusion side of the authoring tool (panel: ui/author).

The designer models in their own Design and presses Record. While they
think aloud, this logs the features they make (core/session_recorder.py)
and stores the voice the panel records with the microphone. On Stop the
features are grouped into draft reasoning steps (core/tutorial/
authoring_draft.py), which the designer edits in the panel. Saving writes
the tutorial into the Design itself (Fusion attributes) and exports one
.f3d that carries it; the voice recording is saved beside it.

Nothing in the geometry or Timeline is changed. Only the attributes of the
"exCADmple" group are written, and only on Save.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import adsk.core
import adsk.fusion

from . import transcript as transcript_io
from .session_recorder import SessionRecorder, timeline_items
from .tutorial.authoring_draft import Draft, DraftError, draft_from_recording
from .tutorial.example_pair import EMBED_GROUP, embedded_chunks, read_embedded

MAX_AUDIO_BYTES = 1024 * 1024 * 1024      # 16 kHz mono: about 9 hours
WORK_ROOT = Path.home() / "exCADmple-tutorials"


def _safe_name(text):
    keep = "".join(c if c.isalnum() or c in "-_ " else "_" for c in (text or "tutorial")).strip()
    return keep[:60] or "tutorial"


def _features(design):
    return [{"index": i, "name": n, "kind": k} for i, n, k in timeline_items(design)]


class Authoring:
    def __init__(self, app, ui, root, post, note, load_tutorial):
        self.app, self.ui, self.root = app, ui, Path(root)
        self.post, self.note, self.load_tutorial = post, note, load_tutorial
        self.recorder = SessionRecorder(app, ui)
        self.design = None
        self.session = None             # the recorder's log of the last recording
        self.draft = None
        self.title = ""
        self.work = None                # folder of this tutorial's recording
        self.audio = None               # Path of the voice / screen recording
        self.audio_start_ms = 0         # session time at which the audio starts
        self.audio_imported = False
        self._audio_file = None
        self._audio_bytes = 0
        self._transcribe = None         # (Popen, output path)
        self.message = ""

    # --- state shown in the panel ----------------------------------------------------------
    def state(self):
        return {
            "recording": self.recorder.recording,
            "voice": self._audio_file is not None,
            "design": self._design_name(),
            "title": self.title,
            "draft": self.draft.view() if self.draft else None,
            "audio": self.audio.as_uri() if self.audio and self.audio.is_file() else None,
            "audio_name": self.audio.name if self.audio else "",
            # Only an imported recording can have started before Record.
            "audio_lead_s": round(-self.audio_start_ms / 1000.0, 2) if self.session and self.audio_imported else None,
            "transcribing": self._transcribe is not None,
            "work": str(self.work) if self.work else "",
            "message": self.message,
        }

    def publish(self, message=None):
        if message is not None:
            self.message = message
        self.post("state", self.state())

    def _design_name(self):
        try:
            return self.design.parentDocument.name if self.design else ""
        except Exception:
            return ""

    def _active_design(self):
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        if not design:
            raise ValueError("Open the Design you are modeling first")
        if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
            raise ValueError("The tutorial needs a parametric design (with a Timeline)")
        return design

    def _work_folder(self, design):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        folder = WORK_ROOT / "{}-{}".format(_safe_name(design.parentDocument.name), stamp)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    # --- opening ---------------------------------------------------------------------------
    def open(self):
        """Panel opened: continue the tutorial stored in the active Design, if any."""
        if self.draft is not None or self.recorder.recording:
            return self.publish()
        try:
            design = self._active_design()
        except ValueError:
            return self.publish("Open your Design, then press Record.")
        self.design = design
        try:
            data = read_embedded(design)
        except Exception as error:
            return self.publish(str(error))
        if data and data.get("authoring"):
            try:
                self.draft = Draft.from_dict(data["authoring"], _features(design))
                self.title = data.get("title") or ""
                return self.publish("Continued the tutorial saved in this design. "
                                    "Import its recording again to listen to it.")
            except DraftError as error:
                return self.publish("The tutorial saved in this design no longer matches it: {}".format(error))
        self.publish("Press Record, then model and think aloud.")

    # --- recording -------------------------------------------------------------------------
    def start(self):
        if self.recorder.recording:
            raise ValueError("Already recording")
        design = self._active_design()
        self.design = design
        self.work = self._work_folder(design)
        self.title = self.title or design.parentDocument.name
        self.session = None
        self.draft = None
        self.audio = None
        self.audio_start_ms = 0
        self.recorder.begin(design)
        self.note("authoring", "recording started", {"design": self._design_name(), "work": str(self.work)})
        self.publish("Recording. Model as usual and say why you do what you do.")

    def audio_start(self, rate):
        """The panel starts sending the voice: 16-bit mono PCM at ``rate`` Hz."""
        if not self.recorder.recording:
            raise ValueError("Not recording")
        rate = int(rate or 16000)
        if not 8000 <= rate <= 96000:
            raise ValueError("Unsupported sample rate")
        self.audio = self.work / "voice.wav"
        self.audio_imported = False
        self._audio_file = wave.open(str(self.audio), "wb")
        self._audio_file.setnchannels(1)
        self._audio_file.setsampwidth(2)
        self._audio_file.setframerate(rate)
        self._audio_bytes = 0
        self.audio_start_ms = self.recorder.log.now_ms()
        self.publish()

    def audio_chunk(self, data):
        if self._audio_file is None:
            return
        chunk = base64.b64decode(data or "")
        self._audio_bytes += len(chunk)
        if self._audio_bytes > MAX_AUDIO_BYTES:
            raise ValueError("The voice recording is too long")
        self._audio_file.writeframes(chunk)

    def audio_stop(self):
        if self._audio_file is not None:
            self._audio_file.close()          # writes the WAV header's final length
            self._audio_file = None

    def stop(self):
        if not self.recorder.recording:
            raise ValueError("Not recording")
        self.audio_stop()
        self.session = self.recorder.finish()
        with open(self.work / "session.json", "w", encoding="utf-8") as handle:
            json.dump(self.session, handle, indent=1)
        self._rebuild()
        self.note("authoring", "recording stopped", {
            "features": len(self.session["features"]), "duration_ms": self.session["duration_ms"],
            "audio": str(self.audio) if self.audio else None})
        found = len(self.session["features"])
        self.publish("Recorded {} new feature{}. Group them into reasoning steps below.".format(
            found, "" if found == 1 else "s"))

    def _rebuild(self):
        """Group the Timeline again from the recording (edits are lost)."""
        segments = self.draft.segments if self.draft else []
        self.draft = draft_from_recording(timeline_items(self.design), self.session, self.audio_start_ms)
        self.draft.set_segments(segments)

    def prepare(self):
        """No recording: explain an existing design with an imported recording."""
        design = self._active_design()
        self.design = design
        self.work = self.work or self._work_folder(design)
        self.title = self.title or design.parentDocument.name
        self.session = None
        self.audio_start_ms = 0
        segments = self.draft.segments if self.draft else []
        self.draft = Draft([dict(f, t_ms=None) for f in _features(design)], 0, segments)
        self.publish("One step per feature. Import the recording and its transcript, then group the steps.")

    def cancel(self):
        self.audio_stop()
        self.recorder.cancel()

    # --- recording and transcript from files -------------------------------------------------
    def _choose(self, title, file_filter):
        dialog = self.ui.createFileDialog()
        dialog.title = title
        dialog.filter = file_filter
        if dialog.showOpen() != adsk.core.DialogResults.DialogOK:
            return None
        return Path(dialog.filename)

    def import_audio(self):
        path = self._choose("Recording of what you said (audio or screen recording)",
                            "Audio or video (*.webm;*.ogg;*.m4a;*.mp3;*.wav;*.mp4;*.mov)")
        if path:
            self.audio = path
            self.audio_imported = True
            self.publish("Using {}.".format(path.name))

    def set_audio_lead(self, seconds):
        """The imported recording started ``seconds`` before Record was pressed."""
        if not self.session:
            raise ValueError("Only a recording made with Record has feature times to align")
        self.audio_start_ms = -int(round(float(seconds) * 1000))
        self._rebuild()
        self.publish("Steps regrouped for the new start of the recording.")

    def set_audio_duration(self, duration_ms):
        if self.draft and isinstance(duration_ms, (int, float)) and duration_ms > 0:
            self.draft.set_duration(duration_ms)
            self.publish()

    def import_transcript(self):
        path = self._choose("Transcript of the recording", "Transcript (*.srt;*.vtt;*.json)")
        if path:
            self._use_transcript(path)

    def _use_transcript(self, path):
        if not self.draft:
            raise ValueError("Record or prepare the steps first")
        segments = transcript_io.load(path)
        self.draft.set_segments(segments)
        self.publish("{} sentences from {} matched to the steps by time.".format(len(segments), Path(path).name))

    def transcribe(self):
        """Run tools/transcribe.py (faster-whisper) outside Fusion."""
        if not self.audio or not self.audio.is_file():
            raise ValueError("There is no recording to transcribe")
        if self._transcribe:
            raise ValueError("Already transcribing")
        python = self._python()
        output = (self.work or self.audio.parent) / "transcript.srt"
        log = open(output.with_suffix(".log"), "w", encoding="utf-8")
        process = subprocess.Popen([python, str(self.root / "tools" / "transcribe.py"), str(self.audio),
                                    "-o", str(output)], stdout=log, stderr=subprocess.STDOUT,
                                   cwd=str(self.root))
        log.close()
        self._transcribe = (process, output)
        self.publish("Transcribing on this computer (this can take a few minutes)…")

    def _python(self):
        try:
            configured = json.loads((self.root / "config.json").read_text(encoding="utf-8")).get("python")
        except Exception:
            configured = None
        for candidate in (configured, "python3", "python"):
            if candidate and shutil.which(candidate):
                return shutil.which(candidate)
        raise ValueError('No Python found to run the transcription. Set "python" in config.json, '
                         "or import a transcript (.srt) made with any tool.")

    def poll_transcribe(self):
        if not self._transcribe:
            return self.publish()
        process, output = self._transcribe
        if process.poll() is None:
            return
        self._transcribe = None
        if process.returncode == 0 and output.is_file():
            return self._use_transcript(output)
        try:
            detail = output.with_suffix(".log").read_text(encoding="utf-8").strip().splitlines()[-1]
        except Exception:
            detail = "exit code {}".format(process.returncode)
        self.publish("Transcription failed: " + detail)

    # --- editing ---------------------------------------------------------------------------
    def edit(self, action, body):
        if not self.draft:
            raise ValueError("Record or prepare the steps first")
        d = self.draft
        if action == "merge":
            d.merge(body.get("step"))
        elif action == "split":
            d.split(body.get("step"), body.get("at"))
        elif action == "move_sentence":
            d.move_sentence(body.get("step"), -1 if body.get("direction", 1) < 0 else 1)
        elif action == "rename":
            d.rename(body.get("step"), body.get("title", ""))
        elif action == "set_text":
            d.set_text(body.get("step"), body.get("text"))
        elif action == "regroup":
            if self.session:
                self._rebuild()
            else:
                segments = d.segments
                self.draft = Draft([dict(f, t_ms=None) for f in d.features], d.duration_ms, segments)
        elif action == "set_title":
            self.title = str(body.get("title", "")).strip()[:120]
        else:
            raise ValueError("Unknown edit: " + str(action))
        self.publish("")

    # --- saving ----------------------------------------------------------------------------
    def _pair(self, model_name, audio_name):
        return self.draft.to_pair(model_name, self.title or self._design_name(), audio=audio_name)

    def _check_design(self):
        if not self.draft or not self.design or not self.design.isValid:
            raise ValueError("Record or prepare the steps first")
        if [(f["index"], f["name"], f["kind"]) for f in self.draft.features] != \
                [(f["index"], f["name"], f["kind"]) for f in _features(self.design)]:
            raise ValueError("The design's Timeline changed after the steps were made. "
                             "Press Regroup to start the steps again from the Timeline.")

    def _embed(self, pair):
        attributes = self.design.attributes
        for old in list(attributes.itemsByGroup(EMBED_GROUP)):
            old.deleteMe()
        for name, value in embedded_chunks(json.dumps(pair, ensure_ascii=False)):
            attributes.add(EMBED_GROUP, name, value)

    def _write(self, f3d):
        """The .f3d with the tutorial inside, and the recording beside it."""
        self._check_design()
        f3d = Path(f3d)
        audio_name = None
        if self.audio and self.audio.is_file():
            audio_name = f3d.stem + self.audio.suffix.lower()
            target = f3d.with_name(audio_name)
            if target.resolve() != self.audio.resolve():
                shutil.copyfile(self.audio, target)
        pair = self._pair(f3d.name, audio_name)
        self._embed(pair)
        manager = self.design.exportManager
        if not manager.execute(manager.createFusionArchiveExportOptions(str(f3d), self.design.rootComponent)):
            raise RuntimeError("Fusion could not export " + f3d.name)
        self.note("authoring", "saved", {"f3d": str(f3d), "audio": audio_name, "steps": len(pair["steps"])})
        return f3d, audio_name

    def save(self):
        self._check_design()
        dialog = self.ui.createFileDialog()
        dialog.title = "Save the design with its tutorial inside"
        dialog.filter = "Fusion archive (*.f3d)"
        dialog.initialFilename = _safe_name(self.title or self._design_name()) + ".f3d"
        if dialog.showSave() != adsk.core.DialogResults.DialogOK:
            return
        path = Path(dialog.filename)
        if path.suffix.lower() != ".f3d":
            path = path.with_suffix(".f3d")
        f3d, audio_name = self._write(path)
        extra = " and {} beside it".format(audio_name) if audio_name else ""
        self.publish("Saved {}{}. Share the .f3d{}; open it with + Import in the player.".format(
            f3d.name, extra, " and the recording" if audio_name else ""))

    def preview(self):
        """Play the tutorial as a learner will see it, in the player."""
        self._check_design()
        folder = (self.work or WORK_ROOT) / "preview"
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)
        f3d, _ = self._write(folder / (_safe_name(self.title or self._design_name()) + ".f3d"))
        self.load_tutorial(str(f3d))
        self.publish("Playing the tutorial in the exCADmple player.")


def open_folder(path):
    """Show a folder in Finder / Explorer."""
    path = str(path)
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif os.name == "nt":
        os.startfile(path)   # noqa: S606 (Windows only)
    else:
        subprocess.Popen(["xdg-open", path])
