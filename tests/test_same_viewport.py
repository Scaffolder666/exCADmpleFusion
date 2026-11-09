"""Same viewport, two independent histories (stubbed Fusion).

The reference .f3d copy keeps its own document and Timeline; the user's
Design stays active and editable; the reference is drawn into the user's
Design as Custom Graphics only. These tests check the add-in's logic:
which document is active, which Timeline/parameters are touched, where
graphics go and that they are cleaned up. Whether Fusion recomputes a
non-active document's parameters, and how the graphics look, needs Fusion
Desktop (docs/SAME_VIEWPORT_TEST.md).
"""
import types
import unittest
from pathlib import Path

from tests import test_him_native as native             # installs the adsk stub
import adsk.core
import adsk.fusion
from core.him_motion import interpolate
from core.him_reference import ReferenceSession

Obj, Coll, Timeline, TimelineObj = native.Obj, native.Coll, native.Timeline, native.TimelineObj


class Matrix:
    def __init__(self, cells=None):
        self.cells = dict(cells or {})

    def setCell(self, r, c, v):
        self.cells[(r, c)] = v

    def copy(self):
        return Matrix(self.cells)

    def transformBy(self, other):          # translations only in these tests
        for r in range(3):
            self.cells[(r, 3)] = self.cells.get((r, 3), 0) + other.cells.get((r, 3), 0)

    def translation(self):
        return tuple(self.cells.get((r, 3), 0) for r in range(3))


class Entity:
    def __init__(self, source):
        self.source, self.transform, self.opacity, self.color = source, None, 1.0, None
        self.isSelectable = True

    def setOpacity(self, value, _):
        self.opacity = value


class Group:
    def __init__(self, log):
        self.isValid, self.isSelectable, self.isChildrenSelectable = True, True, True
        self.entities = []
        log.append(self)

    @property
    def count(self):
        return len(self.entities)

    def item(self, i):
        return self.entities[i]

    def _add(self, source):
        entity = Entity(source)
        self.entities.append(entity)
        return entity

    addBRepBody = addCurve = _add

    def deleteMe(self):
        self.isValid = False


class Document:
    def __init__(self, app, design, name):
        self.app, self.design, self.name, self.isValid = app, design, name, True
        self.products = types.SimpleNamespace(itemByProductType=lambda _: design)

    def activate(self):
        self.app.activeDocument, self.app.activeProduct = self, self.design

    def close(self, save):
        assert save is False, "the reference copy must never be saved"
        self.isValid = False


def user_design(groups):
    timeline = Timeline()
    for i, name in enumerate(("SketchA", "ExtrudeA")):
        feature = Obj("F", "user-" + name, name=name, objectType="adsk::fusion::Sketch")
        timeline.append(TimelineObj(timeline, i, feature))
    timeline.moveToEnd()
    owner = Obj("F", "user-ex")
    width = native.Param("userWidth", 3.0, owner)
    body = Obj("BRepBody", "user-body", isVisible=True, opacity=1.0,
               boundingBox=types.SimpleNamespace(minPoint=types.SimpleNamespace(x=0, y=0, z=0),
                                                 maxPoint=types.SimpleNamespace(x=3, y=2, z=1)))
    design = types.SimpleNamespace(
        _type="Design", designType=1, timeline=timeline, allParameters=Coll([width]),
        rootComponent=types.SimpleNamespace(
            entityToken="user-root", bRepBodies=Coll([body]), allOccurrences=Coll(), sketches=Coll(),
            customGraphicsGroups=types.SimpleNamespace(add=lambda: Group(groups))))
    return design, width, body


class FakeApp:
    def __init__(self):
        self.activeViewport = types.SimpleNamespace(refresh=lambda: None, fit=lambda: None)
        self.documents = types.SimpleNamespace(add=lambda kind: None)
        self.reference_document = None
        self.importManager = types.SimpleNamespace(
            createFusionArchiveImportOptions=lambda path: path,
            importToNewDocument=self._import)

    def _import(self, path):
        self.reference_document.activate()     # Fusion activates a new document
        return self.reference_document


