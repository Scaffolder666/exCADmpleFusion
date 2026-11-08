"""Regression tests for the real-.f3d HiM validation packaging workflow.

These check exact timeline mapping and embedded source bytes. They cannot
verify Fusion Desktop's parametric recomputation or any specific user model.
"""
import tempfile
import unittest
from pathlib import Path

from core.packages import open_package
from tests.test_authoring import EXTRACT
from tools.build_native_validation import make_annotation, make_package


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

    def test_source_file_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "fusion.f3d"
            source.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "Output must"):
                make_package(EXTRACT, source, source)
            self.assertEqual(source.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
