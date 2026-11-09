"""Fast HiM motion: moving the feature's real faces instead of recomputing.

Math and planners are pure Python. The playback tests use the stubbed
Fusion design; they check that frames do not write parameters (no
recompute), that pausing recomputes natively and resuming restores, and
that everything is cleaned up. Whether Fusion draws the moved face copies
correctly and how fast it is needs Fusion Desktop.
"""
import math
import types
import unittest

from tests import test_him_native as native             # installs the adsk stub
import adsk.fusion
from core.him_motion import interpolate
from core.playback import fast_motion as fm

Obj, Coll = native.Obj, native.Coll


def P(x, y, z):
    return types.SimpleNamespace(x=x, y=y, z=z)


def typed(name, **kw):
    return types.SimpleNamespace(objectType="adsk::fusion::" + name, **kw)


def close(a, b, places=9):
    return all(abs(x - y) < 10 ** -places for x, y in zip(a, b))


class MathTests(unittest.TestCase):
    def test_extrude_scale_keeps_the_profile_plane_and_moves_the_top(self):
        m = fm.scale_along((0, 0, 1), (0, 0, 1), 0.5)
        self.assertEqual(fm.apply(m, (3, 4, 1)), (3, 4, 1))          # on the profile plane
        self.assertEqual(fm.apply(m, (3, 4, 3)), (3, 4, 2))          # top halfway
        self.assertEqual(fm.apply(m, (3, 4, -1)), (3, 4, 0))         # symmetric side too

    def test_circular_instance_travels_on_its_arc(self):
        full = fm.rotation_about((0, 0, 1), (5, 0, 0), math.pi / 2)
        for t in (0.0, 0.25, 0.5, 1.0):
            p = fm.apply(fm.screw_partial(full, t), (6, 0, 0))
            self.assertAlmostEqual(math.dist(p, (5, 0, 0)), 1.0)       # radius kept
        self.assertTrue(close(fm.apply(fm.screw_partial(full, 1), (6, 0, 0)), (5, 1, 0)))
        self.assertTrue(close(fm.apply(fm.screw_partial(full, 0), (6, 0, 0)), (6, 0, 0)))

    def test_half_turn_and_translation(self):
        half = fm.rotation_about((0, 1, 0), (1, 0, 0), math.pi)
        mid = fm.apply(fm.screw_partial(half, 0.5), (2, 0, 0))
        self.assertAlmostEqual(math.dist(mid, (1, 0, 0)), 1.0)
        self.assertTrue(close(fm.apply(fm.screw_partial(half, 1), (2, 0, 0)), fm.apply(half, (2, 0, 0))))
        move = fm.identity()
        move[0][3] = 10
        self.assertEqual(fm.apply(fm.screw_partial(move, 0.3), (0, 0, 0)), (3.0, 0.0, 0.0))

    def test_mirror_folds_through_the_plane(self):
        plan = fm.plan_for("MirrorFeature", types.SimpleNamespace(faces=Coll(["f"])),
                           {"mirror": ((4, 0, 0), (1, 0, 0))})
        piece = plan.pieces[0]
        final = (6, 1, 0)
        self.assertTrue(close(fm.apply(piece.matrix(0), final), (2, 1, 0)))   # at the source
        self.assertTrue(close(fm.apply(piece.matrix(0.5), final), (4, 1, 0)))  # flat on the plane
        self.assertTrue(close(fm.apply(piece.matrix(1), final), final))
        self.assertEqual(plan.accuracy, fm.ILLUSTRATIVE)


def extrude(**kw):
    fields = dict(faces=Coll(["side", "top"]), operation=3,
                  startExtent=typed("ProfilePlaneStartDefinition"),
                  extentOne=typed("DistanceExtentDefinition"), extentTwo=None,
                  taperAngleOne=types.SimpleNamespace(value=0.0))
    fields.update(kw)
    return types.SimpleNamespace(**fields)


PLANE = {"plane": ((0, 0, 1), (0, 0, 1))}