class SameViewportBase(unittest.TestCase):
    def setUp(self):
        self._saved = {name: getattr(adsk.core, name, None) for name in ("Matrix3D",)}
        adsk.core.Matrix3D = types.SimpleNamespace(create=lambda: Matrix())
        adsk.fusion.TemporaryBRepManager = types.SimpleNamespace(
            get=lambda: types.SimpleNamespace(copy=lambda body: ("copy", body.entityToken)))
        adsk.fusion.CustomGraphicsAppearanceColorEffect = types.SimpleNamespace(create=lambda a: ("look", a))

        self.app = FakeApp()
        self.ref_design, self.entities, self.ref_groups = native.build()
        root = self.ref_design.rootComponent
        for token in ("body0", "body1", "body2"):
            body = self.entities[token]
            body.isVisible, body.appearance = True, None
            body.parentComponent = types.SimpleNamespace(parentDesign=self.ref_design)
        root.bRepBodies = Coll([self.entities[t] for t in ("body0", "body1", "body2")])
        root.allOccurrences, root.sketches = Coll(), Coll()
        self.user_groups = []
        self.user, self.user_width, self.user_body = user_design(self.user_groups)
        self.user_doc = Document(self.app, self.user, "MyDesign")
        self.ref_doc = Document(self.app, self.ref_design, "fusion (reference copy)")
        self.app.reference_document = self.ref_doc
        self.user_doc.activate()
        self.user_timeline = (self.user.timeline.count, self.user.timeline.markerPosition)

        self.session = ReferenceSession(self.app, None)
        self.session.him.dim_others = False
        self.session.him.wireframe_context = False
        package = types.SimpleNamespace(source_model_path=lambda: Path("fusion.f3d"),
                                        data={"steps": native.STEPS}, needs_populate=False)
        self.assertTrue(self.session.open(package))
        self.d1 = native.param(self.entities, "ex1")
        self.d2 = native.param(self.entities, "fi1")

    def tearDown(self):
        self.session.close()
        for name, value in self._saved.items():
            setattr(adsk.core, name, value)
        del adsk.fusion.TemporaryBRepManager
        del adsk.fusion.CustomGraphicsAppearanceColorEffect

    def live_user_groups(self):
        return [g for g in self.user_groups if g.isValid]

    def assertUserUntouched(self, timeline=None):
        self.assertIs(self.app.activeDocument, self.user_doc)
        self.assertEqual((self.user.timeline.count, self.user.timeline.markerPosition),
                         timeline or self.user_timeline)
        self.assertEqual(self.user_width.writes, [])
        self.assertEqual(self.ref_groups, [])                # nothing drawn in the reference copy



class SameViewportTests(SameViewportBase):
    def test_loading_keeps_the_users_design_active_and_history_separate(self):
        self.assertUserUntouched()
        self.assertIsNot(self.session.document, self.user_doc)
        self.assertIs(self.session.model.design, self.ref_design)
        drawn = [e for g in self.live_user_groups() for e in g.entities]
        self.assertEqual(sorted(e.source[1] for e in drawn), ["body0", "body1", "body2"])
        # Beside the user's model: user max x 3 + 5 cm gap - reference min x 0.
        self.assertTrue(all(e.transform.translation() == (8.0, 0, 0) for e in drawn))
        self.assertTrue(all(not e.isSelectable for e in drawn))
        self.assertTrue(all(not g.isSelectable for g in self.live_user_groups()))
        self.assertEqual([e.opacity for e in drawn if e.source[1] == "body0"], [0.6])

    def test_native_parameter_animation_runs_while_the_user_design_is_active(self):
        shown = self.session.frame(0, 0.5)
        self.assertEqual(shown["mode"], "parameter")
        self.assertAlmostEqual(self.d1.value, interpolate(1.0, 0.5))
        self.assertEqual(self.ref_design.timeline.markerPosition, 2)
        self.assertUserUntouched()
        overlay = self.session.him.group
        self.assertIn(overlay, self.user_groups)              # HiM highlight shown to the user
        self.assertTrue(all(e.transform.translation() == (8.0, 0, 0) for e in overlay.entities))

    def test_pause_model_resume_scrub(self):
        self.session.frame(0, 0.4)
        # Paused: the user models in their own design (two new features).
        for i, name in ((2, "SketchB"), (3, "ExtrudeB")):
            self.user.timeline.append(TimelineObj(self.user.timeline, i, Obj("F", name, name=name)))
        self.user.timeline.moveToEnd()
        after_modeling = (self.user.timeline.count, self.user.timeline.markerPosition)
        self.assertEqual(after_modeling, (4, 4))
        # Resume from the paused position, then scrub back and forward.
        for step, progress in ((0, 0.5), (0, 0.9), (1, 0.3), (0, 0.2), (1, 0.8), (3, 0.5), (1, 1.0)):
            shown = self.session.frame(step, progress)
            self.assertNotEqual(shown["mode"], "error", shown)
            self.assertUserUntouched(after_modeling)
        self.assertAlmostEqual(self.d2.value, 0.2)            # step 2 finished: real value
        self.assertEqual(self.ref_design.timeline.markerPosition, 3)

    def test_static_bodies_are_drawn_once_per_feature_dynamic_ones_every_frame(self):
        self.session.frame(1, 0.1)
        before = len(self.user_groups)
        for progress in (0.2, 0.3, 0.4):
            self.session.frame(1, progress)
        new = self.user_groups[before:]
        reference_copies = [g for g in new if g.entities and all(
            isinstance(e.source, tuple) and e.source[0] == "copy" for e in g.entities)]
        # Fillet1 recomputes body1 only: one dynamic group per frame.
        self.assertEqual(len(reference_copies), 3)
        self.assertTrue(all([e.source[1] for e in g.entities] == ["body1"] for g in reference_copies))

    def test_selecting_the_users_own_geometry_never_filters(self):
        user_face = Obj("BRepFace", "user-face", body=self.user_body)
        self.user_body.parentComponent = types.SimpleNamespace(parentDesign=self.user)
        self.session.frame(1, 0.5)
        self.assertIsNone(self.session.filter(user_face))
        self.assertAlmostEqual(self.d2.value, interpolate(0.2, 0.5))   # playback not interrupted
        reference_face = Obj("BRepFace", "ref-face", body=self.entities["body1"])
        self.assertTrue(self.session.owns(reference_face))
        self.assertFalse(self.session.owns(user_face))

    def test_save_hides_reference_graphics_and_close_removes_everything(self):
        self.session.frame(0, 0.5)
        self.session.stop()                                   # BeforeSave
        self.session.hide()
        self.assertEqual(self.live_user_groups(), [])
        self.assertAlmostEqual(self.d1.value, 1.0)            # reference parameters restored
        self.session.show_overview()                          # AfterSave redraws
        self.assertTrue(self.live_user_groups())
        self.session.frame(0, 0.6)
        self.session.close()
        self.assertEqual(self.live_user_groups(), [])
        self.assertFalse(self.ref_doc.isValid)                # the copy is closed, unsaved
        self.assertTrue(self.user_doc.isValid)
        self.assertUserUntouched()
        self.assertAlmostEqual(self.d1.value, 1.0)

    def test_closing_the_users_design_stops_cleanly(self):
        self.session.frame(0, 0.3)
        self.user_doc.isValid = False
        shown = self.session.frame(1, 0.3)
        self.assertEqual(shown["mode"], "error")
        self.assertIn("Your design was closed", shown["fallback"])
        self.assertAlmostEqual(self.d1.value, 1.0)
        self.assertEqual(len(self.session.him.journal), 0)



