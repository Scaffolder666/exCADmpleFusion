"""Regression checks for reference geometry and time-aligned captions.

Run: python -m unittest discover -s tests -v
"""
import unittest
from pathlib import Path
from core.packages import open_package
from core.animation import reveal_meshes

ROOT = Path(__file__).resolve().parents[1]


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

    def test_reveal_preserves_context_and_reaches_target(self):
        package = open_package(ROOT / "examples" / "phone_stand.json")
        try:
            for step in package.data["steps"][1:]:
                anim = step["animation"]
                start = reveal_meshes(anim, 0)
                end = reveal_meshes(anim, 1)
                self.assertEqual(start[:len(anim["context_meshes"])], anim["context_meshes"])
                self.assertEqual(end, step["geometry"]["meshes"])
                self.assertNotEqual(start, end)
        finally:
            package.close()

    def test_all_demo_steps_have_timed_captions_and_reasoning(self):
        package = open_package(ROOT / "examples" / "phone_stand.json")
        try:
            for step in package.data["steps"]:
                cues = step.get("cues", [])
                self.assertTrue(cues, f"{step['id']} lacks captions")
                self.assertEqual(cues[0]["at_ms"], 0)
                self.assertEqual([c["at_ms"] for c in cues],
                                 sorted(c["at_ms"] for c in cues))
                self.assertTrue(step.get("reasoning", {}).get("text"))
        finally:
            package.close()


if __name__ == "__main__":
    unittest.main()
