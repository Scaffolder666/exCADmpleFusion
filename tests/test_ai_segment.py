"""Authoring tool: recorder log, step proposal (rule-based and Claude), annotation."""
import json
import tempfile
import types
import unittest
from pathlib import Path

from core import ai_segment
from core.ai_segment import SegmentError, heuristic_steps, validate_steps, to_annotation
from core.session_log import SessionLog, tools_between, pointer_between
from core.authoring import build_manifest

FEATURES = [{"index": 0, "name": "Sketch1", "kind": "Sketch"},
            {"index": 1, "name": "Extrude1", "kind": "ExtrudeFeature"},
            {"index": 2, "name": "Fillet1", "kind": "FilletFeature"},
            {"index": 3, "name": "Sketch2", "kind": "Sketch"},
            {"index": 4, "name": "Extrude2", "kind": "ExtrudeFeature"}]
SEGMENTS = [{"start_ms": 1000, "end_ms": 4000, "text": "I start with a wide base."},
            {"start_ms": 21000, "end_ms": 24000, "text": "Round the corners a bit."},
            {"start_ms": 31000, "end_ms": 36000, "text": "Now a small lip at the front."}]
SESSION = {"format": "excadmple-session", "duration_ms": 40000,
           "commands": [{"t_ms": 500, "id": "SketchCreate", "name": "Create Sketch"},
                        {"t_ms": 9000, "id": "Extrude", "name": "Extrude"},
                        {"t_ms": 9500, "id": "OrbitCommand", "name": "Orbit"},
                        {"t_ms": 20000, "id": "FusionFilletEdgeCommand", "name": "Fillet"},
                        {"t_ms": 30000, "id": "Extrude", "name": "Extrude"}],
           "features": [{"t_ms": 6000, "index": 0, "name": "Sketch1", "kind": "Sketch"},
                        {"t_ms": 12000, "index": 1, "name": "Extrude1", "kind": "ExtrudeFeature"},
                        {"t_ms": 25000, "index": 2, "name": "Fillet1", "kind": "FilletFeature"},
                        {"t_ms": 32000, "index": 3, "name": "Sketch2", "kind": "Sketch"},
                        {"t_ms": 35000, "index": 4, "name": "Extrude2", "kind": "ExtrudeFeature"}],
           "selections": [{"t_ms": 21000, "xyz": [1, 0, 0.7], "kind": "edge"}]}


class SessionLogTests(unittest.TestCase):
    def test_log_records_new_features_tools_and_selections(self):
        clock = iter([0.0, 1.0, 2.5, 4.0, 5.0, 6.0]).__next__
        log = SessionLog(clock=clock)
        log.baseline([(0, "Body", "BaseFeature")])
        log.command("Extrude", "Extrude")                         # t = 1000
        log.timeline([(0, "Body", "BaseFeature"), (1, "Extrude1", "ExtrudeFeature")])   # 2500
        log.selection((1, 2, 3), "face")                          # 4000
        data = log.to_dict()
        self.assertEqual(data["commands"], [{"t_ms": 1000, "id": "Extrude", "name": "Extrude"}])
        self.assertEqual(data["features"], [{"t_ms": 2500, "index": 1, "name": "Extrude1", "kind": "ExtrudeFeature"}])
        self.assertEqual(data["selections"][0]["xyz"], [1, 2, 3])

    def test_tools_and_pointer_per_window(self):
        self.assertEqual(tools_between(SESSION, 0, 15000), ["Create Sketch", "Extrude"])   # Orbit ignored
        self.assertEqual(pointer_between(SESSION, 18000, 29000), [{"at_ms": 3000, "xyz": [1, 0, 0.7], "event": "click"}])


