"""HiM animation timing, playback and restore logic."""
import unittest

from core.him_motion import (AdaptiveStepper, Playback, RestoreJournal, FEATURES, animation_mode,
                             initial_frames, interpolate, seconds_per_feature, PARAMETRIC, FADE, NONE)


class MotionTests(unittest.TestCase):
    def test_twenty_supported_features(self):
        self.assertEqual(len(FEATURES), 20)
        self.assertEqual(animation_mode("adsk::fusion::ExtrudeFeature"), PARAMETRIC)
        self.assertEqual(animation_mode("adsk::fusion::MirrorFeature"), FADE)
        self.assertEqual(animation_mode("adsk::fusion::SomeThirdPartyFeature"), NONE)

    def test_speed_range_and_initial_frames(self):
        self.assertEqual(seconds_per_feature(1), 2)
        self.assertEqual(seconds_per_feature(30), 10)
        self.assertEqual(initial_frames(2), 15)
        self.assertEqual(initial_frames(10), 75)
        self.assertEqual(initial_frames(6), 45)

    def test_interpolate_keeps_sign_and_avoids_zero(self):
        self.assertAlmostEqual(interpolate(-2.0, 1.0), -2.0)
        self.assertGreater(abs(interpolate(5.0, 0.0)), 0)
        self.assertAlmostEqual(interpolate(10.0, 0.5), 5.1)

    def test_adaptive_stepper_finishes_on_time(self):
        slow = AdaptiveStepper(2)
        progress, elapsed = 0.0, 0.0
        while progress < 1.0:
            progress += slow.next_increment(0.5, progress)
            elapsed += 0.5
        self.assertLessEqual(elapsed, 2.5)
        fast = AdaptiveStepper(2)
        self.assertLess(fast.next_increment(0.01, 0.0), slow.increment + 1)
        self.assertLess(fast.increment, 0.05)

    def run_until_stop(self, playback, frame=0.1, limit=1000):
        frames = []
        for _ in range(limit):
            if not playback.playing:
                break
            frames.append(playback.tick(frame))
        return frames

    def test_full_clip_plays_each_feature_forward_in_order(self):
        playback = Playback(3, seconds=2)
        playback.play()
        frames = self.run_until_stop(playback)
        order = []
        for f in frames:
            if not order or order[-1] != f.position:
                order.append(f.position)
        self.assertEqual(order, [0, 1, 2])
        self.assertTrue(frames[-1].finished)
        self.assertEqual(frames[-1].progress, 1.0)

    def test_step_backward_reverses_playback(self):
        playback = Playback(3, seconds=2)
        playback.play()
        self.run_until_stop(playback)
        playback.step_backward()
        frames = self.run_until_stop(playback)
        self.assertTrue(all(b.progress <= a.progress for a, b in zip(frames, frames[1:])))
        self.assertEqual(frames[-1].progress, 0.0)
        self.assertEqual(frames[-1].position, 2)
        playback.step_backward()               # previous (newer) feature, reversed
        self.assertEqual(playback.position, 1)
        self.assertEqual(playback.direction, -1)

    def test_step_forward_and_pause_replay(self):
        playback = Playback(3, seconds=2)
        playback.step_forward()
        self.run_until_stop(playback)
        self.assertEqual(playback.position, 0)
        playback.step_forward()
        self.assertEqual(playback.position, 1)
        playback.pause()
        self.assertFalse(playback.tick(0.1).progress > 0)
        playback.replay()
        self.assertEqual((playback.position, playback.progress, playback.playing), (0, 0.0, True))

    def test_non_animatable_features_pass_instantly(self):
        playback = Playback(3, seconds=2, animatable=[True, False, True])
        playback.play()
        positions = {f.position for f in self.run_until_stop(playback)}
        self.assertIn(2, positions)

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
