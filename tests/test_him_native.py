"""Version A: HiM native-parameter playback on a stub Fusion design.

The stub stands in for Fusion's API (timeline, ModelParameters, bodies,
Custom Graphics). These tests check the add-in's own logic: which parameter
is driven for which feature, progress values, restoration after every kind
of interruption, timeline roll and restore, the visual fallback and its
clean-up, and that only the reference copy is ever touched. They do NOT
show that Fusion recomputes the geometry correctly: that needs Fusion
Desktop (see docs/FUSION_DESKTOP_TEST.md).
"""
import types
import unittest

from tests import test_him_fusion_adapter as stub        # installs the adsk stub
import adsk.core
import adsk.fusion
from core.him_fusion import FusionTimelineModel, _model_parameters
from core.him_motion import interpolate
from core.him_reference import ReferenceSession
from core.reference_plan import map_steps

Obj, Coll, Timeline, TimelineObj = stub.Obj, stub.Coll, stub.Timeline, stub.TimelineObj


class Matrix:
    def __init__(self):
        self.cells = {}

    def setCell(self, r, c, v):
        self.cells[(r, c)] = v


adsk.core.Matrix3D = types.SimpleNamespace(create=lambda: Matrix())
adsk.fusion.CustomGraphicsSolidColorEffect.create = staticmethod(lambda color: ("solid", color))
adsk.core.Point3D = types.SimpleNamespace(create=lambda x, y, z: types.SimpleNamespace(x=x, y=y, z=z))


class Param(stub.Param):
    """A ModelParameter; ``minimum`` makes Fusion-like rejections possible."""

    def __init__(self, name, value, owner, minimum=None):
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "writes", [])
        super().__init__(name, value, owner)
        object.__setattr__(self, "writes", [])

    def __setattr__(self, key, value):
        if key == "value" and self.minimum is not None and value < self.minimum:
            raise RuntimeError("value below the feature's minimum")
        if key in ("value", "expression"):
            self.writes.append((key, value))
        super().__setattr__(key, value)


class Group:
    def __init__(self, log):
        self.log, self.isValid, self.isSelectable = log, True, False
        self.curves, self.bodies = [], []
        log.append(self)

    def addCurve(self, curve):
        line = types.SimpleNamespace()
        self.curves.append(line)
        return line

    def addBRepBody(self, body):
        overlay = types.SimpleNamespace(opacity=None)
        overlay.setOpacity = lambda value, _: setattr(overlay, "opacity", value)
        self.bodies.append(overlay)
        return overlay

    def deleteMe(self):
        self.isValid = False


def box():
    p = types.SimpleNamespace(x=0, y=0, z=0)
    return types.SimpleNamespace(minPoint=p, maxPoint=types.SimpleNamespace(x=2, y=2, z=2))


def build(fillet_minimum=None):
    """Sketch1, Extrude1 (distance), Fillet1 (radius), Sketch2, Extrude2
    (to-object extent: no distance), Mirror1 (no parameters)."""
    body = Obj("BRepBody", "body1", opacity=1.0, boundingBox=box())
    mirrored = Obj("BRepBody", "body2", opacity=1.0, boundingBox=box())
    other = Obj("BRepBody", "body0", opacity=0.6, boundingBox=box())
    sketch1 = Obj("Sketch", "sk1", name="Sketch1", objectType="adsk::fusion::Sketch")
    sketch2 = Obj("Sketch", "sk2", name="Sketch2", objectType="adsk::fusion::Sketch")
    extrude1 = Obj("F", "ex1", name="Extrude1", objectType="adsk::fusion::ExtrudeFeature",
                   faces=Coll(), bodies=Coll([body]))
    extrude1.extentOne = types.SimpleNamespace(distance=Param("d1", 1.0, extrude1))
    fillet = Obj("F", "fi1", name="Fillet1", objectType="adsk::fusion::FilletFeature",
                 faces=Coll(), bodies=Coll([body]))
    fillet.edgeSets = Coll([types.SimpleNamespace(radius=Param("d2", 0.2, fillet, fillet_minimum))])
    extrude2 = Obj("F", "ex2", name="Extrude2", objectType="adsk::fusion::ExtrudeFeature",
                   faces=Coll(), bodies=Coll([body]))
    extrude2.extentOne = types.SimpleNamespace(toEntity=object())          # no distance parameter
    mirror = Obj("F", "mi1", name="Mirror1", objectType="adsk::fusion::MirrorFeature",
                 faces=Coll(), bodies=Coll([mirrored]))
    timeline = Timeline()
    for i, e in enumerate((sketch1, extrude1, fillet, sketch2, extrude2, mirror)):
        timeline.append(TimelineObj(timeline, i, e))
    timeline.moveToEnd()
    entities = {o.entityToken: o for o in (body, mirrored, other, sketch1, sketch2, extrude1,
                                           fillet, extrude2, mirror)}
    groups = []
    design = types.SimpleNamespace(
        _type="Design", designType=1, timeline=timeline,
        allParameters=Coll([extrude1.extentOne.distance, fillet.edgeSets[0].radius]),
        findEntityByToken=lambda t: [entities[t]] if t in entities else [],
        allComponents=Coll([types.SimpleNamespace(bRepBodies=Coll([other, body, mirrored]))]),
        rootComponent=types.SimpleNamespace(
            entityToken="root",
            customGraphicsGroups=types.SimpleNamespace(add=lambda: Group(groups))))
    return design, entities, groups