class Line:
    _type = "Line3D"

    def __init__(self, a, b):
        self.startPoint, self.endPoint = a, b


def point(x, y, z=0.0):
    return types.SimpleNamespace(x=x, y=y, z=z)


class SketchDrawingTests(SameViewportBase):
    """A sketch-only step draws the sketch's real curves line by line."""

    def setUp(self):
        super().setUp()
        adsk.core.Line3D = types.SimpleNamespace(
            cast=lambda g: g if getattr(g, "_type", None) == "Line3D" else None,
            create=lambda a, b: Line(a, b))
        self.arc = types.SimpleNamespace(kind="arc")
        lines = [Line(point(0, 0), point(4, 0)), Line(point(4, 0), point(4, 3)), self.arc,
                 Line(point(0, 3), point(0, 0))]
        self.sketch = self.entities["sk1"]
        self.sketch.sketchCurves = Coll([types.SimpleNamespace(worldGeometry=g) for g in lines])
        self.sketch.isLightBulbOn = True
        self.sketch.isVisible = True
        from core.reference_plan import map_steps
        self.session.mapped, _ = map_steps(
            [{"id": "sketch", "source_features": [{"name": "Sketch1", "index": 0}]},
             {"id": "extrude", "source_features": [{"name": "Extrude1", "index": 1}]}],
            self.session.model.features())

    def tearDown(self):
        del adsk.core.Line3D
        super().tearDown()

    def drawn(self):
        return [e.source for e in self.session.him.group.entities]

    def test_lines_appear_in_order_and_the_current_one_grows(self):
        shown = self.session.frame(0, 0.125)               # half of the first of 4 curves
        self.assertTrue(shown["drawing"])
        self.assertEqual(self.ref_design.timeline.markerPosition, 1)   # after Sketch1
        first = self.drawn()
        self.assertEqual(len(first), 1)
        self.assertEqual((first[0].endPoint.x, first[0].endPoint.y), (2.0, 0.0))
        self.assertFalse(self.sketch.isLightBulbOn)        # native sketch hidden while drawing
        self.session.frame(0, 0.6)                          # 2 whole lines, the arc not reached
        self.assertEqual(len(self.drawn()), 2)
        self.session.frame(0, 0.8)                          # the arc appears whole, never approximated
        self.assertIs(self.drawn()[2], self.arc)
        self.assertTrue(all(e.transform.translation() == (8.0, 0, 0)
                            for e in self.session.him.group.entities))
        self.assertUserUntouched()

    def test_finished_or_paused_sketch_stays_outlined_and_visibility_is_restored(self):
        self.session.frame(0, 0.5)
        self.session.frame(0, 1.0)                          # step end: whole sketch outlined in blue
        self.assertEqual(len(self.drawn()), 4)
        self.session.frame(0, 0.3)                           # replay
        self.assertFalse(self.sketch.isLightBulbOn)
        self.session.frame(1, 0.5)                           # next step
        self.assertTrue(self.sketch.isLightBulbOn)
        self.session.frame(0, 0.3)
        self.session.close()
        self.assertTrue(self.sketch.isLightBulbOn)
        self.assertEqual(self.live_user_groups(), [])


if __name__ == "__main__":
    unittest.main()
