"""Focus Mode tests without a Fusion desktop or Autodesk adsk module."""
import unittest
from core.focus import OpacityFocus, FocusError, MAX_DIM_BODIES


class FakeBody:
    def __init__(self, opacity=1.0, fail=False):
        self._opacity = opacity
        self.fail = fail

    @property
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, value):
        if self.fail:
            raise RuntimeError("Fusion could not update body")
        self._opacity = value


class FocusTests(unittest.TestCase):
    def setUp(self):
        self.active_doc = "caster"
        self.bodies = {
            "wheel": FakeBody(0.88),
            "fork": FakeBody(1.0),
            "plate": FakeBody(0.65),
            "already-ghosted": FakeBody(0.10),
        }
        self.focus = OpacityFocus(
            lambda token: self.bodies.get(token),
            lambda: self.active_doc,
        )

    def items(self):
        return list(self.bodies.items())

    def test_focused_part_retains_original_and_background_dims(self):
        changed = self.focus.apply("caster", self.items(), {"wheel"}, 0.24)
        self.assertEqual(changed, 2)
        self.assertEqual(self.bodies["wheel"].opacity, 0.88)
        self.assertEqual(self.bodies["fork"].opacity, 0.24)
        self.assertEqual(self.bodies["plate"].opacity, 0.24)
        self.assertEqual(self.bodies["already-ghosted"].opacity, 0.10)
        self.focus.restore()
        self.assertEqual([self.bodies[k].opacity for k in self.bodies],
                         [0.88, 1.0, 0.65, 0.10])
        self.assertFalse(self.focus.active)

    def test_step_switch_restores_before_reapplying(self):
        self.focus.apply("caster", self.items(), {"wheel"}, 0.24)
        self.focus.apply("caster", self.items(), {"fork"}, 0.24)
        self.assertEqual(self.bodies["wheel"].opacity, 0.24)
        self.assertEqual(self.bodies["fork"].opacity, 1.0)
        self.focus.restore()
        self.assertEqual(self.bodies["wheel"].opacity, 0.88)

    def test_shared_native_body_is_protected_by_token(self):
        # Two instances of the same native component enumerate to one token.
        items = [("wheel", self.bodies["wheel"]),
                 ("wheel", self.bodies["wheel"]),
                 ("fork", self.bodies["fork"])]
        self.focus.apply("caster", items, {"wheel"}, 0.24)
        self.assertEqual(self.bodies["wheel"].opacity, 0.88)
        self.assertEqual(self.bodies["fork"].opacity, 0.24)
        self.focus.restore()

    def test_document_switch_prevents_wrong_restore(self):
        self.focus.apply("caster", self.items(), {"wheel"}, 0.24)
        self.active_doc = "unrelated"
        with self.assertRaises(FocusError):
            self.focus.restore()
        self.assertTrue(self.focus.active)
        self.active_doc = "caster"
        self.focus.restore()
        self.assertFalse(self.focus.active)

    def test_partial_apply_error_rolls_back_prior_changes(self):
        self.bodies["plate"].fail = True
        with self.assertRaises(RuntimeError):
            self.focus.apply("caster", self.items(), {"wheel"}, 0.24)
        self.assertEqual(self.bodies["fork"].opacity, 1.0)
        self.assertFalse(self.focus.active)

    def test_fail_closed_on_empty_target_or_wrong_document(self):
        with self.assertRaises(FocusError):
            self.focus.apply("caster", self.items(), set())
        with self.assertRaises(FocusError):
            self.focus.apply("other", self.items(), {"wheel"})

    def test_fails_before_changes_for_too_many_background_bodies(self):
        huge = [("b"+str(i), FakeBody()) for i in range(MAX_DIM_BODIES+1)]
        with self.assertRaises(FocusError):
            self.focus.apply("caster", huge, {"wheel"})
        self.assertFalse(self.focus.active)


if __name__ == "__main__":
    unittest.main()
