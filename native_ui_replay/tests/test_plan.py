"""Pure-python smoke checks; does not require Fusion or macOS."""
import importlib.util
import pathlib
import unittest

FILE = pathlib.Path(__file__).resolve().parents[1] / "mac_replay.py"
spec = importlib.util.spec_from_file_location("mac_replay", FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NativeReplayPlanTests(unittest.TestCase):
    def test_full_phone_stand_sequence(self):
        self.assertEqual(len(module.STEPS), 4)
        self.assertEqual([step["hotkey"] for step in module.STEPS],
                         ["e", "e", "e", "f"])
        self.assertEqual(
            [step["value"] for step in module.STEPS],
            ["8 mm", "6 mm", "5 mm", "2 mm"])

    def test_only_two_numeric_fields(self):
        self.assertEqual({step["field"] for step in module.STEPS},
                         {"extrude_distance", "fillet_radius"})

    def test_all_targets_distinct(self):
        self.assertEqual(len({step["target"] for step in module.STEPS}), 4)


if __name__ == "__main__":
    unittest.main()