STEPS = [
    {"id": "base", "source_features": [{"name": "Sketch1", "index": 0, "kind": "Sketch"},
                                       {"name": "Extrude1", "index": 1, "kind": "ExtrudeFeature"}]},
    {"id": "round", "source_features": [{"name": "Fillet1", "index": 2, "kind": "FilletFeature"}]},
    {"id": "post", "source_features": [{"name": "Sketch2", "index": 3}, {"name": "Extrude2", "index": 4}]},
    {"id": "mirror", "source_features": [{"name": "Mirror1", "index": 5, "kind": "MirrorFeature"}]},
]


class FakeApp:
    def __init__(self, design):
        self.activeProduct = design
        self.activeDocument = None
        self.activeViewport = types.SimpleNamespace(refresh=lambda: None, fit=lambda: None)


def session_for(design, dim=False):
    app = FakeApp(design)
    session = ReferenceSession(app, None)
    session.him.dim_others = dim
    session.model = FusionTimelineModel(design)
    session.mapped, session.unmatched = map_steps(STEPS, session.model.features())
    session.plan = session.animation_plan()
    return app, session


def param(entities, token):
    entity = entities[token]
    if token == "fi1":
        return entity.edgeSets[0].radius
    return entity.extentOne.distance


class ParameterDiscoveryTests(unittest.TestCase):
    def test_registry_paths_only(self):
        design, entities, _ = build()
        self.assertEqual([p.name for p in _model_parameters(design, entities["ex1"], "ExtrudeFeature")], ["d1"])
        self.assertEqual([p.name for p in _model_parameters(design, entities["fi1"], "FilletFeature")], ["d2"])
        # A "to object" extent has no distance: nothing is animated, and no
        # unrelated length parameter of the design is picked up instead.
        self.assertEqual(_model_parameters(design, entities["ex2"], "ExtrudeFeature"), [])
        self.assertEqual(_model_parameters(design, entities["mi1"], "MirrorFeature"), [])

    def test_animation_plan_distinguishes_parameter_and_visual(self):
        design, _, _ = build()
        _, session = session_for(design)
        modes = [[(i["feature"], i["mode"], i["parameters"]) for i in step] for step in session.plan]
        self.assertEqual(modes, [
            [("Sketch1", "timeline", []), ("Extrude1", "parameter", ["d1"])],
            [("Fillet1", "parameter", ["d2"])],
            [("Sketch2", "timeline", []), ("Extrude2", "visual", [])],
            [("Mirror1", "visual", [])],
        ])


