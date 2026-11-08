"""Extraction from a stub Fusion design: per-item states, parameters, inputs,
marker restored, and the result feeds the package builder."""
import sys
import types
import unittest

from tests import test_him_fusion_adapter as stub          # installs the adsk stub
from core import extract_fusion
from core.authoring import build_manifest

sys.modules["adsk.fusion"].TriangleMeshQualityOptions = types.SimpleNamespace(LowQualityTriangleMesh=0)


class Body:
    def __init__(self, z):
        self.isVisible = True
        height = z if callable(z) else (lambda: z)
        mesh = lambda: types.SimpleNamespace(
            nodeCoordinatesAsDouble=[0, 0, height(), 1, 0, height(), 0, 1, height()], nodeIndices=[0, 1, 2])
        calc = types.SimpleNamespace(setQuality=lambda q: None, calculate=mesh)
        self.meshManager = types.SimpleNamespace(createMeshCalculator=lambda: calc)


class ExtractTests(unittest.TestCase):
    def test_extract_states_and_build(self):
        design, entities, radius = stub.build()
        timeline = design.timeline
        base, rounded = Body(0.0), Body(lambda: radius.value)   # the fillet's shape follows its radius

        def bodies():
            marker = timeline.markerPosition
            return stub.Coll([] if marker < 2 else [base] if marker < 3 else [rounded])
        root = type("Root", (), {"bRepBodies": property(lambda self: bodies()),
                                 "allOccurrences": stub.Coll()})()
        design.rootComponent = root
        timeline.markerPosition = 3
        data = extract_fusion.extract(design, "Stand.f3d")
        self.assertEqual(timeline.markerPosition, 3)                 # restored
        names = [f["name"] for f in data["features"]]
        self.assertEqual(names, ["Sketch1", "Extrude1", "Fillet1"])
        states = [f["state"] for f in data["features"]]
        self.assertEqual(states[0], [])
        self.assertNotEqual(states[1], states[2])
        fillet = data["features"][2]
        # HiM: the fillet radius grew from ~0 while Fusion recomputed; frames recorded
        self.assertEqual(len(fillet["frames"]), extract_fusion.FRAMES_PER_FEATURE)
        self.assertEqual(radius.value, 0.2)                          # restored
        self.assertEqual(radius.expression, "2.0 mm")
        self.assertEqual(data["features"][1]["frames"], [])           # no animatable parameter in the stub
        self.assertEqual(fillet["parameters"][0]["name"], "d3")
        self.assertEqual(data["features"][1]["inputs"]["sketches"], [0])
        annotation = {
            "format": "excadmple-annotation", "version": 1, "id": "s", "title": "S",
            "steps": [{"id": "all", "title": "All", "features": [0, 1, 2],
                       "recording": {"start_ms": 0, "end_ms": 5000}}]}
        manifest = build_manifest(data, annotation, [])
        # empty before-state + extrude result + 8 fillet frames + fillet result
        self.assertEqual(len(manifest["steps"][0]["animation"]["states"]), 3 + extract_fusion.FRAMES_PER_FEATURE)


if __name__ == "__main__":
    unittest.main()
