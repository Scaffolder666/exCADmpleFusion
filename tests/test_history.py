import unittest
from core.history import HistoryError, relevant_history


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.features = [
            {"id":"ground","type":"extrude","affects":["base"]},
            {"id":"sketch","type":"sketch","affects":[],"sketch_plane_feature":"ground"},
            {"id":"extrude","type":"extrude","inputs":["sketch"],"affects":["rod"]},
            {"id":"thread","type":"thread","inputs":["extrude"],"affects":["rod"]},
            {"id":"pattern","type":"pattern","inputs":["thread"],"affects":["rod"]},
            {"id":"unrelated","type":"fillet","affects":["other"]},
        ]

    def test_selected_entity_returns_reverse_feature_order(self):
        self.assertEqual([f["id"] for f in relevant_history(self.features,"rod")],
                         ["pattern","thread","extrude","sketch"])

    def test_show_more_expands_sketch_support(self):
        self.assertEqual([f["id"] for f in relevant_history(self.features,"rod",True)],
                         ["pattern","thread","extrude","sketch","ground"])

    def test_unrelated_selection(self):
        self.assertEqual([f["id"] for f in relevant_history(self.features,"other")],["unrelated"])

    def test_cycle_rejected(self):
        data=[{"id":"a","type":"extrude","affects":["x"],"inputs":["b"]},
              {"id":"b","type":"fillet","inputs":["a"]}]
        with self.assertRaises(HistoryError):
            relevant_history(data,"x")


if __name__ == "__main__":
    unittest.main()
