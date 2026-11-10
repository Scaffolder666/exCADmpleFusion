"""Authoring tool, Fusion side, on a stub Fusion API.

Checks the add-in's own logic: the recording is logged on the design being
modeled, the voice is written as a seekable WAV, the steps are made from
the final Timeline, and Save stores the tutorial in the Design's attributes
and exports one .f3d with the recording beside it. Whether Fusion keeps the
attributes in an exported .f3d, and whether the panel may use the
microphone, needs Fusion Desktop (docs/AUTHORING_TEST.md).
"""
import base64
import json
import tempfile
import types
import unittest
import wave
from pathlib import Path

from tests import test_him_fusion_adapter as stub        # installs the adsk stub
import adsk.core
import adsk.fusion

for _name in ("ApplicationCommandEventHandler", "ActiveSelectionEventHandler"):
    if not hasattr(adsk.core, _name):
        setattr(adsk.core, _name, type(_name, (), {"__init__": lambda self: None}))
adsk.core.DialogResults = getattr(adsk.core, "DialogResults", types.SimpleNamespace(DialogOK=1))
adsk.core.MessageBoxButtonTypes = getattr(adsk.core, "MessageBoxButtonTypes",
                                          types.SimpleNamespace(OKCancelButtonType=1))

from core import authoring_fusion  # noqa: E402
from core.playback.him_filter import FeatureInfo  # noqa: E402
from core.tutorial.example_pair import read_embedded  # noqa: E402
from core.tutorial.packages import open_package  # noqa: E402

Obj, Coll, Timeline, TimelineObj = stub.Obj, stub.Coll, stub.Timeline, stub.TimelineObj


class Event:
    def __init__(self):
        self.handlers = []

    def add(self, handler):
        self.handlers.append(handler)

    def remove(self, handler):
        self.handlers.remove(handler)


class Attribute:
    def __init__(self, store, group, name, value):
        self.store, self.groupName, self.name, self.value = store, group, name, value

    def deleteMe(self):
        del self.store[(self.groupName, self.name)]


class Attributes:
    def __init__(self):
        self.store = {}

    def add(self, group, name, value):
        self.store[(group, name)] = Attribute(self.store, group, name, value)
        return self.store[(group, name)]

    def itemByName(self, group, name):
        return self.store.get((group, name))

    def itemsByGroup(self, group):
        return [a for (g, _), a in self.store.items() if g == group]


class ExportManager:
    def __init__(self):
        self.exported = []

    def createFusionArchiveExportOptions(self, path, component):
        return path

    def execute(self, path):
        Path(path).write_bytes(b"f3d")
        self.exported.append(path)
        return True


def feature(name, kind):
    return Obj("Feature", name.lower(), name=name, objectType="adsk::fusion::" + kind)


def design():
    timeline = Timeline()
    d = Obj("Design", "design", designType=1, timeline=timeline, isValid=True,
            parentDocument=types.SimpleNamespace(name="Phone stand"), attributes=Attributes(),
            exportManager=ExportManager(), rootComponent=object())
    return d


def add(d, name, kind):
    d.timeline.append(TimelineObj(d.timeline, len(d.timeline), feature(name, kind)))


class Dialog:
    def __init__(self, filename):
        self.filename = filename

    def showSave(self):
        return adsk.core.DialogResults.DialogOK

    showOpen = showSave


class AuthoringTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.addCleanup(setattr, authoring_fusion, "WORK_ROOT", authoring_fusion.WORK_ROOT)
        authoring_fusion.WORK_ROOT = self.folder / "work"
        self.design = design()
        add(self.design, "Base", "BaseFeature")               # made before the recording
        self.app = types.SimpleNamespace(activeProduct=self.design)
        self.dialogs = []
        self.ui = types.SimpleNamespace(commandStarting=Event(), commandTerminated=Event(),
                                        activeSelectionChanged=Event(),
                                        createFileDialog=lambda: self.dialogs.pop(0))
        self.states, self.loaded = [], []
        self.clock = [100.0]
        self.authoring = authoring_fusion.Authoring(
            self.app, self.ui, Path(__file__).resolve().parents[1],
            lambda action, payload: self.states.append(payload), lambda *a: None, self.loaded.append)

    def record(self):
        a = self.authoring
        a.start()
        log = a.recorder.log
        log._clock = lambda: self.clock[0]
        log._start = 100.0
        self.clock[0] = 100.5
        a.audio_start(16000)                                  # voice starts 0.5 s after Record
        a.audio_chunk(base64.b64encode(b"\x00\x01" * 16000).decode())
        for t, name, kind in ((106.5, "Sketch1", "Sketch"), (112.5, "Extrude1", "ExtrudeFeature"),
                              (125.5, "Fillet1", "FilletFeature")):
            self.clock[0] = t
            add(self.design, name, kind)
            a.recorder.check_timeline()
        self.clock[0] = 140.5
        a.stop()

    def test_recording_makes_steps_from_the_timeline_and_a_wav(self):
        self.record()
        a = self.authoring
        self.assertFalse(self.ui.commandStarting.handlers)        # handlers removed
        with wave.open(str(a.audio)) as voice:
            self.assertEqual((voice.getframerate(), voice.getnframes()), (16000, 16000))
        steps = a.draft.view()["steps"]
        self.assertEqual([[f["name"] for f in s["features"]] for s in steps],
                         [["Base"], ["Sketch1", "Extrude1"], ["Fillet1"]])
        self.assertEqual([f["t_ms"] for f in a.draft.features], [None, 6000, 12000, 25000])
        self.assertEqual(a.draft.duration_ms, 40000)
        session = json.loads((a.work / "session.json").read_text())
        self.assertEqual(len(session["features"]), 3)
        self.assertIsNone(self.states[-1]["audio_lead_s"])        # recorded here: nothing to align

    def test_save_puts_the_tutorial_inside_the_f3d(self):
        self.record()
        a = self.authoring
        a.edit("merge", {"step": 0})
        a.edit("set_title", {"title": "Phone stand"})
        target = self.folder / "share" / "Stand.f3d"
        target.parent.mkdir()
        self.dialogs.append(Dialog(str(target)))
        a.save()
        self.assertEqual(self.design.exportManager.exported, [str(target)])
        self.assertTrue((target.parent / "Stand.wav").is_file())
        pair = read_embedded(self.design)
        self.assertEqual(pair["model"], "Stand.f3d")
        self.assertEqual([len(s["features"]) for s in pair["steps"]], [3, 1])
        self.assertEqual(pair["steps"][1]["audio"], "Stand.wav")
        # Saving again replaces the stored tutorial instead of adding to it.
        self.dialogs.append(Dialog(str(target)))
        a.save()
        self.assertEqual(len(self.design.attributes.itemsByGroup("exCADmple")), 2)
        # The player reads it back from the (imported) design.
        package = open_package(target)
        features = [FeatureInfo(i, n, k) for i, n, k in authoring_fusion.timeline_items(self.design)]
        steps = package.populate_from_features(features, model=types.SimpleNamespace(design=self.design))
        self.assertEqual(steps[1]["media"]["offset_ms"], pair["steps"][1]["audio_offset_ms"])

    def test_reopening_the_design_continues_the_draft(self):
        self.record()
        self.authoring.edit("rename", {"step": 1, "title": "The base plate"})
        self.dialogs.append(Dialog(str(self.folder / "Stand.f3d")))
        self.authoring.save()
        again = authoring_fusion.Authoring(self.app, self.ui, Path("."), lambda *a: None,
                                           lambda *a: None, lambda *a: None)
        again.open()
        self.assertEqual(again.draft.view()["steps"][1]["title"], "The base plate")
        add(self.design, "Chamfer1", "ChamferFeature")         # the design changed since
        later = authoring_fusion.Authoring(self.app, self.ui, Path("."), lambda *a: None,
                                           lambda *a: None, lambda *a: None)
        later.open()
        self.assertIsNone(later.draft)
        self.assertIn("no longer matches", later.message)

    def test_preview_plays_the_saved_tutorial(self):
        self.record()
        self.authoring.preview()
        self.assertEqual(len(self.loaded), 1)
        self.assertTrue(self.loaded[0].endswith(".f3d"))
        self.assertTrue(Path(self.loaded[0]).with_suffix(".wav").is_file())

    def test_timeline_changed_after_recording(self):
        self.record()
        add(self.design, "Chamfer1", "ChamferFeature")
        with self.assertRaisesRegex(ValueError, "Regroup"):
            self.authoring.preview()
        self.authoring.edit("regroup", {})
        self.authoring.preview()

    def test_existing_design_without_recording(self):
        add(self.design, "Extrude1", "ExtrudeFeature")
        self.authoring.prepare()
        self.assertEqual(len(self.authoring.draft.steps), 2)
        audio = self.folder / "screen.mp4"
        audio.write_bytes(b"video")
        self.dialogs.append(Dialog(str(audio)))
        self.authoring.import_audio()
        self.authoring.set_audio_duration(60000)
        self.assertEqual(self.authoring.draft.view()["steps"][-1]["end_ms"], 60000)
        srt = self.folder / "talk.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nA flat base first.\n\n"
                       "2\n00:00:40,000 --> 00:00:42,000\nThen it gets taller.\n", encoding="utf-8")
        self.dialogs.append(Dialog(str(srt)))
        self.authoring.import_transcript()
        texts = [s["text"] for s in self.authoring.draft.view()["steps"]]
        self.assertEqual(texts, ["A flat base first.", "Then it gets taller."])
        with self.assertRaisesRegex(ValueError, "Record"):
            self.authoring.set_audio_lead(2)

    def test_imported_recording_can_be_aligned(self):
        self.record()
        audio = self.folder / "screen.mp4"
        audio.write_bytes(b"video")
        self.dialogs.append(Dialog(str(audio)))
        self.authoring.import_audio()
        self.authoring.set_audio_lead(2)            # the screen recording started 2 s before Record
        self.assertEqual([f["t_ms"] for f in self.authoring.draft.features], [None, 8500, 14500, 27500])
        self.assertEqual(self.states[-1]["audio_lead_s"], 2.0)


if __name__ == "__main__":
    unittest.main()
