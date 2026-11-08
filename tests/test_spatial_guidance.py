"""Spatial guidance: which geometry a recorded step created or modified,
and the lifetime of its teal highlight in the (stubbed) Fusion viewport.

Geometry detection is pure Python and is tested on the bundled Phone Stand
snapshots. The renderer tests use a stub ``adsk``; they check which meshes
are drawn, their colour, selectability and clean-up, not what Fusion's
viewport actually shows."""
import json
import random
import types
import unittest
from pathlib import Path

from tests import test_him_fusion_adapter as stub        # installs the adsk stub
import adsk.core
import adsk.fusion
from core import step_changes
from core.packages import ExamplePackage
from core.step_changes import ChangeDetector, changed_geometry

ROOT = Path(__file__).resolve().parents[1]


def phone_stand():
    data = json.loads((ROOT / "examples" / "phone_stand.json").read_text())
    return ExamplePackage(data, ROOT / "examples").data["steps"]


def box(x0, y0, z0, x1, y1, z1):
    v = [[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    # 12 triangles, outward winding not needed for the comparison
    t = [[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
         [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]]
    return {"vertices": v, "triangles": t}


def bounds(meshes):
    pts = [p for m in meshes for p in m["vertices"]]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


def count(meshes):
    return sum(len(m["triangles"]) for m in meshes)


class PhoneStandDetectionTests(unittest.TestCase):
    def setUp(self):
        self.steps = phone_stand()

    def changes(self, index):
        previous = self.steps[index - 1]["geometry"]["meshes"] if index else []
        return changed_geometry(previous, self.steps[index]["geometry"]["meshes"])

    def test_step3_front_lip_only(self):
        self.assertEqual(self.steps[2]["title"], "Prevent the phone from sliding")
        changed = self.changes(2)
        lo, hi = bounds(changed)
        # The lip block: x 0.5..9.5, y 0.4..1.0, z 0.7..1.7 (on top of the base)
        for got, want in zip(lo + hi, [0.5, 0.4, 0.7, 9.5, 1.0, 1.7]):
            self.assertAlmostEqual(got, want, places=6)
        # 12 lip triangles minus the 2 bottom ones lying on the base's top face.
        self.assertEqual(count(changed), 10)
        total = count(self.steps[2]["geometry"]["meshes"])
        self.assertLess(count(changed), total / 3)

    def test_first_step_is_the_footprint(self):
        changed = self.changes(0)
        self.assertEqual(count(changed), 12)
        lo, hi = bounds(changed)
        self.assertEqual((lo[2], hi[2]), (0.0, 0.7))

    def test_back_support_is_the_raised_part(self):
        changed = self.changes(1)
        lo, hi = bounds(changed)
        # The support is a new body: all of it, and none of the base.
        support = self.steps[1]["geometry"]["meshes"][1]
        self.assertEqual(count(changed), 12)
        self.assertEqual(bounds(changed), bounds([support]))
        self.assertGreater(hi[2], 8.0)                    # the tall angled support
        base_lo, base_hi = bounds([self.steps[0]["geometry"]["meshes"][0]])
        self.assertGreater(lo[0], base_lo[0])             # narrower than the base footprint

    def test_every_step_is_local(self):
        for index, step in enumerate(self.steps):
            changed = self.changes(index)
            total = count(step["geometry"]["meshes"])
            self.assertTrue(changed, step["id"])
            if index:
                self.assertLessEqual(count(changed), total / 2, step["id"])

    def test_fillet_marks_rounded_edges_not_unchanged_faces(self):
        changed = self.changes(3)                         # Round the base edges
        before = self.steps[2]["geometry"]["meshes"]
        detector = ChangeDetector(before)
        for mesh in changed:                              # every changed triangle is off the old surface
            for a, b, c in step_changes._triangles(mesh):
                self.assertFalse(all(detector.index.near(p) for p in step_changes._samples(a, b, c)))
        same, _ = detector.split(self.steps[3]["geometry"]["meshes"])
        self.assertGreater(count(same), count(changed))   # the flat faces stay unhighlighted


class DetectionRobustnessTests(unittest.TestCase):
    def test_vertex_and_triangle_order_and_float_noise_are_not_changes(self):
        mesh = box(0, 0, 0, 4, 3, 1)
        rng = random.Random(4)
        order = list(range(8))
        rng.shuffle(order)
        where = {old: new for new, old in enumerate(order)}
        vertices = [None] * 8
        for old, new in where.items():
            vertices[new] = [c + rng.uniform(-1e-6, 1e-6) for c in mesh["vertices"][old]]
        triangles = [[where[i] for i in reversed(t)] for t in mesh["triangles"]]
        rng.shuffle(triangles)
        self.assertEqual(changed_geometry([mesh], [{"vertices": vertices, "triangles": triangles}]), [])

    def test_retriangulated_face_is_not_a_change(self):
        quad = {"vertices": [[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]], "triangles": [[0, 1, 2], [0, 2, 3]]}
        other = {"vertices": [[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0], [1, 1, 0]],
                 "triangles": [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]}
        self.assertEqual(changed_geometry([quad], [other]), [])

    def test_bump_on_a_modified_body_is_local(self):
        base = box(0, 0, 0, 10, 8, 1)
        bump = box(4, 3, 1, 6, 5, 2)
        merged = {"vertices": base["vertices"] + bump["vertices"],
                  "triangles": base["triangles"] + [[i + 8 for i in t] for t in bump["triangles"]]}
        changed = changed_geometry([base], [merged])
        lo, hi = bounds(changed)
        self.assertEqual((lo, hi), ([4, 3, 1], [6, 5, 2]))
        self.assertEqual(count(changed), 10)

    def test_moved_body_is_a_change_and_removal_is_not_invented(self):
        a, b = box(0, 0, 0, 1, 1, 1), box(5, 0, 0, 6, 1, 1)
        moved = box(5, 3, 0, 6, 4, 1)
        self.assertEqual(count(changed_geometry([a, b], [a, moved])), 12)
        self.assertEqual(changed_geometry([a, b], [a]), [])

    def test_too_large_to_compare_gives_no_guess(self):
        old = step_changes.MAX_EXAMINED
        step_changes.MAX_EXAMINED = 5
        try:
            self.assertIsNone(ChangeDetector([box(0, 0, 0, 1, 1, 1)]).changed([box(0, 0, 0, 2, 2, 2)]))
        finally:
            step_changes.MAX_EXAMINED = old


# --- renderer lifecycle on a stub Fusion -------------------------------------------------
class Entity:
    def __init__(self, coords, triangles):
        self.coords, self.triangles = coords, triangles
        self.color, self.isSelectable = None, True


class Group:
    def __init__(self, log):
        self.isValid, self.isVisible, self.isSelectable, self.isChildrenSelectable = True, True, True, True
        self.name, self.meshes = "", []
        log.append(self)

    def addMesh(self, coords, triangles, normals, normal_indices):
        entity = Entity(coords, triangles)
        self.meshes.append(entity)
        return entity

    def deleteMe(self):
        self.isValid = False


adsk.fusion.CustomGraphicsCoordinates = types.SimpleNamespace(create=lambda flat: list(flat))
adsk.fusion.CustomGraphicsBasicMaterialColorEffect = types.SimpleNamespace(
    create=lambda diffuse, *rest: ("teal", diffuse))
adsk.core.Color = types.SimpleNamespace(create=lambda *rgba: tuple(rgba))
from core.renderer import ReferenceRenderer, CHANGE_COLOR  # noqa: E402


def teal(group):
    return [m for m in group.meshes if m.color == ("teal", CHANGE_COLOR)]


class RendererLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.groups = []
        design = types.SimpleNamespace(_type="Design", rootComponent=types.SimpleNamespace(
            customGraphicsGroups=types.SimpleNamespace(add=lambda: Group(self.groups))))
        app = types.SimpleNamespace(activeProduct=design,
                                    activeViewport=types.SimpleNamespace(refresh=lambda: None))
        self.renderer = ReferenceRenderer(app)
        self.steps = phone_stand()

    def previous(self, index):
        return self.steps[index - 1]["geometry"]["meshes"] if index else []

    def test_step3_draws_lip_teal_and_rest_plain(self):
        self.renderer.render(self.steps[2], [0, 0, 0], self.previous(2))
        group = self.renderer.group
        lip = teal(group)
        self.assertEqual(len(lip), 1)
        self.assertEqual(len(lip[0].triangles) // 3, 10)
        plain = [m for m in group.meshes if m.color is None]
        self.assertEqual(sum(len(m.triangles) // 3 for m in plain), 36 - 10)   # everything else, unchanged
        self.assertTrue(all(not m.isSelectable for m in group.meshes))
        self.assertFalse(group.isSelectable)
        self.assertFalse(group.isChildrenSelectable)
        xs = lip[0].coords[0::3]
        self.assertEqual((min(xs), max(xs)), (0.5, 9.5))

    def test_switching_steps_replaces_the_highlight(self):
        self.renderer.render(self.steps[2], [0, 0, 0], self.previous(2))
        first = self.renderer.group
        self.renderer.render(self.steps[3], [0, 0, 0], self.previous(3))
        self.assertFalse(first.isValid)
        self.assertTrue(teal(self.renderer.group))
        self.assertEqual([g for g in self.groups if g.isValid], [self.renderer.group])

    def test_paused_animation_frame_keeps_its_highlight(self):
        self.renderer.render(self.steps[2], [0, 0, 0], self.previous(2))
        self.renderer.render_animation(self.steps[2], [0, 0, 0], 0.5, self.previous(2))
        frame = self.renderer.animation_group
        self.assertFalse(self.renderer.group.isVisible)
        lip = teal(frame)
        self.assertTrue(lip)
        zs = lip[0].coords[2::3]
        self.assertLess(max(zs), 1.7)                     # the lip is half grown
        self.assertGreater(max(zs), 0.7)
        # Nothing else is drawn while paused: the frame stays as it is.
        self.assertEqual([g for g in self.groups if g.isValid], [self.renderer.group, frame])
        self.renderer.finish_animation()
        self.assertFalse(frame.isValid)
        self.assertTrue(self.renderer.group.isVisible and teal(self.renderer.group))

    def test_replay_from_start_has_no_lip_yet(self):
        self.renderer.render_animation(self.steps[2], [0, 0, 0], 0.0, self.previous(2))
        self.assertEqual(teal(self.renderer.animation_group), [])

    def test_clear_and_hide_remove_highlights(self):
        self.renderer.render(self.steps[2], [0, 0, 0], self.previous(2))
        self.renderer.set_visible(False)
        self.assertFalse(self.renderer.group.isVisible)
        self.renderer.set_visible(True)
        self.assertTrue(self.renderer.group.isVisible)
        self.renderer.clear()                             # new example / close / stop
        self.assertTrue(all(not g.isValid for g in self.groups))

    def test_without_previous_snapshot_nothing_is_marked(self):
        self.renderer.render(self.steps[2], [0, 0, 0])
        self.assertEqual(teal(self.renderer.group), [])


if __name__ == "__main__":
    unittest.main()


class NativeGuidanceTests(unittest.TestCase):
    """Native .f3d playback: the feature's own faces (teal) and its input
    edges (blue) are marked, not the whole result body."""

    def setUp(self):
        from tests import test_him_native as native
        self.native = native
        self.design, self.entities, self.groups = native.build()
        fillet = self.entities["fi1"]
        self.fillet_face = stub.Obj("BRepFace", "fillet_face")
        fillet.faces = stub.Coll([self.fillet_face])
        fillet.edgeSets[0].edges = stub.Coll([stub.Obj("BRepEdge", "e1", geometry="edge-curve")])
        self.copies = []

        def copy(face):
            body = stub.Obj("BRepBody", "copy-" + face.entityToken)
            self.copies.append(body)
            return body
        adsk.fusion.TemporaryBRepManager = types.SimpleNamespace(
            get=lambda: types.SimpleNamespace(copy=copy))
        _, self.session = native.session_for(self.design)

    def tearDown(self):
        del adsk.fusion.TemporaryBRepManager

    def test_finished_step_marks_faces_and_inputs(self):
        self.session.show_result(1)                          # Fillet1 selected / finished
        group = self.session.him.group
        self.assertTrue(group.isValid)
        self.assertFalse(group.isSelectable)
        self.assertEqual(len(group.bodies), 1)               # the fillet face copy, not body1
        self.assertEqual(group.bodies[0].opacity, 0.6)
        self.assertEqual(len(group.curves), 1)               # its input edge, blue
        self.assertEqual(self.design.timeline.markerPosition, 3)
        self.session.stop()
        self.assertFalse(group.isValid)

    def test_guidance_follows_playback_and_step_changes(self):
        self.session.frame(1, 0.5)                           # animating: faces drawn per frame
        during = self.session.him.group
        self.assertEqual(len(during.bodies), 1)
        self.session.frame(1, 1.0)                           # paused at the end: still marked
        self.assertFalse(during.isValid)
        end = self.session.him.group
        self.assertTrue(end.isValid and end.bodies)
        self.session.frame(0, 0.2)                           # another step: old marks gone
        self.assertFalse(end.isValid)
        self.session.close()
        self.assertTrue(all(not g.isValid for g in self.groups))
        self.assertAlmostEqual(self.native.param(self.entities, "fi1").value, 0.2)

    def test_no_faces_reported_falls_back_to_result_body(self):
        self.entities["fi1"].faces = stub.Coll()
        self.session.show_result(1)
        self.assertEqual(self.session.him.group.bodies[0].opacity, 0.18)
