"""Run the Fusion adapter against a stub ``adsk`` module (no Fusion needed).

The stub models just enough API surface: timeline rollTo/moveToEnd,
findEntityByToken, feature.faces, typed inputs (profile, edgeSets) and
ModelParameters. It checks the adapter wiring, marker restore and parameter
restore, not Fusion's real geometry kernel.
"""
import sys
import types
import unittest


def _install_stub():
    if "adsk" in sys.modules and getattr(sys.modules["adsk"], "_him_stub", False):
        return
    adsk = types.ModuleType("adsk")
    adsk._him_stub = True
    core = types.ModuleType("adsk.core")
    fusion = types.ModuleType("adsk.fusion")

    def caster(name):
        class Cast:
            @staticmethod
            def cast(obj):
                return obj if getattr(obj, "_type", None) == name else None
        Cast.__name__ = name
        return Cast

    for name in ("BRepFace", "BRepEdge", "BRepVertex", "BRepBody", "Sketch", "Profile",
                 "ModelParameter", "TimelineGroup", "Design", "CustomGraphicsSolidColorEffect"):
        setattr(fusion, name, caster(name))
    fusion.DesignTypes = types.SimpleNamespace(ParametricDesignType=1)
    for name in ("Color", "Point3D", "Matrix3D"):
        setattr(core, name, types.SimpleNamespace(create=lambda *a: None))
    adsk.core, adsk.fusion = core, fusion
    sys.modules.update({"adsk": adsk, "adsk.core": core, "adsk.fusion": fusion})


_install_stub()
from core.playback import him_fusion  # noqa: E402
from core.playback.him_filter import extract_relevant_features  # noqa: E402


class Obj:
    def __init__(self, _type, token, **kw):
        self._type, self.entityToken = _type, token
        self.__dict__.update(kw)


class Coll(list):
    @property
    def count(self):
        return len(self)

    def item(self, i):
        return self[i]


class Param:
    _type = "ModelParameter"

    def __init__(self, name, value, owner):
        self.name, self.value, self.unit, self.createdBy = name, value, "mm", owner
        self.expression = "{} mm".format(value * 10)

    def __setattr__(self, key, value):
        object.__setattr__(self, key, value)
        if key == "expression" and value.endswith(" mm"):
            object.__setattr__(self, "value", float(value[:-3]) / 10)


class TimelineObj:
    isGroup = False

    def __init__(self, timeline, index, entity):
        self.timeline, self.index, self.entity = timeline, index, entity
        entity.timelineObject = self

    def rollTo(self, before):
        self.timeline.markerPosition = self.index if before else self.index + 1


class Timeline(Coll):
    markerPosition = 0

    def moveToEnd(self):
        self.markerPosition = len(self)


def build():
    top = Obj("BRepFace", "top")
    side = Obj("BRepFace", "side")
    fillet_face = Obj("BRepFace", "fillet_face")
    edge = Obj("BRepEdge", "edge", faces=Coll([top, side]), geometry="curve")
    for f in (top, side, fillet_face):
        f.edges, f.vertices, f.area = Coll([edge]), Coll(), 1.0
        f.centroid = types.SimpleNamespace(x=0, y=0, z=0)
    sketch = Obj("Sketch", "sk", name="Sketch1", objectType="adsk::fusion::Sketch", referencePlane=None)
    profile = Obj("Profile", "pr", parentSketch=sketch, profileLoops=Coll())
    extrude = Obj("Feature", "ex", name="Extrude1", objectType="adsk::fusion::ExtrudeFeature",
                  faces=Coll([top, side]), profile=profile, bodies=Coll())
    edge_set = types.SimpleNamespace(edges=Coll([edge]))
    fillet = Obj("Feature", "fi", name="Fillet1", objectType="adsk::fusion::FilletFeature",
                 faces=Coll([fillet_face]), edgeSets=Coll([edge_set]), bodies=Coll())
    edge_set.radius = Param("d3", 0.2, fillet)
    timeline = Timeline()
    for i, e in enumerate((sketch, extrude, fillet)):
        timeline.append(TimelineObj(timeline, i, e))
    timeline.moveToEnd()
    entities = {o.entityToken: o for o in (top, side, fillet_face, edge, sketch, extrude, fillet)}
    params = Coll([edge_set.radius])
    design = types.SimpleNamespace(designType=1, timeline=timeline, allParameters=params,
                                   findEntityByToken=lambda t: [entities[t]] if t in entities else [])
    return design, entities, edge_set.radius


class AdapterTests(unittest.TestCase):
    def test_filter_on_stub_design_and_marker_restored(self):
        design, entities, _ = build()
        model = him_fusion.FusionTimelineModel(design)
        result = extract_relevant_features(model, model.ref_of(entities["fillet_face"]),
                                           include_modifications=True)
        model.restore()
        self.assertEqual([f.name for f in result.features], ["Fillet1", "Extrude1"])
        self.assertEqual([b.sketch.name for b in result.bases], ["Sketch1"])
        self.assertTrue(result.bases[0].on_ground_plane)
        self.assertEqual(design.timeline.markerPosition, 3)
        self.assertEqual(model.highlights[2], ["curve"])

    def test_registry_parameter_path(self):
        design, entities, radius = build()
        params = him_fusion._model_parameters(design, entities["fi"], "adsk::fusion::FilletFeature")
        self.assertEqual(params, [radius])


if __name__ == "__main__":
    unittest.main()
