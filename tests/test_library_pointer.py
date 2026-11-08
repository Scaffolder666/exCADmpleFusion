import unittest
from pathlib import Path

from core.library import ExampleLibrary, LibraryError
from core.packages import open_package
from core.pointer import sample, validate_pointer, PointerError

ROOT = Path(__file__).resolve().parents[1]


class LibraryTests(unittest.TestCase):
    def test_multiple_examples_keep_their_own_step(self):
        library = ExampleLibrary()
        phone = library.add(open_package(ROOT / "examples" / "phone_stand.json"))
        tablet = library.add(open_package(ROOT / "examples" / "tablet_stand.json"))
        self.assertEqual(library.active_id, tablet)
        library.remember_step(3)
        library.activate(phone)
        library.remember_step(7)
        self.assertEqual(library.step_index(tablet), 3)
        self.assertEqual(library.step_index(phone), 7)
        self.assertEqual([e["active"] for e in library.listing()], [True, False])
        library.add(open_package(ROOT / "examples" / "phone_stand.json"))   # reopen replaces
        self.assertEqual(len(library), 2)
        library.remove(phone)
        self.assertEqual(library.active_id, tablet)
        with self.assertRaises(LibraryError):
            library.activate("nope")
        library.close()
        self.assertEqual(len(library), 0)


class PointerTests(unittest.TestCase):
    PATH = [{"at_ms": 0, "xyz": [0, 0, 0], "event": "move"},
            {"at_ms": 1000, "xyz": [10, 0, 0], "event": "click"},
            {"at_ms": 2000, "xyz": [10, 10, 0], "event": "drag"}]

    def test_sample_interpolates_and_reports_gestures(self):
        mid = sample(self.PATH, 500)
        self.assertAlmostEqual(mid["xyz"][0], 5.0)
        self.assertFalse(mid["pressed"])
        clicked = sample(self.PATH, 1200)
        self.assertTrue(clicked["pressed"])
        self.assertEqual(clicked["gesture"], "drag")
        self.assertEqual(sample(self.PATH, 5000)["xyz"], [10, 10, 0])
        self.assertGreaterEqual(len(clicked["trail"]), 2)

    def test_validation(self):
        validate_pointer(self.PATH, 2000)
        with self.assertRaises(PointerError):
            validate_pointer(self.PATH, 1500)
        with self.assertRaises(PointerError):
            validate_pointer([{"at_ms": 0, "xyz": [0, 0], "event": "move"}], 100)
        with self.assertRaises(PointerError):
            validate_pointer([{"at_ms": 0, "xyz": [0, 0, 0], "event": "jump"}], 100)

    def test_bundled_examples_have_pointer_paths(self):
        for name in ("phone_stand.json", "tablet_stand.json"):
            package = open_package(ROOT / "examples" / name)
            try:
                meta = package.player_data()
                self.assertTrue(all(s["pointer_available"] for s in meta["steps"]))
                self.assertTrue(all(s["decision"] for s in meta["steps"]))
                self.assertNotIn("pointer", meta["steps"][0])
            finally:
                package.close()


if __name__ == "__main__":
    unittest.main()