class NativePlaybackTests(unittest.TestCase):
    def setUp(self):
        self.design, self.entities, self.groups = build()
        self.app, self.session = session_for(self.design)
        self.d1, self.d2 = param(self.entities, "ex1"), param(self.entities, "fi1")
        self.originals = (self.d1.expression, self.d2.expression)

    def assertRestored(self):
        self.assertEqual((self.d1.expression, self.d2.expression), self.originals)
        self.assertAlmostEqual(self.d1.value, 1.0)
        self.assertAlmostEqual(self.d2.value, 0.2)
        self.assertEqual(len(self.session.him.journal), 0)
        self.assertTrue(all(not g.isValid for g in self.groups))

    def test_parameter_grows_with_progress_and_ends_at_its_value(self):
        for progress in (0.0, 0.25, 0.5, 0.99):
            shown = self.session.frame(0, progress)
            self.assertEqual(shown["mode"], "parameter")
            self.assertEqual(shown["parameters"], ["d1"])
            self.assertAlmostEqual(self.d1.value, interpolate(1.0, progress))
            self.assertEqual(self.design.timeline.markerPosition, 2)        # rolled to after Extrude1
        values = [v for k, v in self.d1.writes if k == "value"]
        self.assertEqual(values, sorted(values))                            # monotonic growth
        self.assertGreater(values[0], 0)                                    # never exactly zero
        shown = self.session.frame(0, 1.0)
        self.assertEqual(shown["mode"], "result")
        self.assertRestored()                                               # final geometry = original

    def test_restored_on_step_change_stop_close_and_show_result(self):
        self.session.frame(0, 0.4)
        self.session.frame(1, 0.4)                       # step change mid-animation
        self.assertAlmostEqual(self.d1.value, 1.0)
        self.assertEqual(self.d1.expression, self.originals[0])
        self.assertAlmostEqual(self.d2.value, interpolate(0.2, 0.4))
        self.session.stop()
        self.assertRestored()
        self.session.frame(1, 0.7)
        self.session.show_result(2)
        self.assertRestored()
        self.assertEqual(self.design.timeline.markerPosition, 5)            # after Extrude2
        self.session.frame(1, 0.7)
        self.session.close()
        self.assertRestored()

    def test_multiple_consecutive_operations_and_replay(self):
        seen = []
        for step in range(4):
            for progress in (0.0, 0.5, 0.9, 1.0):
                shown = self.session.frame(step, progress)
                seen.append((step, shown["mode"], shown.get("feature")))
        self.assertIn((0, "parameter", "Extrude1"), seen)
        self.assertIn((1, "parameter", "Fillet1"), seen)
        self.assertIn((2, "visual", "Extrude2"), seen)
        self.assertIn((3, "visual", "Mirror1"), seen)
        self.assertRestored()
        self.assertEqual(self.design.timeline.markerPosition, 6)            # finished model
        # Replay step 1 from the start after finishing it.
        self.session.frame(1, 0.0)
        self.assertAlmostEqual(self.d2.value, interpolate(0.2, 0.0))
        self.assertEqual(self.design.timeline.markerPosition, 3)
        self.session.frame(1, 1.0)
        self.assertRestored()

    def test_backward_playback_reverses_the_parameter(self):
        for progress in (0.9, 0.6, 0.3):
            self.session.frame(1, progress)
            self.assertAlmostEqual(self.d2.value, interpolate(0.2, progress))
        self.session.stop()
        self.assertRestored()

    def test_visual_fallback_draws_and_cleans_up(self):
        shown = self.session.frame(3, 0.5)
        self.assertEqual(shown["mode"], "visual")
        group = self.groups[-1]
        self.assertTrue(group.isValid)
        self.assertEqual(len(group.bodies), 1)
        self.assertAlmostEqual(group.bodies[0].opacity, 0.5)
        self.session.frame(3, 1.0)
        self.assertTrue(all(not g.isValid for g in self.groups))
        self.assertEqual(self.d1.writes, [])                                # model untouched

    def test_no_change_while_another_document_is_active(self):
        self.session.document = object()
        self.app.activeDocument = object()                                  # the user switched documents
        self.assertIsNone(self.session.frame(0, 0.5))
        self.assertEqual(self.d1.writes, [])
        self.app.activeDocument = self.session.document
        self.assertEqual(self.session.frame(0, 0.5)["mode"], "parameter")

    def test_animation_uses_the_reference_design_not_the_active_product(self):
        user_design, user_entities, user_groups = build()
        self.app.activeProduct = user_design                                # the other design
        self.session.frame(1, 0.5)
        self.assertAlmostEqual(self.d2.value, interpolate(0.2, 0.5))
        self.assertEqual(param(user_entities, "fi1").writes, [])
        self.assertEqual(user_groups, [])
        self.session.stop()
        self.assertRestored()


