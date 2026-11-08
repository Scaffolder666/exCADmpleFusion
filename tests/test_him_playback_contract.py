"""Regression checks for reference geometry and time-aligned captions.

Run: python -m unittest discover -s tests -v
"""
import unittest
from pathlib import Path
from core.packages import open_package
from core.animation import animation_meshes

ROOT = Path(__file__).resolve().parents[1]


def _close(left, right, tol=1e-4):
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if a["triangles"] != b["triangles"] or len(a["vertices"]) != len(b["vertices"]):
            return False
        for p, q in zip(a["vertices"], b["vertices"]):
            if any(abs(x - y) > tol for x, y in zip(p, q)):
                return False
    return True


class HiMPlaybackContractTests(unittest.TestCase):
    def test_demo_has_distinct_cumulative_geometry_snapshots(self):
        package = open_package(ROOT / "examples" / "phone_stand.json")
        try:
            signatures = []
            for step in package.data["steps"]:
                meshes = step.get("geometry", {}).get("meshes", [])
                self.assertTrue(meshes, f"{step['id']} lacks step geometry")
                self.assertTrue(step.get('animation'))
                signatures.append(tuple((len(m["vertices"]), len(m["triangles"])) for m in meshes))
            self.assertEqual(len(set(signatures)), len(signatures),
                             "Each sample step should have a different geometry composition")
        finally:
            package.close()

    def test_every_animation_ends_at_the_step_geometry(self):
        for name in ("phone_stand.json", "tablet_stand.json"):
            package = open_package(ROOT / "examples" / name)
            try:
                for step in package.data["steps"]:
                    anim = step["animation"]
                    start = animation_meshes(anim, 0)
                    end = animation_meshes(anim, 1)
                    self.assertTrue(_close(end, step["geometry"]["meshes"]), step["id"])
                    self.assertNotEqual(start, end, step["id"])
            finally:
                package.close()

    def test_all_demo_steps_have_timed_words_and_tools(self):
        package = open_package(ROOT / "examples" / "phone_stand.json")
        try:
            for step in package.data["steps"]:
                cues = step.get("cues", [])
                self.assertTrue(cues, f"{step['id']} lacks captions")
                self.assertEqual(cues[0]["at_ms"], 0)
                self.assertEqual([c["at_ms"] for c in cues],
                                 sorted(c["at_ms"] for c in cues))
                self.assertTrue(step.get("tools"))
        finally:
            package.close()


if __name__ == "__main__":
    unittest.main()
