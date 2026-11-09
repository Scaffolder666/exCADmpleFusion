"""Playback cost on a stubbed Fusion design: a feature with several
animated parameters is updated in one recompute (Design.modifyParameters),
with a per-parameter fallback, and slow frames are logged. Real Fusion
timings need Fusion Desktop."""
import types
import unittest

from tests import test_him_native as native             # installs the adsk stub
import adsk.core
from core.him_motion import interpolate


class BatchedParameterTests(unittest.TestCase):
    def setUp(self):
        self.design, self.entities, _ = native.build()
        extrude = self.entities["ex1"]
        extrude.extentTwo = types.SimpleNamespace(distance=native.Param("d1b", 0.5, extrude))
        self.d1, self.d1b = extrude.extentOne.distance, extrude.extentTwo.distance
        self.calls = []

        def modify(params, values):
            self.calls.append([p.name for p in params])
            for p, v in zip(params, values):
                object.__setattr__(p, "value", v)            # one recompute for all
            return True
        self.design.modifyParameters = modify
        adsk.core.ValueInput = types.SimpleNamespace(createByReal=lambda v: v)
        self.logged = []
        _, self.session = native.session_for(self.design)
        self.session.log = self.logged.append
        self.session.him.log = self.logged.append

    def tearDown(self):
        self.session.close()
        del adsk.core.ValueInput

    def test_two_sided_extrude_is_one_update_per_frame(self):
        for progress in (0.2, 0.5, 0.8):
            self.session.frame(0, progress)
            self.assertAlmostEqual(self.d1.value, interpolate(1.0, progress))
            self.assertAlmostEqual(self.d1b.value, interpolate(0.5, progress))
        self.assertEqual(self.calls, [["d1", "d1b"]] * 3)
        self.assertEqual([k for k, _ in self.d1.writes if k == "value"], [])   # no per-parameter recompute
        self.session.stop()
        self.assertAlmostEqual(self.d1.value, 1.0)               # restored as before
        self.assertAlmostEqual(self.d1b.value, 0.5)

    def test_falls_back_to_one_by_one_when_batching_fails(self):
        def broken(params, values):
            raise RuntimeError("not supported in this Fusion version")
        self.design.modifyParameters = broken
        self.session.frame(0, 0.5)
        self.assertAlmostEqual(self.d1.value, interpolate(1.0, 0.5))
        self.assertAlmostEqual(self.d1b.value, interpolate(0.5, 0.5))
        self.assertTrue(any("batched parameter update unavailable" in m for m in self.logged))

    def test_single_parameter_features_are_unchanged(self):
        self.session.frame(1, 0.5)                               # Fillet1: one radius
        self.assertEqual(self.calls, [])
        self.assertAlmostEqual(native.param(self.entities, "fi1").value, interpolate(0.2, 0.5))

    def test_slow_frames_are_logged_with_their_cause(self):
        self.session.SLOW_FRAME_SECONDS = -1                     # every frame counts as slow
        self.session.frame(1, 0.5)
        timing = self.session.last_timing
        self.assertEqual((timing["feature"], timing["kind"]), ("Fillet1", "FilletFeature"))
        self.assertTrue(any(m.startswith("Slow frame Fillet1") and "recompute" in m for m in self.logged))


if __name__ == "__main__":
    unittest.main()