class SegmentTests(unittest.TestCase):
    def test_rule_based_split_follows_logged_feature_times(self):
        steps = validate_steps(heuristic_steps(FEATURES, SESSION, SEGMENTS, 40000), FEATURES, 40000)
        self.assertEqual([s["features"] for s in steps], [["Sketch1", "Extrude1"], ["Fillet1"], ["Sketch2", "Extrude2"]])
        self.assertEqual([(s["start_ms"], s["end_ms"]) for s in steps], [(0, 13500), (13500, 26500), (26500, 40000)])
        self.assertEqual(steps[0]["title"], "I start with a wide base")
        self.assertEqual(steps[1]["title"], "Round the corners a bit")

    def test_rule_based_split_without_a_log_spreads_steps_evenly(self):
        steps = heuristic_steps(FEATURES, None, [], 30000)
        self.assertEqual([(s["start_ms"], s["end_ms"]) for s in steps], [(0, 10000), (10000, 20000), (20000, 30000)])
        self.assertEqual(steps[1]["title"], "Fillet1")

    def test_validation_rejects_bad_proposals(self):
        good = [{"title": "Base", "features": ["Sketch1", "Extrude1", "Fillet1"], "start_ms": 0, "end_ms": 26000},
                {"title": "Lip", "features": ["Sketch2", "Extrude2"], "start_ms": 26000, "end_ms": 40000}]
        self.assertEqual(len(validate_steps(good, FEATURES, 40000)), 2)
        cases = {
            "Unknown": [dict(good[0], features=["Sketch1", "Nope"])] + good[1:],
            "twice": [good[0], dict(good[1], features=["Fillet1", "Extrude2"])],
            "not assigned": [good[0], dict(good[1], features=["Extrude2"])],
            "time range": [good[0], dict(good[1], start_ms=20000)],
            "order": [dict(good[1], start_ms=0, end_ms=10000), dict(good[0], start_ms=10000)],
        }
        for message, steps in cases.items():
            with self.assertRaisesRegex(SegmentError, message):
                validate_steps(steps, FEATURES, 40000)

    def test_claude_request_and_parsing(self):
        calls = {}
        answer = {"steps": [{"title": "Wide base", "features": ["Sketch1", "Extrude1", "Fillet1"],
                             "start_ms": 0, "end_ms": 26000},
                            {"title": "Front lip", "features": ["Sketch2", "Extrude2"],
                             "start_ms": 26000, "end_ms": 40000}]}

        def create(**kwargs):
            calls.update(kwargs)
            return types.SimpleNamespace(stop_reason="end_turn",
                                         content=[types.SimpleNamespace(type="text", text=json.dumps(answer))])
        client = types.SimpleNamespace(beta=types.SimpleNamespace(messages=types.SimpleNamespace(create=create)))
        steps = validate_steps(ai_segment.propose_with_claude(client, FEATURES, SESSION, SEGMENTS, 40000),
                               FEATURES, 40000)
        self.assertEqual([s["title"] for s in steps], ["Wide base", "Front lip"])
        self.assertEqual(calls["model"], "claude-opus-5-5")
        self.assertEqual(calls["output_config"]["format"]["schema"], ai_segment.SCHEMA)
        self.assertEqual(calls["fallbacks"], "default")
        prompt = calls["messages"][0]["content"]
        self.assertIn("Extrude1 (ExtrudeFeature) appeared at 12000 ms", prompt)
        self.assertIn("Round the corners a bit.", prompt)

        refused = lambda **kw: types.SimpleNamespace(stop_reason="refusal", content=[])
        client.beta.messages.create = refused
        with self.assertRaises(SegmentError):
            ai_segment.propose_with_claude(client, FEATURES, SESSION, SEGMENTS, 40000)


class PipelineTests(unittest.TestCase):
    def test_annotation_feeds_build_package(self):
        steps = heuristic_steps(FEATURES, SESSION, SEGMENTS, 40000)
        annotation = to_annotation(steps, {"id": "stand", "title": "Stand", "video": "session.mp4"}, SESSION)
        self.assertEqual(annotation["steps"][1]["tools"], ["Fillet"])
        self.assertEqual(annotation["steps"][1]["pointer"][0]["event"], "click")
        tri = lambda z: {"vertices": [[0, 0, z], [1, 0, z], [0, 1, z]], "triangles": [[0, 1, 2]]}
        extract = {"format": "excadmple-extract", "version": 1, "source": {"file": "Stand.f3d"},
                   "meshes": {"a": tri(0), "b": tri(0.1), "c": tri(1)},
                   "features": [dict(f, state=s) for f, s in zip(FEATURES, [[], ["a"], ["b"], ["b"], ["b", "c"]])]}
        manifest = build_manifest(extract, annotation, SEGMENTS)
        self.assertEqual([s["title"] for s in manifest["steps"]],
                         ["I start with a wide base", "Round the corners a bit", "Now a small lip at the front"])
        self.assertEqual(manifest["steps"][1]["tools"], ["Fillet"])
        self.assertEqual(manifest["steps"][2]["media"], {"video": "media/session.mp4", "offset_ms": 26500})

    def test_cli_without_ai(self):
        import subprocess, sys
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tri = {"vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "triangles": [[0, 1, 2]]}
            (tmp / "d.extract.json").write_text(json.dumps({"format": "excadmple-extract", "version": 1,
                "meshes": {"a": tri}, "features": [dict(f, state=["a"]) for f in FEATURES]}))
            (tmp / "t.json").write_text(json.dumps(SEGMENTS))
            (tmp / "s.session.json").write_text(json.dumps(SESSION))
            out = subprocess.run([sys.executable, str(root / "tools" / "author.py"), str(tmp / "d.extract.json"),
                                  str(tmp / "t.json"), "--session", str(tmp / "s.session.json"), "--id", "stand",
                                  "--title", "Stand", "--no-ai", "-o", str(tmp / "annotation.json")],
                                 capture_output=True, text=True, check=True).stdout
            self.assertIn("3 steps (rule-based split)", out)
            self.assertEqual(len(json.loads((tmp / "annotation.json").read_text())["steps"]), 3)


if __name__ == "__main__":
    unittest.main()
