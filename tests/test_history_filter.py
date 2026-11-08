"""HiM-style filtering on a design example (ui/shared/history_filter.js via Node)."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "ui" / "shared" / "history_filter.js"


def run(script, data):
    code = "const F = require(%s); const data = JSON.parse(require('fs').readFileSync(0,'utf8'));\n%s" % (
        json.dumps(str(JS)), script)
    out = subprocess.run(["node", "-e", code], input=json.dumps(data), capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HistoryFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.steps = json.loads((ROOT / "examples" / "phone_stand.json").read_text(encoding="utf-8"))["steps"]
        cls.ids = [s["id"] for s in cls.steps]

    def changed(self, point, upto=None):
        result = run("const ix = F.buildIndex(data.steps);"
                     "process.stdout.write(JSON.stringify(F.changedAt(ix, data.p, data.upto === null ? undefined : data.upto)));",
                     {"steps": self.steps, "p": point, "upto": upto})
        return [self.ids[i] for i in result]

    def test_lip_was_made_by_the_lip_step_and_cut_by_the_cable_step(self):
        self.assertEqual(self.changed([2.0, 0.7, 1.7]), ["lip", "cable"])

    def test_rounded_corner_is_changed_by_fillet_but_not_later_steps(self):
        corner = [0.2343, 0.2343, 0.7]       # on the rounded base, near a corner
        found = self.changed(corner)
        self.assertIn("base_round", found)
        self.assertNotIn("pads", found)
        self.assertNotIn("back_window", found)

    def test_window_edge_shows_window_step_only_up_to_shown_state(self):
        rail = self.steps[7]["geometry"]["meshes"][1]["vertices"][4]   # back panel, after the window cut
        self.assertIn("back_window", self.changed(rail))
        self.assertNotIn("back_window", self.changed(rail, upto=6))

    def test_show_more_follows_dependencies_one_level(self):
        more = run("const ix = F.buildIndex(data.steps); process.stdout.write(JSON.stringify(F.buildsOn(ix, data.picked)));",
                   {"steps": self.steps, "picked": [self.ids.index("cable")]})
        self.assertEqual([self.ids[i] for i in more], ["lip"])

    def test_point_off_the_model_matches_nothing(self):
        self.assertEqual(self.changed([100, 100, 100]), [])


if __name__ == "__main__":
    unittest.main()
