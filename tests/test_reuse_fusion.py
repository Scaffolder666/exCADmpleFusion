"""ReuseController on a stub adsk: selection -> matches -> notebook stored
in the design's attributes."""
import types
import unittest
from pathlib import Path

import tests.test_him_fusion_adapter  # noqa: F401  (installs the adsk stub)
from core.library import ExampleLibrary
from core.packages import open_package
from core.reuse_fusion import ReuseController, ATTR_GROUP, ATTR_NAME

ROOT = Path(__file__).resolve().parents[1]


class Attributes:
    def __init__(self):
        self.store = {}

    def itemByName(self, group, name):
        value = self.store.get((group, name))
        return types.SimpleNamespace(value=value) if value is not None else None

    def add(self, group, name, value):
        self.store[(group, name)] = value


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
        self.attributes = Attributes()
        design = types.SimpleNamespace(_type="Design", attributes=self.attributes,
                                       rootComponent=types.SimpleNamespace(entityToken="doc-1"))
        self.app = types.SimpleNamespace(activeProduct=design)
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

    def test_selection_record_and_watch(self):
        self.controller.explain(object())
        view = self.last_view()
        fillet = view["features"][0]
        self.assertEqual(fillet["matches"][0]["ref"]["topic"], "edge_rounding")
        self.assertEqual(fillet["matches"][0]["comparison"]["nearest_option"], "Soft")
        self.assertEqual(len(view["topics"]), 9)
        self.controller.record({"example_id": "phone-stand", "step_id": "base_round",
                                "feature_key": "tok-f", "stance": "adapt", "note": "smaller radius"})
        raw = self.attributes.store[(ATTR_GROUP, ATTR_NAME)]
        self.assertIn("smaller radius", raw)
        view = self.last_view()
        self.assertEqual(view["summary"]["adapt"], 1)
        self.assertEqual(view["features"][0]["matches"][0]["stance"], "adapt")
        self.assertEqual(view["notebook"][0]["user_value"], "6 mm")
        self.controller.watch("phone-stand", "base_round")
        self.assertEqual(self.opened, [("phone-stand", 3)])

    def test_notebook_reloads_from_another_document(self):
        self.controller.record({"example_id": "tablet-stand", "step_id": "cork", "stance": "reject"})
        other = types.SimpleNamespace(_type="Design", attributes=Attributes(),
                                      rootComponent=types.SimpleNamespace(entityToken="doc-2"))
        self.app.activeProduct = other
        self.controller.document_changed()
        self.assertEqual(self.last_view()["notebook"], [])


if __name__ == "__main__":
    unittest.main()