class PlannerTests(unittest.TestCase):
    def test_new_body_extrude_is_exact_join_is_approximate(self):
        self.assertEqual(fm.plan_for("ExtrudeFeature", extrude(), PLANE).accuracy, fm.EXACT)
        self.assertEqual(fm.plan_for("ExtrudeFeature", extrude(operation=0), PLANE).accuracy, fm.APPROXIMATE)

    def test_extrudes_that_cannot_be_scaled_keep_native_recompute(self):
        for entity in (extrude(taperAngleOne=types.SimpleNamespace(value=0.1)),
                       extrude(extentOne=typed("ToEntityExtentDefinition")),
                       extrude(startExtent=typed("OffsetStartDefinition")),
                       extrude(faces=Coll())):
            self.assertIsNone(fm.plan_for("ExtrudeFeature", entity, PLANE))
        self.assertIsNone(fm.plan_for("ExtrudeFeature", extrude(), {}))       # profile not read
        self.assertIsNone(fm.plan_for("FilletFeature", extrude(), PLANE))      # fillet: always native

    def test_pattern_instances_skip_the_source(self):
        def element(dx, faces):
            cells = fm.identity()
            cells[0][3] = dx
            transform = types.SimpleNamespace(getCell=lambda r, c: cells[r][c])
            return types.SimpleNamespace(transform=transform, faces=Coll(faces))
        entity = types.SimpleNamespace(patternElements=Coll([element(0, ["src"]), element(5, ["a"]),
                                                              element(10, ["b"])]))
        plan = fm.plan_for("RectangularPatternFeature", entity, {})
        self.assertEqual([p.faces for p in plan.pieces], [["a"], ["b"]])
        # Instance b (final x = 10 + 1) starts on the source (x = 1).
        self.assertTrue(close(fm.apply(plan.pieces[1].matrix(0), (11, 0, 0)), (1, 0, 0)))
        self.assertTrue(close(fm.apply(plan.pieces[1].matrix(0.5), (11, 0, 0)), (6, 0, 0)))

    def test_revolve_needs_an_angle_and_axis(self):
        entity = types.SimpleNamespace(faces=Coll(["f"]), extentDefinition=typed(
            "AngleExtentDefinition", angle=types.SimpleNamespace(value=math.pi / 2)))
        plan = fm.plan_for("RevolveFeature", entity, {"axis": ((0, 0, 0), (0, 0, 1))})
        self.assertTrue(close(fm.apply(plan.pieces[0].matrix(1), (1, 0, 0)), (1, 0, 0)))
        self.assertTrue(close(fm.apply(plan.pieces[0].matrix(0), (0, 1, 0)), (1, 0, 0)))
        self.assertIsNone(fm.plan_for("RevolveFeature", entity, {}))


