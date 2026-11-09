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

    def test_extrudes_that_cannot_be_scaled_fall_back_to_the_crossfade(self):
        for entity, why in ((extrude(taperAngleOne=types.SimpleNamespace(value=0.1)), "taper"),
                            (extrude(extentOne=typed("ToEntityExtentDefinition")), "cannot be scaled"),
                            (extrude(startExtent=typed("OffsetStartDefinition")), "profile plane")):
            plan = fm.plan_for("ExtrudeFeature", entity, PLANE)
            self.assertEqual(plan.accuracy, fm.ILLUSTRATIVE)
            self.assertEqual([p.role for p in plan.pieces], ["change"])        # its faces fade in
            self.assertIn(why, plan.note)
        self.assertIsNone(fm.plan_for("ExtrudeFeature", extrude(faces=Coll()), PLANE))   # nothing to show
        fillet = fm.plan_for("FilletFeature", extrude(), PLANE)
        self.assertEqual(fillet.label, "the result replaces what was there")

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

    def test_revolve_sweeps_its_profile_while_the_faces_appear(self):
        """A full revolve turned as a finished solid looked static; the
        profile sweeping about the axis shows the operation."""
        entity = types.SimpleNamespace(faces=Coll(["f"]), extentDefinition=typed(
            "AngleExtentDefinition", angle=types.SimpleNamespace(value=2 * math.pi)))
        plan = fm.plan_for("RevolveFeature", entity, {"axis": ((0, 0, 0), (0, 0, 1)),
                                                      "profile_curves": ["profile-line"]})
        profile, faces = plan.pieces
        self.assertEqual((profile.kind, profile.role, profile.faces), ("curve", "profile", ["profile-line"]))
        self.assertTrue(close(fm.apply(profile.matrix(0), (1, 0, 0)), (1, 0, 0)))          # starts at the profile
        self.assertTrue(close(fm.apply(profile.matrix(0.25), (1, 0, 0)), (0, 1, 0)))       # a quarter turn
        self.assertEqual((faces.role, faces.opacity(0), faces.opacity(0.5), faces.opacity(1)),
                         ("change", 0.0, 0.5, 1.0))
        self.assertEqual(fm.plan_for("RevolveFeature", entity, {}).label,          # no axis: crossfade
                         "the result replaces what was there")

    def test_partial_revolve_sweeps_towards_its_end_face(self):
        start = types.SimpleNamespace(centroid=P(1, 0, 0))
        end = types.SimpleNamespace(centroid=P(0, -1, 0))                    # -90 degrees about z
        entity = types.SimpleNamespace(faces=Coll(["f"]), startFaces=Coll([start]), endFaces=Coll([end]),
                                       extentDefinition=typed("AngleExtentDefinition",
                                                              angle=types.SimpleNamespace(value=math.pi / 2)))
        plan = fm.plan_for("RevolveFeature", entity, {"axis": ((0, 0, 0), (0, 0, 1)), "profile_curves": ["c"]})
        self.assertTrue(close(fm.apply(plan.pieces[0].matrix(1), (1, 0, 0)), (0, -1, 0)))

    def test_crossfade_for_combine_copy_paste_and_others(self):
        tool, target, result = (types.SimpleNamespace(entityToken=t) for t in ("tool", "target", "target"))
        entity = types.SimpleNamespace(bodies=Coll([result]), faces=Coll(["cut-face"]))
        inputs = {"before_bodies": {"tool": "tool-copy", "target": "target-copy", "other": "other-copy"},
                  "after_tokens": {"target", "other"}}
        plan = fm.plan_for("CombineFeature", entity, inputs)
        before, after, faces = plan.pieces
        # The target as it was and the consumed tool fade out; the untouched body is not part of it.
        self.assertEqual((before.role, sorted(before.faces)), ("before", ["target-copy", "tool-copy"]))
        self.assertEqual((before.opacity(0), before.opacity(1)), (1.0, 0.0))
        self.assertEqual((after.role, after.faces, after.opacity(1)), ("after", [result], 1.0))
        self.assertEqual((faces.role, faces.faces), ("change", ["cut-face"]))
        pasted = fm.plan_for("CopyPasteBody", types.SimpleNamespace(bodies=Coll([types.SimpleNamespace(
            entityToken="new")])), {"before_bodies": {"src": "src-copy"}, "after_tokens": {"src", "new"}})
        self.assertEqual([p.role for p in pasted.pieces], ["after"])        # the copy appears


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
        _, self.session = native.session_for(self.design, dim=True, fast=True)
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
        self.session.frame(1, 0.5)                                   # fillet: its own (crossfade) group
        self.assertFalse(group.isValid)
        self.assertIsNot(self.session.him.fast_group, group)
        self.assertEqual(native.param(self.entities, "fi1").writes, [])
        self.session.frame(0, 1.0)                                    # step end: final position
        self.assertAlmostEqual(native.param(self.entities, "fi1").value, 0.2)
        self.assertIsNotNone(self.session.him.fast_group)
        self.session.stop()
        self.assertIsNone(self.session.him.fast_group)

    def test_the_first_solid_uses_fast_motion_with_an_empty_context(self):
        """Extrude2 in the real model: nothing exists before it, so the
        ghost context is empty. That is valid, not a reason to fall back."""
        him = self.session.him
        del him._start_ghost_context                                  # the real method
        him.capture_ghost_context = lambda: setattr(him, "pending_ghost",
                                                    {"curves": (), "body_tokens": frozenset()})
        shown = self.session.frame(0, 0.5)
        self.assertEqual(shown["motion"], "exact")
        self.assertTrue(shown["wireframe"])
        self.assertEqual(self.d1.writes, [])

    def test_highlight_is_lit_and_outlined_and_the_outline_moves(self):
        made = []
        previous = getattr(adsk.fusion, "CustomGraphicsBasicMaterialColorEffect", None)
        adsk.fusion.CustomGraphicsBasicMaterialColorEffect = types.SimpleNamespace(
            create=lambda diffuse, *rest: made.append(diffuse) or ("lit", diffuse))
        edge = types.SimpleNamespace(geometry="edge-curve")
        adsk.fusion.TemporaryBRepManager = types.SimpleNamespace(get=lambda: types.SimpleNamespace(
            copy=lambda face: types.SimpleNamespace(entityToken=face.entityToken, edges=Coll([edge]))))
        try:
            self.session.frame(0, 0.5)
        finally:
            if previous is None:
                del adsk.fusion.CustomGraphicsBasicMaterialColorEffect
            else:
                adsk.fusion.CustomGraphicsBasicMaterialColorEffect = previous
        group = self.session.him.fast_group
        self.assertTrue(made)                                          # shaded material, not flat colour
        self.assertTrue(all(b.color[0] == "lit" for b in group.bodies))
        self.assertEqual(len(group.curves), 2)                         # one outline edge per face copy
        moved = [entity for _, entity in self.session.him.active["fast_entities"]]
        self.assertTrue(all(curve in moved for curve in group.curves))
        self.session.frame(0, 0.8)
        self.assertAlmostEqual(group.curves[0].transform.cells[(2, 2)], interpolate(1.0, 0.8))

    def test_fillet_crossfades_without_recompute(self):
        self.entities["fi1"].faces = Coll([Obj("BRepFace", "round-face")])
        shown = self.session.frame(1, 0.25)
        self.assertEqual(shown["motion"], "illustrative")
        radius = native.param(self.entities, "fi1")
        self.assertEqual(radius.writes, [])                            # no parameter change
        bodies = self.session.him.fast_group.bodies
        roles = [(piece.role, entity.opacity) for piece, entity in self.session.him.active["fast_entities"]]
        self.assertIn(("before", 0.75), roles)                         # body1 as it was, fading out
        self.assertIn(("after", 0.25), roles)                          # the filleted body, fading in
        self.assertIn(("change", 0.25), roles)                         # its new face, teal
        self.session.frame(1, 0.8)
        self.assertIn(("before", 0.2), [(p.role, round(e.opacity, 6))
                                        for p, e in self.session.him.active["fast_entities"]])
        self.session.stop()
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
        self.assertTrue(any(line.startswith("HiM motion Extrude1 (ExtrudeFeature): fast, illustrative (")
                            and "taper angle" in line for line in logged), logged)


