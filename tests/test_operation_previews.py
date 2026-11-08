"""Pure-Python operation preview contract; run: python -m unittest discover -s tests."""
import math
import unittest
from core.animation import operation_meshes, validate_animation, AnimationError

MESH = {"vertices": [[1,0,0],[2,0,0],[1,1,0]], "triangles": [[0,1,2]]}
AXIS = {"axis_origin_cm":[0,0,0], "axis_direction":[0,0,1]}

class OperationPreviewTests(unittest.TestCase):
    def test_revolve_rotates_mesh(self):
        a = dict(type="revolve", new_meshes=[MESH], angle_deg=90, **AXIS)
        self.assertEqual(operation_meshes(a, 0)[0]["vertices"][0], [1,0,0])
        x,y,z = operation_meshes(a, 1)[0]["vertices"][0]
        self.assertAlmostEqual(x, 0, places=6)
        self.assertAlmostEqual(y, 1, places=6)
    def test_pattern_adds_instances(self):
        a = dict(type="pattern", new_meshes=[MESH], count=4, **AXIS)
        self.assertEqual(len(operation_meshes(a, 0)), 1)
        self.assertEqual(len(operation_meshes(a, 1)), 4)
    def test_mirror_reverses_winding(self):
        a = dict(type="mirror", new_meshes=[MESH], plane_origin_cm=[0,0,0], plane_normal=[1,0,0])
        result = operation_meshes(a, 1)
        self.assertEqual(result[1]["vertices"][0], [-1,0,0])
        self.assertEqual(result[1]["triangles"], [[0,2,1]])
    def test_transform(self):
        a = dict(type="transform", new_meshes=[MESH], translation_cm=[0,0,2])
        self.assertEqual(operation_meshes(a, .5)[0]["vertices"][0], [1,0,1])
    def test_reject_bad_axis(self):
        with self.assertRaises(AnimationError):
            validate_animation(dict(type="revolve", new_meshes=[MESH], axis_origin_cm=[0,0,0], axis_direction=[0,0,0]))

if __name__ == "__main__":
    unittest.main()
