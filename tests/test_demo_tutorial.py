"""The validation tutorial (tools/demo_tutorial.py) assembles into a valid
package whose steps map onto the demo timeline. The Fusion half
(tools/fusion_demo) needs Fusion Desktop and is not run here."""
import tempfile
import unittest
from pathlib import Path

from core.authoring import build_manifest, write_package
from core.him_filter import FeatureInfo
from core.packages import open_package
from core.reference_plan import map_steps, animated
from tools.demo_tutorial import annotation_and_transcript

TIMELINE = [(0, "Sketch1", "Sketch"), (1, "Extrude1", "ExtrudeFeature"), (2, "Fillet1", "FilletFeature"),
            (3, "Sketch2", "Sketch"), (4, "Extrude2", "ExtrudeFeature"), (5, "Plane1", "ConstructionPlane"),
            (6, "Mirror1", "MirrorFeature")]
MESH = {"vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "triangles": [[0, 1, 2]]}


def fake_extract():
    meshes = {"m%d" % i: MESH for i in range(len(TIMELINE))}
    return {"format": "excadmple-extract", "version": 1, "source": {"file": "HiMValidation.f3d"},
            "meshes": meshes,
            "features": [{"index": i, "name": n, "kind": k, "suppressed": False, "parameters": [],
                          "inputs": {"sketches": [], "features": []}, "state": ["m%d" % i]}
                         for i, n, k in TIMELINE]}


class DemoTutorialTests(unittest.TestCase):
    def test_package_builds_and_maps_onto_the_timeline(self):
        annotation, segments = annotation_and_transcript(fake_extract())
        with tempfile.TemporaryDirectory() as temp:
            f3d = Path(temp) / "HiMValidation.f3d"
            f3d.write_bytes(b"f3d")
            manifest = build_manifest(fake_extract(), annotation, segments, source_model=str(f3d))
            out = write_package(manifest, Path(temp) / "him.excadmple", (), str(f3d))
            package = open_package(out)
            try:
                steps = package.data["steps"]
                self.assertEqual([s["id"] for s in steps], ["base", "round", "post", "mirror"])
                self.assertTrue(all(s["cues"] for s in steps))
                self.assertFalse(any(s.get("pointer") for s in steps))     # nothing fabricated
                self.assertTrue(package.source_model_path().is_file())
                mapped, missing = map_steps(steps, [FeatureInfo(*t) for t in TIMELINE])
            finally:
                package.close()
        self.assertEqual(missing, [])
        self.assertEqual([[f.name for f in animated(m)] for m in mapped],
                         [["Extrude1"], ["Fillet1"], ["Extrude2"], ["Mirror1"]])

    def test_unexpected_timeline_is_rejected(self):
        extract = fake_extract()
        extract["features"] = extract["features"][:3]
        with self.assertRaises(ValueError):
            annotation_and_transcript(extract)


if __name__ == "__main__":
    unittest.main()
