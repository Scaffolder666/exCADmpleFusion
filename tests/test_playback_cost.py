"""Work saved per step (stubbed Fusion): a revisited step reuses the
context read before it (no Timeline roll back, no body copies), a
parameter that ends at its real value is not written back (no extra
recompute), and slow step starts are logged by phase."""
import types
import unittest

from tests import test_him_native as native             # installs the adsk stub
from tests import test_fast_motion as fast
import adsk.fusion
from core.playback.him_motion import RestoreJournal, interpolate


class JournalTests(unittest.TestCase):
    def test_a_parameter_back_at_its_real_value_is_not_written_again(self):
        design, entities, _ = native.build()
        d1 = entities["ex1"].extentOne.distance
        journal = RestoreJournal()
        journal.capture("d1", d1)
        d1.value = 1.0                                            # the step ended exactly at its value
        d1.writes.clear()
        journal.restore()
        self.assertEqual(d1.writes, [])                           # no write: no recompute
        self.assertEqual(len(journal), 0)

    def test_a_changed_parameter_is_still_restored(self):
        design, entities, _ = native.build()
        d1 = entities["ex1"].extentOne.distance
        journal = RestoreJournal()
        journal.capture("d1", d1)
        object.__setattr__(d1, "value", 0.4)                      # value changed, expression text unchanged
        journal.restore()
        self.assertEqual(d1.writes[-1], ("expression", "10.0 mm"))
        self.assertAlmostEqual(d1.value, 1.0)


class ContextCacheTests(unittest.TestCase):
    """Extrude1 (step 0) and Fillet1 (step 1) of the stub design."""

    tearDown = fast.FastPlaybackTests.tearDown

    def setUp(self):
        fast.FastPlaybackTests.setUp(self)
        self.captures = []
        him = self.session.him
        original = him.capture_ghost_context
        him.capture_ghost_context = lambda: (self.captures.append(1), original())
        self.rolls = []
        model_go = self.session.model.go
        self.session.model.go = lambda state: (self.rolls.append(state), model_go(state))

    def test_revisiting_a_step_reuses_its_context(self):
        self.session.frame(0, 0.5)
        self.session.frame(1, 0.5)
        first = (len(self.captures), list(self.rolls))
        self.session.frame(0, 0.5)                                # back to step 1
        self.assertEqual(len(self.captures), first[0])            # no new capture
        self.assertNotIn(1, self.rolls[len(first[1]):])           # never rolled to "before Extrude1" again
        self.assertEqual(self.session.frame(0, 0.6)["motion"], "exact")
        self.assertAlmostEqual(self.session.him.active["fast_entities"][0][1].transform.cells[(2, 2)],
                               interpolate(1.0, 0.6))

    def test_slow_starts_are_logged_by_phase(self):
        logged = []
        self.session.log = logged.append
        self.session.SLOW_FRAME_SECONDS = -1
        self.session.frame(0, 0.5)
        self.session.frame(1, 0.5)
        self.session.frame(0, 0.5)
        starts = [line for line in logged if line.startswith("Slow start")]
        self.assertEqual(len(starts), 3)
        self.assertIn("inputs", starts[0])
        self.assertIn("roll", starts[0])
        self.assertIn("(cached)", starts[2])


if __name__ == "__main__":
    unittest.main()
