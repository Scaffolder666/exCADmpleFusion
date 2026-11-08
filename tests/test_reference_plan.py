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
        self.assertEqual(missing, ["Gone"])

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
