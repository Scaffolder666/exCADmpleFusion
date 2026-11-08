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
        mesh = types.SimpleNamespace(nodeCoordinatesAsDouble=[0, 0, z, 1, 0, z, 0, 1, z], nodeIndices=[0, 1, 2])
        calc = types.SimpleNamespace(setQuality=lambda q: None, calculate=lambda: mesh)
        self.meshManager = types.SimpleNamespace(createMeshCalculator=lambda: calc)


class ExtractTests(unittest.TestCase):
    def test_extract_states_and_build(self):
        design, entities, radius = stub.build()
        timeline = design.timeline
        base, rounded = Body(0.0), Body(0.1)

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
        self.assertEqual(len(data["meshes"]), 2)
        fillet = data["features"][2]
        self.assertEqual(fillet["parameters"][0]["name"], "d3")
        self.assertEqual(data["features"][1]["inputs"]["sketches"], [0])
        annotation = {
            "format": "excadmple-annotation", "version": 1, "id": "s", "title": "S",
            "steps": [{"id": "all", "title": "All", "features": [0, 1, 2],
                       "recording": {"start_ms": 0, "end_ms": 5000}}]}
        manifest = build_manifest(data, annotation, [])
        self.assertEqual(len(manifest["steps"][0]["animation"]["states"]), 3)


if __name__ == "__main__":
    unittest.main()
