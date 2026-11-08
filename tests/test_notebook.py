import json
import unittest

from core.notebook import Notebook, NotebookError

REF = {"example_id": "phone-stand", "example_title": "Phone Stand", "step_id": "lip",
       "step_title": "Prevent sliding", "topic": "retaining_lip", "question": "How tall?",
       "options": [{"label": "Low"}, {"label": "Medium", "chosen": True}]}


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.store = {"raw": None}
        self.book = Notebook(lambda: self.store["raw"], lambda text: self.store.update(raw=text),
                             clock=lambda: 0)

    def test_record_persists_and_reloads(self):
        entry = self.book.record("adapt", REF, "Thicker case, so 14 mm", {"name": "Lip", "key": "tok"}, "14 mm")
        self.assertEqual(entry["example_choice"], "Medium")
        again = Notebook(lambda: self.store["raw"])
        self.assertEqual(again.entries[0]["note"], "Thicker case, so 14 mm")
        self.assertEqual(again.entries[0]["user_feature"], "Lip")

    def test_same_decision_and_feature_updates_instead_of_duplicating(self):
        self.book.record("undecided", REF, "", {"key": "tok"})
        self.book.record("adopt", REF, "fine", {"key": "tok"})
        self.assertEqual(len(self.book.entries), 1)
        self.assertEqual(self.book.entries[0]["stance"], "adopt")
        self.book.record("reject", REF, "", {"key": "other"})
        self.assertEqual(self.book.summary()["reject"], 1)
        self.assertEqual(len(self.book.entries), 2)

    def test_remove_csv_and_errors(self):
        entry = self.book.record("adopt", REF)
        self.assertIn("retaining_lip", self.book.to_csv())
        self.book.remove(entry["id"])
        self.assertEqual(json.loads(self.store["raw"])["entries"], [])
        with self.assertRaises(NotebookError):
            self.book.record("maybe", REF)
        with self.assertRaises(NotebookError):
            self.book.remove("missing")
        with self.assertRaises(NotebookError):
            Notebook.parse('{"version": 99}')


if __name__ == "__main__":
    unittest.main()
