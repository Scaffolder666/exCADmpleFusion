"""Pure-Python tests for real pre-feature ghost context capture and isolation.

These DO NOT claim Fusion Desktop renderer fidelity.
"""
import types
import unittest

from tests import test_him_fusion_adapter as stub  # provides fake adsk
from core.him_wireframe import (capture_before_feature, can_isolate_feature,
                                WireframeOverflow)


class GhostContextTests(unittest.TestCase):
    @staticmethod
    def model(bodies):
        return types.SimpleNamespace(allComponents=stub.Coll([
            types.SimpleNamespace(bRepBodies=stub.Coll(bodies))]))

    @staticmethod
    def body(token, *curves, visible=True):
        edges = stub.Coll([types.SimpleNamespace(geometry=c) for c in curves])
        return stub.Obj("BRepBody", token, edges=edges, isVisible=visible, opacity=1.0)

    def test_collects_only_pre_feature_real_brep_edges(self):
        before = self.model([self.body("a", "actual-circle", "actual-line"),
                             self.body("b", "another-curve")])
        result = capture_before_feature(before)
        self.assertEqual(result["curves"],
                         ("actual-circle", "actual-line", "another-curve"))
        self.assertEqual(result["body_tokens"], frozenset({"a", "b"}))
        self.assertEqual(result["body_count"], 2)

    def test_an_edge_without_geometry_is_skipped_not_fatal(self):
        """A revolved body's degenerate apex edge has no curve. It used to
        discard the whole context (steps fell back to Fusion recompute)."""
        before = self.model([self.body("cone", "rim-circle", None, "seam-line")])
        result = capture_before_feature(before)
        self.assertEqual(result["curves"], ("rim-circle", "seam-line"))
        self.assertEqual(result["body_tokens"], frozenset({"cone"}))

    def test_nothing_before_the_first_solid_is_an_empty_context(self):
        result = capture_before_feature(self.model([]))
        self.assertEqual((result["curves"], result["body_count"]), ((), 0))

    def test_existing_hidden_body_is_not_drawn(self):
        before = self.model([self.body("a", "line"),
                             self.body("secret", "should-not-display", visible=False)])
        result = capture_before_feature(before)
        self.assertEqual(result["curves"], ("line",))
        self.assertEqual(result["body_tokens"], frozenset({"a"}))

    def test_edge_budget_rejects_partial_context_instead_of_hiding_solids(self):
        before = self.model([self.body("a", "one", "two"),
                             self.body("b", "three")])
        with self.assertRaises(WireframeOverflow):
            capture_before_feature(before, max_edges=2)
        with self.assertRaises(WireframeOverflow):
            capture_before_feature(before, max_bodies=1)

    def test_unavailable_mesh_edges_causes_explicit_fallback(self):
        before = self.model([self.body("a", "line"),
                             stub.Obj("BRepBody", "mesh-like", opacity=1.0)])
        self.assertIsNone(capture_before_feature(before))

    def test_same_body_fillet_not_mislabeled_as_new_body(self):
        before = frozenset({"existing"})
        target = self.body("existing", "real-edge")
        self.assertFalse(can_isolate_feature("FilletFeature", [], [target], before))
        self.assertFalse(can_isolate_feature("ExtrudeFeature", [], [target], before))
        self.assertTrue(can_isolate_feature("FilletFeature", [object()], [target], before))
        new_body = self.body("new", "real-edge")
        self.assertTrue(can_isolate_feature("ExtrudeFeature", [], [new_body], before))
        self.assertFalse(can_isolate_feature("CombineFeature", [], [new_body], before))


if __name__ == "__main__":
    unittest.main()