class FailureTests(unittest.TestCase):
    def test_rejected_parameter_falls_back_to_visual_and_restores(self):
        design, entities, groups = build(fillet_minimum=0.1)
        _, session = session_for(design)
        d2 = param(entities, "fi1")
        original = d2.expression
        shown = session.frame(1, 0.1)                                       # 0.2 * ~0.12 < 0.1
        self.assertEqual(shown["mode"], "visual")
        self.assertIn("rejected d2", shown["fallback"])
        self.assertEqual(d2.expression, original)
        self.assertAlmostEqual(d2.value, 0.2)
        self.assertTrue(groups[-1].bodies)                                  # the fade is drawn instead
        session.stop()
        self.assertTrue(all(not g.isValid for g in groups))
        self.assertEqual(len(session.him.journal), 0)

    def test_feature_error_state_falls_back(self):
        design, entities, _ = build()
        _, session = session_for(design)
        adsk.fusion.FeatureHealthStates = types.SimpleNamespace(ErrorFeatureHealthState="error")
        try:
            entities["ex1"].healthState = "error"
            shown = session.frame(0, 0.3)
        finally:
            del adsk.fusion.FeatureHealthStates
        self.assertEqual(shown["mode"], "visual")
        self.assertIn("failed to compute", shown["fallback"])
        self.assertAlmostEqual(param(entities, "ex1").value, 1.0)

    def test_unexpected_error_restores_and_reports(self):
        design, entities, groups = build()
        _, session = session_for(design)
        session.frame(1, 0.5)
        session.him._render = lambda frame: (_ for _ in ()).throw(RuntimeError("boom"))
        session.current = None
        shown = session.frame(1, 0.6)
        self.assertEqual(shown["mode"], "error")
        self.assertAlmostEqual(param(entities, "fi1").value, 0.2)
        self.assertEqual(len(session.him.journal), 0)
        self.assertTrue(all(not g.isValid for g in groups))

    def test_dimming_is_restored_including_result_bodies_of_visual_steps(self):
        design, entities, _ = build()
        _, session = session_for(design, dim=True)
        session.frame(3, 0.5)                                              # Mirror1: everything dimmed
        self.assertEqual(entities["body2"].opacity, 0.2)
        self.assertEqual(entities["body1"].opacity, 0.2)
        self.assertEqual(entities["body0"].opacity, 0.2)
        session.frame(1, 0.5)                                              # Fillet1: its body stays solid
        self.assertEqual(entities["body1"].opacity, 1.0)
        self.assertEqual(entities["body2"].opacity, 0.2)
        session.stop()
        self.assertEqual([entities[t].opacity for t in ("body0", "body1", "body2")], [0.6, 1.0, 1.0])


class TutorialDataTests(unittest.TestCase):
    """The reference playback adds nothing to, and removes nothing from,
    what the panel gets for audio, transcript and pointer."""

    def test_source_features_coexist_with_audio_transcript_and_pointer(self):
        import json
        import tempfile
        import zipfile
        from pathlib import Path
        from core.packages import open_package
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root / "examples" / "phone_stand.json").read_text())
        step = data["steps"][0]
        step["source_features"] = [{"index": 0, "name": "Sketch1", "kind": "Sketch"},
                                   {"index": 1, "name": "Extrude1", "kind": "ExtrudeFeature"}]
        step["media"] = {"audio": "media/session.wav", "offset_ms": 0}
        step["pointer"] = [{"at_ms": 100, "xyz": [0, 0, 0], "event": "click"}]
        data["source_model"] = "source/Design.f3d"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "t.excadmple"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("manifest.json", json.dumps(data))
                z.writestr("media/session.wav", b"RIFF")
                z.writestr("source/Design.f3d", b"f3d")
            package = open_package(path)
            try:
                player = package.player_data()["steps"][0]
                self.assertEqual(player["cues"], step["cues"])
                self.assertTrue(player["media"]["audio"])
                self.assertTrue(player["pointer_available"])
                self.assertEqual(player["source_features"], step["source_features"])
                self.assertTrue(package.source_model_path().is_file())
            finally:
                package.close()
        design, _, _ = build()
        mapped, missing = map_steps(data["steps"][:1], FusionTimelineModel(design).features())
        self.assertEqual([f.name for f in mapped[0]], ["Sketch1", "Extrude1"])
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