class RefusalReasonTests(unittest.TestCase):
    def test_reasons_are_reported(self):
        empty = extrude(faces=Coll())
        cases = [("ExtrudeFeature", empty, {}, "profile plane could not be read"),
                 ("FilletFeature", empty, PLANE, "nothing to show before or after")]
        for kind, entity, inputs, expected in cases:
            reasons = []
            self.assertIsNone(fm.plan_for(kind, entity, inputs, reasons=reasons))
            self.assertIn(expected, reasons[0])


if __name__ == "__main__":
    unittest.main()


def matrix_obj(cells):
    return types.SimpleNamespace(getCell=lambda r, c: cells[r][c])


class MovePlannerTests(unittest.TestCase):
    def body(self, token="b"):
        return types.SimpleNamespace(objectType="adsk::fusion::BRepBody", entityToken=token)

    def plan(self, cells, targets=None, reasons=None):
        body = self.body()
        entity = types.SimpleNamespace(transform=matrix_obj(cells), inputEntities=Coll([body]))
        inputs = fm.capture_inputs("MoveFeature", entity) if targets is None else targets
        inputs = dict(inputs, resolve={"b": body}.get)
        return fm.plan_for("MoveFeature", entity, inputs, reasons=reasons)

    def test_translation_moves_from_the_old_place_to_the_new_one(self):
        cells = fm.identity()
        cells[0][3], cells[2][3] = 6.0, 2.0
        plan = self.plan(cells)
        piece = plan.pieces[0]
        self.assertEqual(plan.accuracy, fm.ILLUSTRATIVE)
        final = (7.0, 0.0, 2.0)                                   # was at (1, 0, 0)
        self.assertTrue(close(fm.apply(piece.matrix(0), final), (1, 0, 0)))
        self.assertTrue(close(fm.apply(piece.matrix(0.5), final), (4, 0, 1)))
        self.assertTrue(close(fm.apply(piece.matrix(1), final), final))

    def test_rotation_travels_on_the_arc(self):
        plan = self.plan(fm.rotation_about((0, 0, 1), (0, 0, 0), math.pi / 2))
        mid = fm.apply(plan.pieces[0].matrix(0.5), (0, 2, 0))       # final point; started at (2, 0, 0)
        self.assertAlmostEqual(math.dist(mid, (0, 0, 0)), 2.0)
        self.assertTrue(close(fm.apply(plan.pieces[0].matrix(0), (0, 2, 0)), (2, 0, 0)))

    def test_inputs_read_before_the_move_work_when_fusion_refuses_after_it(self):
        """Fusion: reading a Move's transform or inputEntities with the
        marker after the Move raises "Didn't roll editing feature back"."""
        cells = fm.identity()
        cells[0][3] = 5.0
        body = self.body()

        class Move:
            rolled_back = True
            objectType = "adsk::fusion::MoveFeature"

            def _guard(self):
                if not self.rolled_back:
                    raise RuntimeError("3 : Didn't roll editing feature back.")

            @property
            def transform(self):
                self._guard()
                return matrix_obj(cells)

            @property
            def inputEntities(self):
                self._guard()
                return Coll([body])
        move = Move()
        inputs = fm.capture_inputs("MoveFeature", move)          # marker before the Move
        move.rolled_back = False                                  # marker after it
        reasons = []
        plan = fm.plan_for("MoveFeature", move, dict(inputs, resolve={"b": body}.get), reasons=reasons)
        self.assertIsNotNone(plan, reasons)
        self.assertEqual(plan.pieces[0].faces, [body])
        # Without the early read, the refusal names the cause instead of crashing.
        reasons = []
        self.assertIsNone(fm.plan_for("MoveFeature", move, {}, reasons=reasons))
        self.assertIn("transform could not be read", reasons[0])

    def test_definition_transform_and_result_bodies_are_used_when_needed(self):
        cells = fm.identity()
        cells[1][3] = 3.0
        entity = types.SimpleNamespace(definition=types.SimpleNamespace(transform=matrix_obj(cells)),
                                       bodies=Coll(["body"]))
        self.assertEqual(fm.plan_for("MoveFeature", entity, {}).pieces[0].faces, ["body"])

    def test_refusals_are_explained(self):
        scaled = fm.identity()
        scaled[0][0] = 2.0
        occurrence = {"move_matrix": fm.identity(), "move_targets": [("Occurrence", "o")]}
        lost = {"move_matrix": fm.identity(), "move_targets": [("BRepBody", "gone")]}
        cases = [(types.SimpleNamespace(inputEntities=Coll([self.body()])), {}, "could not be read"),
                 (types.SimpleNamespace(transform=matrix_obj(scaled)), {}, "not a rigid motion"),
                 (types.SimpleNamespace(), occurrence, "Occurrence"),
                 (types.SimpleNamespace(), lost, "could not be found after the move")]
        for entity, inputs, expected in cases:
            reasons = []
            self.assertIsNone(fm.plan_for("MoveFeature", entity, inputs, reasons=reasons))
            self.assertIn(expected, reasons[0])


