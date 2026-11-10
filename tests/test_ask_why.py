""""Ask why": click the reference drawn in the user's viewport (stubbed Fusion).

Off by default: the reference graphics cannot be selected, so they never
get in the way of the user's modeling. On: the complete reference is shown
and its bodies can be clicked; the click point, moved back by the display
offset, finds the real face of the reference copy, and HiM's filter gives
the steps that made it. Whether Fusion reports the click point on Custom
Graphics (Selection.point) needs Fusion Desktop (docs/SAME_VIEWPORT_TEST.md).
"""
import types
import unittest

from tests import test_same_viewport as base
import adsk.core
import adsk.fusion


class Point:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class AskWhyTests(base.SameViewportBase):
    def setUp(self):
        super().setUp()
        self._point = adsk.core.Point3D
        adsk.core.Point3D = types.SimpleNamespace(create=Point)
        adsk.fusion.BRepEntityTypes = types.SimpleNamespace(BRepFaceEntityType="face", BRepEdgeEntityType="edge")
        self.face = base.Obj("BRepFace", "top", body=self.entities["body1"])
        self.queries = []

        def find(point, kind, tolerance, visible_only):
            self.queries.append(((point.x, point.y, point.z), kind))
            hit = kind == "face" and abs(point.x - 1.0) < tolerance
            return base.Coll([self.face] if hit else [])
        self.ref_design.rootComponent.findBRepUsingPoint = find

    def tearDown(self):
        adsk.core.Point3D = self._point
        del adsk.fusion.BRepEntityTypes
        super().tearDown()

    def drawn(self):
        return [e for g in self.live_user_groups() for e in g.entities]

    def test_off_by_default_nothing_can_be_clicked(self):
        self.assertFalse(self.session.ask_why)
        self.assertTrue(all(not e.isSelectable for e in self.drawn()))
        self.assertIsNone(self.session.why_at(Point(9.0, 0, 0)))
        self.assertEqual(self.queries, [])

    def test_on_shows_the_complete_model_and_its_bodies_can_be_clicked(self):
        self.session.frame(1, 0.5)                       # in the middle of playback
        self.session.set_ask_why(True)
        self.assertEqual(self.session.current, ("overview",))
        bodies = [e for e in self.drawn() if e.source[0] == "copy"]
        self.assertTrue(bodies and all(e.isSelectable for e in bodies))
        self.assertUserUntouched()
        self.session.set_ask_why(False)
        self.assertTrue(all(not e.isSelectable for e in self.drawn()))

    def test_click_finds_the_real_face_and_its_steps(self):
        # The HiM filter itself is tested in test_him_filter.py; here: it gets the real face.
        filtered = []
        self.session.filter = lambda entity: filtered.append(entity) or {"steps": [1]}
        self.session.set_ask_why(True)
        result = self.session.why_at(Point(9.0, 0.5, 0.25))   # drawn 8 cm to the right
        self.assertEqual(self.queries[0], ((1.0, 0.5, 0.25), "face"))
        self.assertEqual((filtered, result), ([self.face], {"steps": [1]}))
        self.assertTrue(self.session.owns(self.face))         # a face of the reference copy
        self.assertEqual(self.session.model.design.timeline.markerPosition,
                         self.session.model.end_state())
        self.assertUserUntouched()

    def test_click_beside_any_face(self):
        self.session.set_ask_why(True)
        self.assertIsNone(self.session.why_at(Point(30.0, 0, 0)))
        self.assertEqual([kind for _, kind in self.queries], ["face", "edge"])
        self.assertTrue(self.drawn())                    # the reference is still shown


if __name__ == "__main__":
    unittest.main()
