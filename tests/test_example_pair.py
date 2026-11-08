"""Integration contracts for the local JSON + original Fusion .f3d workflow.

These are pure-Python tests. Fusion Desktop must still validate that the
actual native model imports and the Feature Timeline recomputes correctly.
"""
import hashlib
import json
import tempfile
import types
import unittest
from pathlib import Path

from core.packages import open_package, PackageError
from core.example_pair import hypothetical_transcript

class LocalExamplePairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.model = self.folder / "fusion.f3d"
        self.original_bytes = b"test f3d bytes: not real Fusion geometry"
        self.model.write_bytes(self.original_bytes)
        self.config = self.folder / "fusion_example.json"
        self.raw = {
            "format": "excadmple-pair", "version": 1,
            "title": "Native example", "model": "fusion.f3d",
            "model_sha256": hashlib.sha256(self.original_bytes).hexdigest(),
            "auto_generate": True, "step_duration_ms": 8000,
            "steps": [],
        }
        self.features = [
            types.SimpleNamespace(index=0, name="Sketch1", kind="Sketch"),
            types.SimpleNamespace(index=1, name="Extrude1", kind="ExtrudeFeature"),
            types.SimpleNamespace(index=2, name="Extrude1", kind="ExtrudeFeature"),
            types.SimpleNamespace(index=3, name="Revolve1", kind="RevolveFeature"),
            types.SimpleNamespace(index=4, name="Combine1", kind="CombineFeature"),
        ]
        self.write()

    def write(self):
        self.config.write_text(json.dumps(self.raw), encoding="utf-8")

    def test_auto_generates_one_step_per_true_feature_and_editable_json(self):
        pkg = open_package(self.config)
        self.assertTrue(pkg.needs_populate)
        self.assertEqual(pkg.source_model_path(), self.model)
        pkg.populate_from_features(self.features)
        self.assertEqual(len(pkg.data["steps"]), 5)
        self.assertEqual([s["source_features"][0]["index"] for s in pkg.data["steps"]],
                         [0, 1, 2, 3, 4])
        self.assertEqual(pkg.data["steps"][1]["tools"], ["Extrude"])
        self.assertIn("SIMULATED DESIGN EXPLANATION", pkg.data["steps"][1]["cues"][0]["label"])
        self.assertIn("not the original designer's words", pkg.data["steps"][1]["cues"][0]["label"])
        self.assertFalse(any(s["geometry"]["meshes"] for s in pkg.data["steps"]))
        self.assertIsNotNone(pkg.generated_path)
        saved = json.loads(pkg.generated_path.read_text(encoding="utf-8"))
        self.assertFalse(saved["auto_generate"])
        self.assertEqual(saved["steps"][2]["features"][0]["index"], 2)
        self.assertEqual(self.model.read_bytes(), self.original_bytes)
        meta = pkg.player_data()
        self.assertEqual(len(meta["steps"]), 5)
        self.assertTrue(meta["source_model_included"])
        self.assertEqual(meta["steps"][1]["media"], {})
        pkg.close()

    def test_generated_annotations_are_reusable_and_editable(self):
        original = open_package(self.config)
        original.populate_from_features(self.features)
        annotated = original.generated_path
        raw = json.loads(annotated.read_text(encoding="utf-8"))
        raw["steps"][1]["transcript"] = "Human-edited explanation for the extrude."
        raw["steps"][1].pop("cues")
        annotated.write_text(json.dumps(raw), encoding="utf-8")
        pkg = open_package(annotated)
        pkg.populate_from_features(self.features)
        self.assertEqual(pkg.data["steps"][1]["cues"][0]["label"],
                         "Human-edited explanation for the extrude.")
        self.assertFalse(pkg.needs_populate)
        self.assertEqual(self.model.read_bytes(), self.original_bytes)

    def test_duplicate_names_must_use_timeline_indices(self):
        self.raw["auto_generate"] = False
        self.raw["steps"] = [{"title": "Ambiguous feature", "features": ["Extrude1"]}]
        self.write()
        with self.assertRaisesRegex(PackageError, "ambiguous"):
            open_package(self.config).populate_from_features(self.features)
        self.raw["steps"] = [{"title": "Second extrude",
                              "features": [{"index": 2, "name": "Extrude1", "kind": "ExtrudeFeature"}],
                              "transcript": "A recorded annotation."}]
        self.write()
        pkg = open_package(self.config)
        pkg.populate_from_features(self.features)
        self.assertEqual(pkg.data["steps"][0]["source_features"][0]["index"], 2)
        self.assertEqual(pkg.data["steps"][0]["cues"][0]["label"], "A recorded annotation.")

    def test_detects_modified_timeline_and_file_hash_mismatch(self):
        self.raw["auto_generate"] = False
        self.raw["steps"] = [{"features": [{"index": 1, "name": "WrongName"}]}]
        self.write()
        with self.assertRaisesRegex(PackageError, "Timeline changed"):
            open_package(self.config).populate_from_features(self.features)
        self.model.write_bytes(b"new contents")
        with self.assertRaisesRegex(PackageError, "SHA-256"):
            open_package(self.config)

    def test_prevent_paths_outside_example_folder(self):
        for filename in ("../fusion.f3d", "C:\\fusion.f3d", "/tmp/fusion.f3d"):
            self.raw["model"] = filename
            self.write()
            with self.assertRaises(PackageError):
                open_package(self.config)

    def test_optional_real_audio_in_same_folder(self):
        self.raw["auto_generate"] = False
        self.raw["audio"] = "thinking.wav"
        self.raw["steps"] = [{"title": "First feature", "features": [0],
                              "transcript": "This is recorded speech."}]
        (self.folder / "thinking.wav").write_bytes(b"RIFF")
        self.write()
        pkg = open_package(self.config)
        pkg.populate_from_features(self.features)
        self.assertEqual(pkg.data["steps"][0]["media"]["audio"], "thinking.wav")
        self.assertTrue(pkg.player_data()["steps"][0]["media"]["audio"].startswith("file:"))

    def test_missing_fusion_history_or_excessive_length_is_explicit(self):
        pkg = open_package(self.config)
        with self.assertRaisesRegex(PackageError, "no accessible parametric"):
            pkg.populate_from_features([])
        huge = [types.SimpleNamespace(index=i, name="Feature" + str(i), kind="Sketch")
                for i in range(151)]
        with self.assertRaisesRegex(PackageError, "maximum"):
            pkg.populate_from_features(huge)

    def test_hypothetical_text_is_not_mislabeled_as_real_speech(self):
        text = hypothetical_transcript("Revolve2", "RevolveFeature")
        self.assertIn("SIMULATED", text)
        self.assertIn("not the original designer", text)
        self.assertIn("rotationally symmetric", text)


if __name__ == "__main__":
    unittest.main()
