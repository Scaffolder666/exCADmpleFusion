"""Authored operation previews remain deterministic and non-destructive."""
import unittest
from core.animation import (
    AnimationError, validate_animation, transition_meshes,
    rectangular_pattern_meshes,
)

A = {"vertices": [[0,0,0], [1,0,0], [0,1,0]], "triangles": [[0,1,2]]}
B = {"vertices": [[0,0,0], [2,0,0], [0,2,0]], "triangles": [[0,1,2]]}
C = {"vertices": [[0,0,0], [2,0,0], [0,2,0], [1,1,0]], "triangles": [[0,1,3],[0,3,2]]}


class TransitionTests(unittest.TestCase):
    def test_matching_topology_interpolates(self):
        for kind in ("fillet", "chamfer", "boolean", "split", "combine",
                     "loft", "shell", "thread", "import", "export"):
            anim = {"type": kind, "before_meshes": [A], "after_meshes": [B]}
            validate_animation(anim)
            self.assertEqual(transition_meshes(anim, .5)[0]["vertices"][1], [1.5, 0, 0])
            self.assertEqual(transition_meshes(anim, 1), [B])

    def test_topology_change_uses_snapshot_switch(self):
        anim = {"type": "boolean", "before_meshes": [A], "after_meshes": [C]}
        self.assertEqual(transition_meshes(anim, .25), [A])
        self.assertEqual(transition_meshes(anim, .75), [C])

    def test_rectangular_pattern(self):
        anim = {"type": "rectangular_pattern", "new_meshes": [A],
                "x_count": 3, "y_count": 2,
                "x_offset_cm": [2,0,0], "y_offset_cm": [0,3,0]}
        validate_animation(anim)
        self.assertEqual(len(rectangular_pattern_meshes(anim, 0)), 1)
        result = rectangular_pattern_meshes(anim, 1)
        self.assertEqual(len(result), 6)
        self.assertEqual(result[-1]["vertices"][0], [4,3,0])

    def test_invalid_mesh_and_progress(self):
        with self.assertRaises(AnimationError):
            validate_animation({"type": "fillet", "before_meshes": [A], "after_meshes": []})
        with self.assertRaises(AnimationError):
            transition_meshes({"type": "fillet", "before_meshes": [A], "after_meshes": [B]}, float("nan"))


if __name__ == "__main__":
    unittest.main()
