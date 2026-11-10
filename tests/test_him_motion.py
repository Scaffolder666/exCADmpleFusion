"""HiM parameter registry, interpolation and restore logic."""
import unittest

from core.playback.him_motion import (RestoreJournal, FEATURES, animation_mode,
                             interpolate, PARAMETRIC, FADE, NONE)


class MotionTests(unittest.TestCase):
    def test_twenty_supported_features(self):
        self.assertEqual(len(FEATURES), 20)
        self.assertEqual(animation_mode("adsk::fusion::ExtrudeFeature"), PARAMETRIC)
        self.assertEqual(animation_mode("adsk::fusion::MirrorFeature"), FADE)
        self.assertEqual(animation_mode("adsk::fusion::SomeThirdPartyFeature"), NONE)

    def test_interpolate_keeps_sign_and_avoids_zero(self):
        self.assertAlmostEqual(interpolate(-2.0, 1.0), -2.0)
        self.assertGreater(abs(interpolate(5.0, 0.0)), 0)
        self.assertAlmostEqual(interpolate(10.0, 0.5), 5.1)

    def test_restore_journal(self):
        class Param:
            def __init__(self, expression):
                self.expression = expression
        a, b = Param("10 mm"), Param("d1 * 2")
        journal = RestoreJournal()
        journal.capture("a", a)
        journal.capture("b", b)
        a.expression, b.expression = "0.2 mm", "3 mm"
        journal.capture("a", a)        # second capture keeps the original
        journal.restore()
        self.assertEqual((a.expression, b.expression), ("10 mm", "d1 * 2"))
        self.assertEqual(len(journal), 0)


if __name__ == "__main__":
    unittest.main()