class MovePlaybackTests(unittest.TestCase):
    """Mirror1 of the stub design turned into a Move of body2."""

    def setUp(self):
        self.design, self.entities, self.groups = native.build()
        move = self.entities["mi1"]
        move.objectType = "adsk::fusion::MoveFeature"
        cells = fm.identity()
        cells[0][3] = 10.0
        move.transform = matrix_obj(cells)
        body = self.entities["body2"]
        body.objectType = "adsk::fusion::BRepBody"
        timeline = self.design.timeline

        class AfterMoveRefuses(Coll):
            """Like Fusion: readable only with the marker before the Move."""
            @property
            def count(inner):
                if timeline.markerPosition > 5:
                    raise RuntimeError("3 : Didn't roll editing feature back.")
                return len(inner)
        move.inputEntities = AfterMoveRefuses([body])
        move.bodies = Coll()                                      # no fallback: inputs must be read early
        self.copies = []
        adsk.fusion.TemporaryBRepManager = types.SimpleNamespace(
            get=lambda: types.SimpleNamespace(copy=lambda item: self.copies.append(item.entityToken)
                                              or ("copy", item.entityToken)))
        from core.him_fusion import FusionTimelineModel
        from core.him_reference import ReferenceSession
        from core.reference_plan import map_steps
        self.session = ReferenceSession(native.FakeApp(self.design), None)
        self.session.him.dim_others = True
        self.session.him.wireframe_context = True
        him = self.session.him
        him.capture_ghost_context = lambda: setattr(him, "pending_ghost",
                                                    {"curves": ["edge"], "body_tokens": frozenset()})

        def ghost(prepared, snapshot):
            prepared["wireframe"] = True
            return True
        him._start_ghost_context = ghost
        self.session.model = FusionTimelineModel(self.design)
        self.session.mapped, _ = map_steps([{"id": "move", "source_features": [{"name": "Mirror1", "index": 5}]}],
                                           self.session.model.features())

    def tearDown(self):
        self.session.close()
        del adsk.fusion.TemporaryBRepManager

    def test_an_arrow_shows_from_where_to_where(self):
        lines = []
        native.Group.addLines = lambda group, coords, indices, strip: lines.append(list(coords)) or \
            types.SimpleNamespace()
        coords = getattr(adsk.fusion, "CustomGraphicsCoordinates", None)
        adsk.fusion.CustomGraphicsCoordinates = types.SimpleNamespace(create=lambda flat: list(flat))
        try:
            self.session.frame(0, 0.3)
        finally:
            del native.Group.addLines
            if coords is None:
                del adsk.fusion.CustomGraphicsCoordinates
            else:
                adsk.fusion.CustomGraphicsCoordinates = coords
        self.assertEqual(len(lines), 1)
        start, tip = lines[0][0:3], lines[0][3:6]
        self.assertEqual([round(v, 6) for v in start], [-9.0, 1.0, 1.0])   # body2's centre before the move
        self.assertEqual([round(v, 6) for v in tip], [1.0, 1.0, 1.0])      # and after it (+10 cm in x)

    def test_the_moved_body_slides_into_place_without_recompute(self):
        logged = []
        self.session.him.log = logged.append
        shown = self.session.frame(0, 0.5)
        self.assertEqual(shown["motion"], "illustrative")
        self.assertEqual(self.copies, ["body2"])                    # the whole body, copied once
        transform = self.session.him.active["fast_entities"][0][1].transform.cells
        self.assertAlmostEqual(transform[(0, 3)], -5.0)             # halfway back from +10
        self.session.frame(0, 0.9)
        self.assertEqual(self.copies, ["body2"])
        self.assertAlmostEqual(self.session.him.active["fast_entities"][0][1].transform.cells[(0, 3)], -1.0)
        self.assertIn("HiM motion Mirror1 (MoveFeature): fast, illustrative", logged)
        self.session.frame(0, 1.0)
        self.assertIsNone(self.session.him.fast_group)


