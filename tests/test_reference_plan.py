import unittest

from core.him_filter import FeatureInfo
from core.reference_plan import map_steps, frame_target, steps_for_features

F = [FeatureInfo(0, "Sketch1", "Sketch"), FeatureInfo(1, "Extrude1", "ExtrudeFeature"),
     FeatureInfo(2, "Fillet1", "FilletFeature"), FeatureInfo(3, "Sketch2", "Sketch"),
     FeatureInfo(4, "Extrude2", "ExtrudeFeature")]
STEPS = [{"source_features": [{"name": "Sketch1", "index": 0}, {"name": "Extrude1", "index": 1},
                              {"name": "Fillet1", "index": 2}]},
         {"source_features": [{"name": "Sketch2", "index": 3}, {"name": "Extrude2", "index": 4},
                              {"name": "Gone", "index": 9}]},
         {}]


class ReferencePlanTests(unittest.TestCase):
    def test_map_steps_by_name_and_reports_missing(self):
        mapped, missing = map_steps(STEPS, F)
        self.assertEqual([[f.name for f in m] for m in mapped],
                         [["Sketch1", "Extrude1", "Fillet1"], ["Sketch2", "Extrude2"], []])
        self.assertEqual(missing, ["step ?: Gone (index 9) - not in the model"])

    def test_duplicate_feature_names_require_exact_index(self):
        features = [FeatureInfo(1, "Extrude", "ExtrudeFeature"),
                    FeatureInfo(2, "Extrude", "ExtrudeFeature")]
        steps = [{"id": "ambiguous", "source_features": [{"name": "Extrude", "index": 9}]},
                 {"id": "exact", "source_features": [{"name": "Extrude", "index": 2}]}]
        mapped, missing = map_steps(steps, features)
        self.assertEqual(mapped[0], [])
        self.assertEqual([f.index for f in mapped[1]], [2])
        self.assertEqual(missing, ["step ambiguous: Extrude (index 9) - 2 timeline items share this name"])

    def test_shifted_index_accepts_a_unique_name_of_the_same_kind(self):
        steps = [{"id": "s", "source_features": [{"name": "Fillet1", "index": 7, "kind": "FilletFeature"}]}]
        mapped, missing = map_steps(steps, F)
        self.assertEqual([f.index for f in mapped[0]], [2])
        self.assertEqual(missing, [])

    def test_kind_mismatch_is_reported_not_animated(self):
        steps = [{"id": "a", "source_features": [{"name": "Extrude1", "index": 1, "kind": "RevolveFeature"}]},
                 {"id": "b", "source_features": [{"name": "Fillet1", "index": 5, "kind": "ChamferFeature"}]}]
        mapped, missing = map_steps(steps, F)
        self.assertEqual(mapped, [[], []])
        self.assertEqual(len(missing), 2)
        self.assertIn("ExtrudeFeature", missing[0])
        self.assertIn("ChamferFeature", missing[1])

    def test_a_timeline_item_belongs_to_one_step_only(self):
        steps = [{"id": "a", "source_features": [{"name": "Extrude1", "index": 1}]},
                 {"id": "b", "source_features": [{"name": "Extrude1", "index": 1}]}]
        mapped, missing = map_steps(steps, F)
        self.assertEqual([[f.index for f in m] for m in mapped], [[1], []])
        self.assertEqual(missing, ["step b: Extrude1 (index 1) - already used by step a"])

    def test_duplicate_names_with_exact_indices_map_to_their_own_items(self):
        features = [FeatureInfo(1, "Extrude", "ExtrudeFeature"), FeatureInfo(2, "Extrude", "ExtrudeFeature")]
        steps = [{"id": "a", "source_features": [{"name": "Extrude", "index": 1}]},
                 {"id": "b", "source_features": [{"name": "Extrude", "index": 2}]}]
        mapped, missing = map_steps(steps, features)
        self.assertEqual([[f.index for f in m] for m in mapped], [[1], [2]])
        self.assertEqual(missing, [])

    def test_frame_target_splits_time_between_animated_features(self):
        mapped, _ = map_steps(STEPS, F)
        self.assertEqual(frame_target(mapped[0], 0.0), (0, 0.0))     # Extrude1 starts
        position, t = frame_target(mapped[0], 0.75)
        self.assertEqual(position, 1)                                  # Fillet1, halfway
        self.assertAlmostEqual(t, 0.5)
        self.assertEqual(frame_target(mapped[0], 1.0), (1, 1.0))
        self.assertEqual(frame_target(mapped[2], 0.3), (None, 1.0))   # nothing to animate

    def test_filter_result_to_steps(self):
        mapped, _ = map_steps(STEPS, F)
        self.assertEqual(steps_for_features(mapped, [4, 2]), [0, 1])
        self.assertEqual(steps_for_features(mapped, [7]), [])


if __name__ == "__main__":
    unittest.main()