class FastPlaybackTests(unittest.TestCase):
    """Extrude1 of the stub design, with a real-looking profile plane."""

    def setUp(self):
        self.design, self.entities, self.groups = native.build()
        ex = self.entities["ex1"]
        ex.faces = Coll([Obj("BRepFace", "ex-side"), Obj("BRepFace", "ex-top")])
        ex.operation = 3
        ex.startExtent = typed("ProfilePlaneStartDefinition")
        ex.extentOne.objectType = "adsk::fusion::DistanceExtentDefinition"
        ex.profile = types.SimpleNamespace(plane=types.SimpleNamespace(origin=P(0, 0, 0), normal=P(0, 0, 1)))
        self.d1 = ex.extentOne.distance
        adsk.fusion.TemporaryBRepManager = types.SimpleNamespace(
            get=lambda: types.SimpleNamespace(copy=lambda face: ("copy", face.entityToken)))
        _, self.session = native.session_for(self.design, dim=True)
        him = self.session.him
        him.wireframe_context = True
        # The ghost context itself is covered elsewhere; here it only has to
        # hide the native result so the moved copies are what the user sees.
        him.capture_ghost_context = lambda: setattr(him, "pending_ghost",
                                                    {"curves": ["edge"], "body_tokens": frozenset()})

        def ghost(prepared, snapshot):
            prepared["wireframe"] = True
            return True
        him._start_ghost_context = ghost

    def tearDown(self):
        self.session.close()
        del adsk.fusion.TemporaryBRepManager

    def cells(self):
        entity = self.session.him.active["fast_entities"][0][1]
        return entity.transform.cells

    def test_frames_move_copies_and_never_recompute(self):
        shown = self.session.frame(0, 0.5)
        self.assertEqual((shown["motion"], shown["mode"]), ("exact", "parameter"))
        self.assertIn("same shape", shown["motion_note"])
        group = self.session.him.fast_group
        self.assertEqual(len(group.bodies), 2)                     # both faces copied once
        self.assertAlmostEqual(self.cells()[(2, 2)], interpolate(1.0, 0.5))
        for progress in (0.6, 0.7, 0.9):
            self.session.frame(0, progress)
        self.assertIs(self.session.him.fast_group, group)          # moved, not rebuilt
        self.assertAlmostEqual(self.cells()[(2, 2)], interpolate(1.0, 0.9))
        self.assertEqual(self.d1.writes, [])                        # no parameter change at all
        self.assertEqual(self.session._changing_tokens(), set())    # nothing to redraw per frame

    def test_pause_recomputes_natively_and_play_resumes_fast(self):
        self.session.frame(0, 0.4)
        group = self.session.him.fast_group
        shown = self.session.frame(0, 0.5, settle=True)              # paused
        self.assertEqual(shown["motion"], "settled")
        self.assertIn("Paused: Fusion's real recompute", shown["motion_note"])
        self.assertAlmostEqual(self.d1.value, interpolate(1.0, 0.5))  # Fusion's real shape
        self.assertFalse(group.isValid)
        shown = self.session.frame(0, 0.6)                            # play again
        self.assertEqual(shown["motion"], "exact")
        self.assertAlmostEqual(self.d1.value, 1.0)                    # restored, then moved again
        self.assertTrue(self.session.him.fast_group.isValid)
        self.session.stop()
        self.assertAlmostEqual(self.d1.value, 1.0)
        self.assertEqual(len(self.session.him.journal), 0)
        self.assertIsNone(self.session.him.fast_group)
        self.assertTrue(all(not g.isValid for g in self.groups))

    def test_step_change_and_end_clean_up(self):
        self.session.frame(0, 0.5)
        group = self.session.him.fast_group
        self.session.frame(1, 0.5)                                   # fillet: native as before
        self.assertFalse(group.isValid)
        self.assertAlmostEqual(native.param(self.entities, "fi1").value, interpolate(0.2, 0.5))
        self.session.frame(0, 1.0)                                    # step end
        self.assertAlmostEqual(native.param(self.entities, "fi1").value, 0.2)
        self.assertIsNone(self.session.him.fast_group)

    def test_without_hidden_native_result_it_stays_native(self):
        self.session.him._start_ghost_context = lambda prepared, snapshot: False
        shown = self.session.frame(0, 0.5)
        self.assertEqual(shown["motion"], "native")
        self.assertIn("ghost context unavailable", shown["motion_note"])
        self.assertAlmostEqual(self.d1.value, interpolate(1.0, 0.5))
        self.session.stop()
        self.assertAlmostEqual(self.d1.value, 1.0)

    def test_failed_face_copy_falls_back_to_native(self):
        adsk.fusion.TemporaryBRepManager = types.SimpleNamespace(
            get=lambda: types.SimpleNamespace(copy=lambda face: None))
        shown = self.session.frame(0, 0.5)
        self.assertEqual(shown["motion"], "native")
        self.assertIn("could not be copied", shown["motion_note"])
        self.assertAlmostEqual(self.d1.value, interpolate(1.0, 0.5))

    def test_each_feature_logs_which_motion_it_uses_and_why(self):
        logged = []
        self.session.him.log = logged.append
        self.session.frame(0, 0.5)
        self.assertIn("HiM motion Extrude1 (ExtrudeFeature): fast, exact", logged)
        self.entities["ex1"].taperAngleOne = types.SimpleNamespace(value=0.2)
        self.session.frame(1, 0.5)
        self.session.frame(0, 0.5)                                    # Extrude1 again, now tapered
        self.assertIn("HiM motion Extrude1 (ExtrudeFeature): Fusion recompute, the extrude has a taper angle",
                      logged)
        self.assertIn("taper angle", self.session.him.status()["motion_note"])


class RefusalReasonTests(unittest.TestCase):
    def test_reasons_are_reported(self):
        cases = [("ExtrudeFeature", extrude(), {}, "profile plane could not be read"),
                 ("ExtrudeFeature", extrude(extentOne=typed("ToEntityExtentDefinition")), PLANE,
                  "ToEntityExtentDefinition cannot be scaled"),
                 ("FilletFeature", extrude(), PLANE, "no fast motion for FilletFeature")]
        for kind, entity, inputs, expected in cases:
            reasons = []
            self.assertIsNone(fm.plan_for(kind, entity, inputs, reasons=reasons))
            self.assertIn(expected, reasons[0])


if __name__ == "__main__":
    unittest.main()
