"""One visual language for every step (stubbed Fusion): sketch steps dim
the rest of the model like other steps; changed faces are always opaque
teal; a whole pre-existing part is never painted as a step's change; a
finished step keeps its look until the next one. Not a Fusion test."""
import types
import unittest

from tests import test_him_native as native             # installs the adsk stub
import adsk.fusion
from core.him_motion import interpolate
from core.reference_plan import map_steps

Obj, Coll = native.Obj, native.Coll


class VisualConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.design, self.entities, self.groups = native.build()
        _, self.session = native.session_for(self.design, dim=True)
        self.session.him.wireframe_context = False            # translucent-context style
        adsk.fusion.TemporaryBRepManager = types.SimpleNamespace(
            get=lambda: types.SimpleNamespace(copy=lambda item: ("copy", item.entityToken)))

    def tearDown(self):
        self.session.close()
        del adsk.fusion.TemporaryBRepManager

    def opacities(self):
        return [self.entities[t].opacity for t in ("body0", "body1", "body2")]

    def test_a_sketch_step_dims_the_model_like_any_other_step(self):
        self.session.mapped, _ = map_steps([{"id": "s", "source_features": [{"name": "Sketch1", "index": 0}]},
                                            {"id": "e", "source_features": [{"name": "Extrude1", "index": 1}]}],
                                           self.session.model.features())
        self.session.frame(0, 0.5)
        self.assertEqual(self.opacities(), [0.2, 0.2, 0.2])
        self.session.frame(1, 0.5)                          # next step: its own context
        self.assertEqual(self.entities["body1"].opacity, 1.0)
        self.session.stop()
        self.assertEqual(self.opacities(), [0.6, 1.0, 1.0])

    def test_a_sketch_step_shows_the_same_context_look_as_feature_steps(self):
        """Translucent white faces with a dark outline, like every other
        step - not merely dimmed bodies."""
        for token in ("body0", "body1", "body2"):
            self.entities[token].edges = Coll([types.SimpleNamespace(geometry="edge-of-" + token)])
            self.entities[token].isVisible = True
        self.session.him.wireframe_context = True
        self.session.mapped, _ = map_steps([{"id": "s", "source_features": [{"name": "Sketch1", "index": 0}]}],
                                           self.session.model.features())
        self.session.frame(0, 0.5)
        ghost = self.session.him.ghost_group
        self.assertIsNotNone(ghost)
        self.assertEqual(len(ghost.curves), 3)                               # dark outline
        self.assertEqual([b.opacity for b in ghost.bodies], [0.28, 0.28, 0.28])   # translucent white faces
        self.assertTrue(all(o < 0.01 for o in self.opacities()))              # native bodies hidden
        self.session.stop()
        self.assertEqual(self.opacities(), [0.6, 1.0, 1.0])

    def test_changed_faces_are_opaque_teal(self):
        fillet = self.entities["fi1"]
        fillet.faces = Coll([Obj("BRepFace", "round-face")])
        self.session.frame(1, 0.5)
        bodies = self.session.him.group.bodies
        self.assertEqual([b.opacity for b in bodies], [1.0])

    def test_a_whole_existing_part_is_not_painted_as_the_change(self):
        # Fillet1 reports no faces: the only candidate is all of body1,
        # which existed before the fillet (the existing isolation rule).
        self.session.frame(1, 0.5)
        self.assertEqual(self.session.him.group.bodies, [])
        self.assertAlmostEqual(native.param(self.entities, "fi1").value, interpolate(0.2, 0.5))

    def test_a_finished_step_keeps_its_look_until_the_next_step(self):
        fillet = self.entities["fi1"]
        fillet.faces = Coll([Obj("BRepFace", "round-face")])
        self.session.frame(1, 0.9)
        shown = self.session.frame(1, 1.0)
        self.assertEqual(shown["mode"], "parameter")
        self.assertEqual(native.param(self.entities, "fi1").value, 0.2)        # exactly the real value
        self.assertEqual([b.opacity for b in self.session.him.group.bodies], [1.0])
        self.assertEqual(self.entities["body0"].opacity, 0.2)                  # context unchanged
        self.session.frame(2, 0.1)
        self.assertEqual(native.param(self.entities, "fi1").expression, "2.0 mm")


if __name__ == "__main__":
    unittest.main()