class RevolvePlaybackTests(unittest.TestCase):
    """Mirror1 of the stub design turned into a full revolve about z."""

    def setUp(self):
        self.design, self.entities, self.groups = native.build()
        rev = self.entities["mi1"]
        rev.objectType = "adsk::fusion::RevolveFeature"
        rev.axis = types.SimpleNamespace(geometry=types.SimpleNamespace(origin=P(0, 0, 0), direction=P(0, 0, 1)))
        rev.extentDefinition = typed("AngleExtentDefinition", angle=types.SimpleNamespace(value=2 * math.pi))
        rev.faces = Coll([Obj("BRepFace", "rev-face")])
        adsk.fusion.TemporaryBRepManager = types.SimpleNamespace(
            get=lambda: types.SimpleNamespace(copy=lambda item: ("copy", getattr(item, "entityToken", "?"))))
        from core.him_fusion import FusionTimelineModel
        from core.him_reference import ReferenceSession
        from core.reference_plan import map_steps
        self.session = ReferenceSession(native.FakeApp(self.design), None)
        him = self.session.him
        him.dim_others = him.wireframe_context = True
        him.capture_ghost_context = lambda: setattr(him, "pending_ghost",
                                                    {"curves": ["edge"], "body_tokens": frozenset()})

        def ghost(prepared, snapshot):
            prepared["wireframe"] = True
            return True
        him._start_ghost_context = ghost
        self.session.model = FusionTimelineModel(self.design)
        self.session.model.highlights[5] = ["profile-curve"]      # the input profile (blue)
        self.session.mapped, _ = map_steps([{"id": "rev", "source_features": [{"name": "Mirror1", "index": 5}]}],
                                           self.session.model.features())

    def tearDown(self):
        self.session.close()
        del adsk.fusion.TemporaryBRepManager

    def test_the_profile_turns_and_the_solid_appears(self):
        shown = self.session.frame(0, 0.25)
        self.assertEqual(shown["motion"], "illustrative")
        entities = self.session.him.active["fast_entities"]
        profile = [e for p, e in entities if p.role == "profile"][0]
        faces = [e for p, e in entities if p.role == "change"][0]
        self.assertAlmostEqual(profile.transform.cells[(0, 0)], 0.0)    # a quarter of the full turn
        self.assertAlmostEqual(profile.transform.cells[(1, 0)], 1.0)
        self.assertAlmostEqual(faces.opacity, 0.25)
        self.session.frame(0, 0.75)
        self.assertAlmostEqual(profile.transform.cells[(1, 0)], -1.0)   # three quarters
        self.assertAlmostEqual(faces.opacity, 0.75)
