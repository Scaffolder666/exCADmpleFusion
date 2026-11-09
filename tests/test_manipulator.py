"""Fusion-style manipulators: only the moving face is highlighted, with an
arrow and the current value. Geometry is pure Python; playback uses the
stubbed Fusion design (not Fusion's real viewport)."""
import math
import types
import unittest

from tests import test_him_native as native             # installs the adsk stub
from tests import test_fast_motion as fast
import adsk.core
import adsk.fusion
from core.him_motion import interpolate
from core.playback import manipulator as mp

Obj, Coll = native.Obj, native.Coll
TEAL, NEUTRAL, ORANGE = (20, 184, 166, 255), (196, 202, 210, 255), (235, 109, 35, 255)


def face(token, x, y, z):
    return Obj("BRepFace", token, centroid=fast.P(x, y, z))


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.top, self.bottom, self.side = face("top", 0, 0, 2), face("bottom", 0, 0, 0), face("side", 1, 0, 1)
        self.plane = {"plane": ((0, 0, 0), (0, 0, 1))}

    def extrude(self, **kw):
        fields = dict(endFaces=Coll([self.top]), startFaces=Coll([self.bottom]), extentTwo=None,
                      extentOne=types.SimpleNamespace(objectType="adsk::fusion::DistanceExtentDefinition",
                                                      distance="d1"))
        fields.update(kw)
        return types.SimpleNamespace(**fields)

    def test_one_sided_extrude_moves_only_its_end_face(self):
        entity = self.extrude()
        self.assertEqual(mp.moving_faces("ExtrudeFeature", entity), {"top"})
        handles = mp.handles("ExtrudeFeature", entity, self.plane)
        self.assertEqual([(h["anchor"], h["direction"], h["parameter"]) for h in handles],
                         [((0, 0, 2), (0, 0, 1), "d1")])

    def test_two_sided_extrude_moves_both_ends_with_their_own_distances(self):
        bottom = face("bottom", 0, 0, -3)
        entity = self.extrude(startFaces=Coll([bottom]),
                              extentTwo=types.SimpleNamespace(distance="d2"))
        self.assertEqual(mp.moving_faces("ExtrudeFeature", entity), {"top", "bottom"})
        handles = mp.handles("ExtrudeFeature", entity, self.plane)
        self.assertEqual([(h["direction"], h["parameter"]) for h in handles],
                         [((0, 0, 1), "d1"), ((0, 0, -1), "d2")])

    def test_other_operations_have_no_moving_face(self):
        self.assertEqual(mp.moving_faces("FilletFeature", self.extrude()), set())
        self.assertEqual(mp.handles("FilletFeature", self.extrude(), self.plane), [])
        self.assertEqual(mp.handles("ExtrudeFeature", self.extrude(), {}), [])   # plane unknown

    def test_revolve_arrow_is_tangent_and_points_away_from_the_start(self):
        entity = types.SimpleNamespace(endFaces=Coll([face("end", 0, 2, 0)]),
                                       startFaces=Coll([face("start", 2, 0, 0)]),
                                       extentDefinition=types.SimpleNamespace(angle="a1"))
        handles = mp.handles("RevolveFeature", entity, {"axis": ((0, 0, 0), (0, 0, 1))})
        self.assertTrue(all(abs(a - b) < 1e-9 for a, b in zip(handles[0]["direction"], (-1, 0, 0))))
        self.assertEqual(handles[0]["parameter"], "a1")

    def test_arrow_shape(self):
        points, indices = mp.arrow_lines((0, 0, 2), (0, 0, 1), 1.0)
        self.assertEqual(points[1], (0, 0, 3))                       # tip above the face
        self.assertEqual(indices, [0, 1, 1, 2, 1, 3])
        self.assertTrue(all(p[2] < 3 for p in points[2:]))            # head below the tip


class NumberTests(unittest.TestCase):
    def test_labels_have_at_most_two_decimals(self):
        from core.playback.him_fusion import _short_number
        self.assertEqual([_short_number(v) for v in (6.1584118, 12.0, 0.5, -0.0001, 90.004)],
                         ["6.16", "12", "0.5", "0", "90"])


class Lines:
    def __init__(self, coords):
        self.coords, self.color, self.isSelectable = coords, None, True


class ManipulatorPlaybackTests(fast.FastPlaybackTests):
    """Extrude1 from the fast-motion fixture, with its end and start faces."""

    def setUp(self):
        self._color = adsk.core.Color
        adsk.core.Color = types.SimpleNamespace(create=lambda *rgba: tuple(rgba))
        self._coords = getattr(adsk.fusion, "CustomGraphicsCoordinates", None)
        adsk.fusion.CustomGraphicsCoordinates = types.SimpleNamespace(create=lambda flat: list(flat))
        native.Group.addLines = lambda group, coords, indices, strip: group.curves.append(Lines(coords)) \
            or group.curves[-1]
        super().setUp()
        ex = self.entities["ex1"]
        self.top, self.side = face("ex-top", 1, 1, 1), face("ex-side", 2, 1, 0.5)
        ex.faces = Coll([self.side, self.top])
        ex.endFaces, ex.startFaces = Coll([self.top]), Coll()

    def tearDown(self):
        super().tearDown()
        del native.Group.addLines
        adsk.core.Color = self._color
        if self._coords is None:
            del adsk.fusion.CustomGraphicsCoordinates
        else:
            adsk.fusion.CustomGraphicsCoordinates = self._coords

    def arrow_tip_z(self):
        lines = [c for c in self.session.him.handle_group.curves if isinstance(c, Lines)]
        return lines[0].coords[5]                                    # z of the tip point

    def test_fast_motion_highlights_only_the_top_and_moves_its_arrow(self):
        self.session.frame(0, 0.5)
        colors = [b.color[1] for b in self.session.him.fast_group.bodies]
        self.assertEqual(colors, [NEUTRAL, TEAL])                    # side plain, top highlighted
        low = self.arrow_tip_z()
        self.session.frame(0, 0.9)
        self.assertGreater(self.arrow_tip_z(), low)                  # the arrow rises with the face
        self.assertEqual(self.d1.writes, [])                          # still no recompute
        self.assertEqual(self.session.him._value_label(
            self.session.him.active["handles"][0], interpolate(1.0, 0.9)), "9.02 mm")
        self.session.stop()
        self.assertIsNone(self.session.him.handle_group)

    def test_paused_native_frame_has_the_same_highlight_and_arrow(self):
        self.session.frame(0, 0.4)
        self.session.frame(0, 0.5, settle=True)
        group = self.session.him.group
        colors = [b.color[1] for b in group.bodies]
        self.assertEqual(colors, [NEUTRAL, TEAL])
        self.assertTrue(any(isinstance(c, Lines) for c in group.curves))   # arrow in the overlay


if __name__ == "__main__":
    unittest.main()
