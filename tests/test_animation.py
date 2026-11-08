"""Non-destructive Extrude geometry generation and validation tests."""
import math
import unittest

from core.animation import AnimationError, extrude_mesh, validate_animation
from core.packages import PackageError, open_package
from pathlib import Path
import json
import tempfile


class AnimationTests(unittest.TestCase):
    def setUp(self):
        self.extrude = {
            "type": "extrude",
            "profile": [[0,0,0], [3,0,0], [3,2,0], [0,2,0]],
            "direction_cm": [0,0,5],
            "cap_triangles": [[0,1,2], [0,2,3]],
        }

    def test_full_distance_and_topology_are_preserved(self):
        middle = extrude_mesh(self.extrude, 0.5)
        end = extrude_mesh(self.extrude, 1.0)
        self.assertEqual(len(end["vertices"]), 8)
        self.assertEqual(len(end["triangles"]), 12)
        self.assertEqual(middle["vertices"][4], [0,0,2.5])
        self.assertEqual(end["vertices"][4], [0,0,5])
        self.assertEqual(middle["triangles"], end["triangles"])

    def test_profile_is_not_modified_by_animation(self):
        initial = json.dumps(self.extrude)
        extrude_mesh(self.extrude, 0)
        extrude_mesh(self.extrude, 1)
        self.assertEqual(json.dumps(self.extrude), initial)

    def test_zero_is_non_degenerate_for_fusion_graphics(self):
        mesh = extrude_mesh(self.extrude, 0)
        self.assertGreater(mesh["vertices"][4][2], 0)

    def test_progress_clamped(self):
        self.assertEqual(extrude_mesh(self.extrude, -3), extrude_mesh(self.extrude, 0))
        self.assertEqual(extrude_mesh(self.extrude, 10), extrude_mesh(self.extrude, 1))

    def test_invalid_parameters_rejected(self):
        for value in (None, float("nan"), True):
            with self.assertRaises(AnimationError):
                extrude_mesh(self.extrude, value)
        broken = dict(self.extrude, direction_cm=[0,0,0])
        with self.assertRaises(AnimationError):
            validate_animation(broken)
        broken = dict(self.extrude, type="fillet")
        with self.assertRaises(AnimationError):
            validate_animation(broken)

    def test_manifest_exposes_capability_not_geometry(self):
        source = Path(__file__).resolve().parents[1] / "examples" / "phone_stand.json"
        pkg = open_package(source)
        meta = pkg.player_data()["steps"]
        self.assertTrue(meta[0]["animation_available"])
        self.assertTrue(meta[1]["animation_available"])
        self.assertTrue(meta[2]["animation_available"])
        self.assertEqual(pkg.step(1)["animation"]["type"], "revolve")
        self.assertEqual(pkg.step(3)["animation"]["type"], "fillet")
        self.assertNotIn("animation", meta[0])
        self.assertEqual(pkg.step(0)["animation"]["type"], "extrude")
        pkg.close()

    def test_invalid_animation_package_rejected(self):
        source = Path(__file__).resolve().parents[1] / "examples" / "phone_stand.json"
        data = json.loads(source.read_text())
        data["steps"][0]["animation"]["cap_triangles"] = [[0,99,2]]
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / "broken.json"
            file.write_text(json.dumps(data))
            with self.assertRaises(PackageError):
                open_package(file)


if __name__ == "__main__":
    unittest.main()
