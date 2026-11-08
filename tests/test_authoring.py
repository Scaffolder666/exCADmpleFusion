"""Three source files -> version-2 example package."""
import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from core import transcript
from core.authoring import build_manifest, write_package, AuthoringError
from core.animation import animation_meshes
from core.packages import open_package, _validate


def tri(z):
    return {"vertices": [[0, 0, z], [1, 0, z], [0, 1, z]], "triangles": [[0, 1, 2]]}


EXTRACT = {
    "format": "excadmple-extract", "version": 1,
    "source": {"file": "Stand.f3d", "units": "cm"},
    "meshes": {"base": tri(0), "base_round": tri(0.1), "lip": tri(1)},
    "features": [
        {"index": 0, "name": "Sketch1", "kind": "Sketch", "parameters": [], "inputs": {}, "state": []},
        {"index": 1, "name": "Extrude1", "kind": "ExtrudeFeature",
         "parameters": [{"name": "d1", "expression": "7 mm", "value": 0.7, "unit": "mm"}],
         "inputs": {"sketches": [0], "features": []}, "state": ["base"]},
        {"index": 2, "name": "Fillet1", "kind": "FilletFeature",
         "parameters": [{"name": "d2", "expression": "8 mm", "value": 0.8, "unit": "mm"}],
         "inputs": {"sketches": [], "features": [1]}, "state": ["base_round"]},
        {"index": 3, "name": "Sketch2", "kind": "Sketch", "parameters": [], "inputs": {}, "state": ["base_round"]},
        {"index": 4, "name": "Extrude2", "kind": "ExtrudeFeature", "parameters": [],
         "inputs": {"sketches": [3], "features": [1]}, "state": ["base_round", "lip"]},
    ],
}
ANNOTATION = {
    "format": "excadmple-annotation", "version": 1,
    "id": "stand", "title": "Stand",
    "recording": {"audio": "session.wav"},
    "steps": [
        {"id": "base", "title": "Base", "features": ["Sketch1", "Extrude1", "Fillet1"],
         "recording": {"start_ms": 0, "end_ms": 20000}},
        {"id": "lip", "title": "Lip", "features": [3, 4],
         "recording": {"start_ms": 20000, "end_ms": 35000}},
    ],
}
SRT = """1
00:00:01,000 --> 00:00:04,000
I start with a wide base.

2
00:00:21,500 --> 00:00:24,000
Now a small lip at the front.
"""


class AuthoringTests(unittest.TestCase):
    def build(self, annotation=None):
        return build_manifest(EXTRACT, annotation or ANNOTATION, transcript.parse_cues(SRT))

    def test_manifest_follows_extract_annotation_and_transcript(self):
        m = self.build()
        self.assertEqual(m["version"], 2)
        base, lip = m["steps"]
        self.assertEqual(base["tools"], ["Sketch", "Extrude", "Fillet"])
        self.assertEqual(set(base) - {"geometry", "animation"},
                         {"id", "title", "duration_ms", "tools", "source_features", "cues", "media"})
        # before (empty) -> after extrude -> after fillet; the sketch adds no state
        self.assertEqual(base["animation"]["states"], [[], ["base"], ["base_round"]])
        self.assertEqual(base["geometry"]["meshes"], ["base_round"])
        self.assertEqual(sorted(m["meshes"]), ["base", "base_round", "lip"])
        expanded = _validate(json.loads(json.dumps(m)))           # ids -> meshes on load
        step = expanded["steps"][0]
        self.assertEqual(animation_meshes(step["animation"], 1.0), [tri(0.1)])
        self.assertEqual(base["cues"], [{"at_ms": 1000, "label": "I start with a wide base."}])
        self.assertEqual(lip["cues"][0]["at_ms"], 1500)
        self.assertEqual(lip["media"], {"audio": "media/session.wav", "offset_ms": 20000})
        self.assertEqual([f["name"] for f in lip["source_features"]], ["Sketch2", "Extrude2"])

    def test_package_roundtrip_with_recording(self):
        m = self.build()
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "session.wav"
            audio.write_bytes(b"RIFF....WAVE")
            out = write_package(m, Path(tmp) / "stand.excadmple", [audio])
            with zipfile.ZipFile(out) as z:
                self.assertEqual(sorted(z.namelist()), ["manifest.json", "media/session.wav"])
            package = open_package(out)
            try:
                meta = package.player_data()
                self.assertEqual(meta["steps"][1]["media"]["offset_ms"], 20000)
                self.assertTrue(meta["steps"][1]["media"]["audio"].startswith("file:"))
            finally:
                package.close()
            with self.assertRaises(AuthoringError):
                write_package(m, Path(tmp) / "x.excadmple", [])

    def test_errors_are_explicit(self):
        bad = copy.deepcopy(ANNOTATION)
        bad["steps"][1]["features"] = ["Extrude1"]
        with self.assertRaisesRegex(AuthoringError, "overlaps"):
            self.build(bad)
        bad = copy.deepcopy(ANNOTATION)
        bad["steps"][1]["features"] = ["Nope"]
        with self.assertRaisesRegex(AuthoringError, "Nope"):
            self.build(bad)
        bad = copy.deepcopy(ANNOTATION)
        del bad["steps"][0]["recording"]
        with self.assertRaisesRegex(AuthoringError, "recording"):
            self.build(bad)


class TranscriptTests(unittest.TestCase):
    def test_vtt_and_json(self):
        vtt = "WEBVTT\n\n00:01.200 --> 00:03.000 align:start\n<v Designer>Wide base first.\n\nNOTE skip\n\n1:00:00.000 --> 1:00:01.000\nLate\n"
        segs = transcript.parse_cues(vtt)
        self.assertEqual(segs[0], {"start_ms": 1200, "end_ms": 3000, "text": "Wide base first."})
        self.assertEqual(segs[1]["start_ms"], 3600000)
        with self.assertRaises(transcript.TranscriptError):
            transcript.validate([{"start_ms": 5, "text": "a"}, {"start_ms": 1, "text": "b"}])


if __name__ == "__main__":
    unittest.main()


class SourceModelTests(unittest.TestCase):
    def test_source_f3d_travels_in_the_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            f3d = Path(tmp) / "Stand.f3d"
            f3d.write_bytes(b"fake f3d")
            audio = Path(tmp) / "session.wav"
            audio.write_bytes(b"RIFF")
            m = build_manifest(EXTRACT, ANNOTATION, transcript.parse_cues(SRT), source_model=f3d)
            self.assertEqual(m["source_model"], "source/Stand.f3d")
            out = write_package(m, Path(tmp) / "s.excadmple", [audio], f3d)
            package = open_package(out)
            try:
                self.assertEqual(package.source_model_path().read_bytes(), b"fake f3d")
                self.assertEqual(package.source_path, out.resolve())
            finally:
                package.close()

