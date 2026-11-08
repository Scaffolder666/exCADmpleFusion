"""ReuseController on a stub adsk: selection -> matched decisions -> watch."""
import types
import unittest
from pathlib import Path

import tests.test_him_fusion_adapter  # noqa: F401  (installs the adsk stub)
from core.library import ExampleLibrary
from core.packages import open_package
from core.reuse_fusion import ReuseController

ROOT = Path(__file__).resolve().parents[1]


class FakeHiM:
    selection_label = "Face"

    def __init__(self):
        self.explained = []

    def explain(self, entity):
        self.explained.append(entity)

    def describe(self):
        return {"features": [
            {"timeline_index": 5, "name": "Corner fillet", "kind": "FilletFeature", "key": "tok-f",
             "role": "created", "parameters": [{"name": "d9", "unit": "mm", "value": 0.6, "expression": "6 mm"}]},
            {"timeline_index": 1, "name": "Extrude1", "kind": "ExtrudeFeature", "key": "tok-e",
             "role": "created", "parameters": []},
        ]}


class ReuseControllerTests(unittest.TestCase):
    def setUp(self):
        self.app = types.SimpleNamespace(activeProduct=None)
        self.library = ExampleLibrary()
        for name in ("tablet_stand.json", "phone_stand.json"):
            self.library.add(open_package(ROOT / "examples" / name))
        self.posts, self.opened = [], []
        self.controller = ReuseController(self.app, None, FakeHiM(), self.library,
                                          lambda a, p: self.posts.append((a, p)),
                                          lambda example_id, index: self.opened.append((example_id, index)))

    def tearDown(self):
        self.library.close()

    def last_view(self):
        return [p for a, p in self.posts if a == "reuse_view"][-1]

    def test_selection_matches_and_watch(self):
        self.controller.explain(object())
        view = self.last_view()
        fillet = view["features"][0]
        self.assertEqual(fillet["matches"][0]["ref"]["topic"], "edge_rounding")
        self.assertEqual(fillet["matches"][0]["comparison"]["nearest_option"], "Soft")
        self.assertEqual(len(view["topics"]), 9)
        self.controller.watch("phone-stand", "base_round")
        self.assertEqual(self.opened, [("phone-stand", 3)])

    def test_document_change_clears_selection(self):
        self.controller.explain(object())
        self.controller.document_changed()
        self.assertEqual(self.last_view()["features"], [])


if __name__ == "__main__":
    unittest.main()
