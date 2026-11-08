"""Reasoning reuse: decision schema, matching, comparison, cross-example topics."""
import copy
import json
import math
import unittest
from pathlib import Path

from core import reuse
from core.packages import open_package, PackageError

ROOT = Path(__file__).resolve().parents[1]


def examples():
    out = []
    for name in ("phone_stand.json", "tablet_stand.json"):
        data = json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))
        out.append((data["id"], data))
    return out


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.refs = reuse.collect_decisions(examples())

    def test_every_bundled_step_has_a_valid_decision(self):
        self.assertEqual(len(self.refs), 9 + 5)
        for ref in self.refs:
            self.assertLessEqual(sum(1 for o in ref["options"] if o.get("chosen")), 1)

    def test_parse_quantity_internal_units(self):
        self.assertEqual(reuse.parse_quantity("80 mm"), (8.0, "length"))
        value, kind = reuse.parse_quantity("65 deg")
        self.assertEqual(kind, "angle")
        self.assertAlmostEqual(value, math.radians(65))
        self.assertEqual(reuse.parse_quantity("65°")[1], "angle")
        self.assertEqual(reuse.parse_quantity("4"), (4.0, "count"))
        with self.assertRaises(reuse.ReuseError):
            reuse.parse_quantity("about eight")

    def test_named_fillet_matches_edge_rounding_strongly(self):
        feature = {"name": "Base corner fillet", "kind": "FilletFeature", "key": "f1",
                   "parameters": [{"name": "d12", "unit": "mm", "value": 0.5, "expression": "5 mm"}]}
        matches = reuse.match_feature(feature, self.refs)
        top = matches[0]
        self.assertEqual(top["ref"]["topic"], "edge_rounding")
        self.assertEqual(top["level"], reuse.STRONG)
        self.assertTrue(any("Fillet" in r for r in top["reasons"]))
        self.assertEqual(top["comparison"]["user_value"], "5 mm")
        self.assertEqual(top["comparison"]["nearest_option"], "Break the edge")

    def test_generic_extrude_only_gets_type_level_matches(self):
        feature = {"name": "Extrude1", "kind": "ExtrudeFeature", "parameters": []}
        matches = reuse.match_feature(feature, self.refs, limit=50)
        self.assertTrue(matches)
        self.assertTrue(all(m["level"] == reuse.TYPE for m in matches))

    def test_tag_in_parameter_name_matches_lip_in_both_examples(self):
        feature = {"name": "Extrude3", "kind": "ExtrudeFeature",
                   "parameters": [{"name": "lip_height", "unit": "mm", "value": 1.2, "expression": "12 mm"}]}
        matches = reuse.match_feature(feature, self.refs)
        lips = [m for m in matches if m["ref"]["topic"] == "retaining_lip"]
        self.assertEqual({m["ref"]["example_id"] for m in lips}, {"phone-stand", "tablet-stand"})
        self.assertEqual(matches[0]["ref"]["topic"], "retaining_lip")

    def test_unrelated_feature_has_no_match(self):
        feature = {"name": "Thread1", "kind": "ThreadFeature", "parameters": []}
        self.assertEqual(reuse.match_feature(feature, self.refs), [])

    def test_angle_comparison_warns_about_reference(self):
        ref = next(r for r in self.refs if r["topic"] == "viewing_angle" and r["example_id"] == "phone-stand")
        comparison = reuse.compare(ref, [{"name": "tilt", "unit": "deg", "value": math.radians(72)}])
        self.assertEqual(comparison["user_value"], "72°")
        self.assertEqual(comparison["nearest_option"], "Upright")
        self.assertTrue(comparison["note"])

    def test_topics_group_both_examples(self):
        topics = {t["topic"]: t for t in reuse.by_topic(self.refs)}
        anti_slip = topics["anti_slip"]["answers"]
        self.assertEqual({a["choice"] for a in anti_slip}, {"Four corner pads", "Full cork sheet"})
        self.assertIn("step_id", anti_slip[0])
        self.assertEqual(len(topics["fit_check"]["answers"]), 1)

    def test_invalid_decisions_rejected_by_package(self):
        data = json.loads((ROOT / "examples" / "tablet_stand.json").read_text(encoding="utf-8"))
        bad = copy.deepcopy(data)
        for option in bad["steps"][0]["decision"]["options"]:
            option["chosen"] = True
        path = ROOT / "tests" / "_bad_decision.json"
        try:
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(PackageError):
                open_package(path)
            bad = copy.deepcopy(data)
            bad["steps"][0]["decision"]["parameter"]["value"] = "65 deg"   # kind says length
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(PackageError):
                open_package(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
