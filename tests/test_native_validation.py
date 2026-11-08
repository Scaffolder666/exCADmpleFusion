"""Regression tests for the real-.f3d HiM validation packaging workflow.

These check exact timeline mapping and embedded source bytes. They cannot
verify Fusion Desktop's parametric recomputation or any specific user model.
"""
import tempfile
import unittest
from pathlib import Path

from core.packages import open_package
from tests.test_authoring import EXTRACT
from tools.build_native_validation import (native_only_manifest, make_annotation, make_package,
                                           hypothetical_reasoning, synthetic_reasoning_segments)


class NativeValidationTests(unittest.TestCase):
    def test_one_step_per_timeline_feature_with_exact_index(self):
        annotation = make_annotation(EXTRACT, "Actual Fusion design")
        steps = annotation["steps"]
        self.assertEqual(len(steps), len(EXTRACT["features"]))
        self.assertEqual([s["features"] for s in steps], [[0], [1], [2], [3], [4]])
        self.assertEqual([s["title"] for s in steps],
                         ["Sketch1", "Extrude1", "Fillet1", "Sketch2", "Extrude2"])
        self.assertEqual([s["recording"] for s in steps],
                         [{"start_ms": i * 4000, "end_ms": (i + 1) * 4000}
                          for i in range(len(steps))])

    def test_native_model_embedded_and_no_fabricated_transcript(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "fusion.f3d"
            source.write_bytes(b"test-only stand-in for a Fusion archive")
            output = Path(folder) / "native.excadmple"
            result, count = make_package(EXTRACT, source, output, "Actual Fusion design")
            self.assertEqual(result, output)
            self.assertEqual(count, len(EXTRACT["features"]))
            package = open_package(output)
            try:
                self.assertEqual(package.source_model_path().read_bytes(), source.read_bytes())
                self.assertEqual(len(package.data["steps"]), 5)
                self.assertTrue(all(step["cues"] == [] and step["media"] == {}
                                    for step in package.data["steps"]))
                self.assertEqual([step["source_features"][0]["index"]
                                  for step in package.data["steps"]], [0, 1, 2, 3, 4])
            finally:
                package.close()

    def test_synthetic_reasoning_uses_real_feature_metadata_not_claimed_intent(self):
        cues = synthetic_reasoning_segments(EXTRACT)
        self.assertEqual(len(cues), len(EXTRACT["features"]))
        self.assertEqual(cues[0]["start_ms"], 250)
        self.assertEqual(cues[-1]["start_ms"], 4 * 4000 + 250)
        for cue in cues:
            self.assertIn("SIMULATED TEST REASONING", cue["text"])
            self.assertIn("not the designer's words", cue["text"])
        extrude = hypothetical_reasoning(EXTRACT["features"][1])
        self.assertIn("Extrude1", extrude)
        self.assertIn("d1 = 7 mm", extrude)
        self.assertIn("Earlier timeline references: 0", extrude)
        self.assertIn("possible consideration", extrude.lower())

    def test_synthetic_reasoning_is_separate_from_original_recording(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "fusion.f3d"
            source.write_bytes(b"unchanged source model")
            destination = Path(folder) / "native-reasoning.excadmple"
            make_package(EXTRACT, source, destination, synthetic_reasoning=True)
            package = open_package(destination)
            try:
                steps = package.data["steps"]
                self.assertEqual(len(steps), 5)
                self.assertEqual([len(s["cues"]) for s in steps], [1] * 5)
                self.assertTrue(all(s["media"] == {} for s in steps))
                self.assertIn("hypothesis-only", package.data["description"])
                self.assertEqual(package.source_model_path().read_bytes(), source.read_bytes())
            finally:
                package.close()

    def test_metadata_only_native_package_supports_real_timeline_without_snapshots(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "fusion.f3d"
            source.write_bytes(b"original parametric design")
            destination = Path(folder) / "native.excadmple"
            extract = dict(EXTRACT, meshes={})
            extract["features"] = [dict(feature, state=[]) for feature in EXTRACT["features"]]
            result, count = make_package(
                extract, source, destination, synthetic_reasoning=True,
                native_only=True)
            self.assertEqual(result, destination)
            self.assertEqual(count, len(EXTRACT["features"]))
            pkg = open_package(result)
            try:
                self.assertEqual(pkg.source_model_path().read_bytes(), source.read_bytes())
                self.assertEqual(len(pkg.data["steps"]), count)
                self.assertTrue(all("animation" not in s and not s["geometry"]["meshes"]
                                    for s in pkg.data["steps"]))
                self.assertEqual([s["source_features"][0]["index"] for s in pkg.data["steps"]],
                                 [0, 1, 2, 3, 4])
                self.assertTrue(all(len(s["cues"]) == 1 and s["media"] == {}
                                    for s in pkg.data["steps"]))
                self.assertEqual(pkg.data["steps"][1]["tools"], ["Extrude"])
            finally:
                pkg.close()

    def test_native_only_does_not_truncate_a_large_feature_history(self):
        source = Path("fusion.f3d")
        features = [dict(EXTRACT["features"][1], index=i, name="Extrude" + str(i), state=[])
                    for i in range(125)]
        extract = dict(EXTRACT, meshes={}, features=features)
        manifest = native_only_manifest(extract, source, "Large test", True)
        self.assertEqual(len(manifest["steps"]), 125)
        self.assertEqual(manifest["steps"][124]["source_features"][0]["index"], 124)
        self.assertEqual(len(manifest["steps"][124]["cues"]), 1)

    def test_source_file_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "fusion.f3d"
            source.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "Output must"):
                make_package(EXTRACT, source, source)
            self.assertEqual(source.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
