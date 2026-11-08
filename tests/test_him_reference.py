"""Version A reference session on a stub Fusion design: the timeline is
rolled to each step, parameters untouched, and selection -> steps (HiM)."""
import types
import unittest

from tests import test_him_fusion_adapter as stub        # installs the adsk stub
from core.him_fusion import FusionTimelineModel
from core.him_reference import ReferenceSession
from core.reference_plan import map_steps

STEPS = [
    {"id": "base", "source_features": [{"name": "Sketch1", "index": 0}, {"name": "Extrude1", "index": 1}]},
    {"id": "round", "source_features": [{"name": "Fillet1", "index": 2}]},
]


class FakeApp:
    def __init__(self, design):
        self.activeProduct = design
        self.activeViewport = types.SimpleNamespace(refresh=lambda: None, fit=lambda: None)


class ReferenceSessionTests(unittest.TestCase):
    def setUp(self):
        self.design, self.entities, self.radius = stub.build()
        self.design.allParameters = stub.Coll([self.radius])
        self.design._type = "Design"
        self.design.rootComponent = types.SimpleNamespace(
            entityToken="root", customGraphicsGroups=types.SimpleNamespace(add=lambda: types.SimpleNamespace(
                isSelectable=False, addCurve=lambda c: (_ for _ in ()).throw(RuntimeError("no curves")),
                deleteMe=lambda: None, isValid=True)))
        app = FakeApp(self.design)
        self.session = ReferenceSession(app, None)
        self.session.model = FusionTimelineModel(self.design)
        self.session.mapped, _ = map_steps(STEPS, self.session.model.features())

    def test_each_step_shows_the_real_model_without_changing_parameters(self):
        original = (self.radius.value, self.radius.expression)
        self.session.show_result(0)
        self.assertEqual(self.design.timeline.markerPosition, 2)    # after Extrude1
        self.session.show_result(1)
        self.assertEqual(self.design.timeline.markerPosition, 3)    # last step: whole model
        self.assertEqual((self.radius.value, self.radius.expression), original)

    def test_selection_filters_to_steps(self):
        result = self.session.filter(self.entities["fillet_face"])
        self.assertEqual(result["steps"], [0, 1])
        self.assertEqual(result["tags"], {0: "changed here", 1: "changed here"})
        self.assertIn("Fillet1", result["features"])


if __name__ == "__main__":
    unittest.main()
