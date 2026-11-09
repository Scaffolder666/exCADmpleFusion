"""logs/latest.log: what a run did, for diagnosis."""
import json
import tempfile
import unittest
from pathlib import Path

from core import diagnostics
from core.diagnostics import DiagnosticLog


class DiagnosticLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "logs"

    def test_session_and_latest_files_get_the_same_lines(self):
        log = DiagnosticLog(self.folder, "build v10")
        log.header(fusion="2.0.21000")
        log.write("frame", "step 3 at 40%", {"feature": "Move3", "motion": "illustrative"})
        try:
            raise RuntimeError("3 : Didn't roll editing feature back.")
        except RuntimeError:
            log.exception("Move3")
        latest = (self.folder / "latest.log").read_text(encoding="utf-8")
        self.assertEqual(latest, log.path.read_text(encoding="utf-8"))
        self.assertIn('"build": "build v10"', latest)
        self.assertIn('"fusion": "2.0.21000"', latest)
        self.assertIn('[frame] step 3 at 40% {"feature": "Move3", "motion": "illustrative"}', latest)
        self.assertIn("Didn't roll editing feature back", latest)
        self.assertIn("Traceback", latest)

    def test_a_new_run_starts_a_new_latest_and_old_sessions_are_pruned(self):
        for i in range(diagnostics.KEEP + 3):
            path = self.folder / "session-2026010{:02d}-000000.log".format(i)
            self.folder.mkdir(parents=True, exist_ok=True)
            path.write_text("old")
        log = DiagnosticLog(self.folder)
        log.write("x", "new run")
        self.assertEqual((self.folder / "latest.log").read_text(encoding="utf-8").count("new run"), 1)
        self.assertNotIn("old", (self.folder / "latest.log").read_text(encoding="utf-8"))
        self.assertEqual(len(list(self.folder.glob("session-*.log"))), diagnostics.KEEP)

    def test_size_is_capped_and_unwritable_folders_never_raise(self):
        old = diagnostics.MAX_BYTES
        diagnostics.MAX_BYTES = 200
        try:
            log = DiagnosticLog(self.folder)
            for i in range(20):
                log.write("x", "line {}".format(i))
            text = (self.folder / "latest.log").read_text(encoding="utf-8")
            self.assertIn("size limit reached", text)
            self.assertLess(len(text), 400)
        finally:
            diagnostics.MAX_BYTES = old
        blocked = Path(self.tmp.name) / "file"
        blocked.write_text("not a folder")
        log = DiagnosticLog(blocked / "logs")
        log.write("x", "nowhere to go")              # no exception
        log.exception()
        self.assertIsNone(log.path)


if __name__ == "__main__":
    unittest.main()
