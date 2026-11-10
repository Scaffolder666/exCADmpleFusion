"""Authoring tool: grouping recorded features and speech into reasoning steps,
and the tutorial it writes (beside or inside the .f3d)."""
import json
import tempfile
import types
import unittest
from pathlib import Path

from core.playback.him_filter import FeatureInfo
from core.tutorial.authoring_draft import Draft, DraftError, TAIL_MS, draft_from_recording
from core.tutorial.example_pair import embedded_chunks, read_embedded, EMBED_GROUP
from core.tutorial.packages import open_package, PackageError

FEATURES = [{"index": 0, "name": "Sketch1", "kind": "Sketch", "t_ms": 6000},
            {"index": 1, "name": "Extrude1", "kind": "ExtrudeFeature", "t_ms": 12000},
            {"index": 2, "name": "Fillet1", "kind": "FilletFeature", "t_ms": 25000},
            {"index": 3, "name": "Sketch2", "kind": "Sketch", "t_ms": 32000},
            {"index": 4, "name": "Extrude2", "kind": "ExtrudeFeature", "t_ms": 35000}]
SEGMENTS = [{"start_ms": 1000, "end_ms": 4000, "text": "I start with a wide base."},
            {"start_ms": 9000, "end_ms": 11000, "text": "One centimetre is enough to be stiff."},
            {"start_ms": 21000, "end_ms": 24000, "text": "Round the corners so it does not cut your hand."},
            {"start_ms": 31000, "end_ms": 36000, "text": "Now a small lip at the front."}]


def draft():
    return Draft(FEATURES, 40000, SEGMENTS)


def ranges(d):
    return [(s["start_ms"], s["end_ms"]) for s in d.view()["steps"]]


def names(d):
    return [[f["name"] for f in s["features"]] for s in d.view()["steps"]]


class GroupingTests(unittest.TestCase):
    def test_sketches_go_with_their_feature_and_speech_with_its_time(self):
        d = draft()
        self.assertEqual(names(d), [["Sketch1", "Extrude1"], ["Fillet1"], ["Sketch2", "Extrude2"]])
        self.assertEqual(ranges(d), [(0, 12000 + TAIL_MS), (13500, 26500), (26500, 40000)])
        steps = d.view()["steps"]
        self.assertEqual(steps[0]["text"], "I start with a wide base. One centimetre is enough to be stiff.")
        self.assertEqual(steps[0]["title"], "I start with a wide base")
        self.assertEqual(steps[1]["sentences"][0]["start_ms"], 21000)

    def test_boundary_never_passes_the_next_feature(self):
        features = [dict(f) for f in FEATURES]
        features[2]["t_ms"] = 12500         # the fillet was made right after the extrude
        d = Draft(features, 40000, SEGMENTS)
        self.assertEqual(ranges(d)[0], (0, 12500))

    def test_features_without_times_share_the_recording(self):
        features = [dict(f, t_ms=None) for f in FEATURES]
        d = Draft(features, 30000)
        self.assertEqual(len(d.steps), 3)
        starts = [s for s, _ in ranges(d)]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(all(e - s >= 500 for s, e in ranges(d)))
        self.assertEqual(ranges(d)[-1][1], 30000)

    def test_untimed_steps_spread_over_the_real_recording(self):
        d = Draft([dict(f, t_ms=None) for f in FEATURES], 0)
        d.set_segments([{"start_ms": 1000, "end_ms": 2000, "text": "a"},
                        {"start_ms": 50000, "end_ms": 59000, "text": "b"}])
        for start, end in ranges(d):                # three equal shares of 59 s
            self.assertAlmostEqual(end - start, 19667, delta=50)
        d.set_duration(90000)
        self.assertAlmostEqual(ranges(d)[0][1], 30000, delta=50)
        d.set_boundary(0, 20000)                     # placed by hand: no more spreading
        d.set_duration(120000)
        self.assertEqual([r[0] for r in ranges(d)][:2], [0, 20000])
        self.assertEqual(ranges(d)[-1][1], 120000)
        self.assertAlmostEqual(ranges(d)[1][1], 60000, delta=100)

    def test_no_features(self):
        with self.assertRaises(DraftError):
            Draft([], 1000)


class RecordingTests(unittest.TestCase):
    def test_times_come_from_the_log_shifted_to_the_voice_recording(self):
        session = {"duration_ms": 41000, "features": [
            {"t_ms": 7000, "index": 0, "name": "Sketch1", "kind": "Sketch"},
            {"t_ms": 13000, "index": 1, "name": "Extrude1", "kind": "ExtrudeFeature"},
            {"t_ms": 14000, "index": 2, "name": "Extrude2", "kind": "ExtrudeFeature"}]}   # undone later
        timeline = [(0, "Base", "BaseFeature"), (1, "Sketch1", "Sketch"), (2, "Extrude1", "ExtrudeFeature")]
        d = draft_from_recording(timeline, session, audio_start_ms=1000)
        self.assertEqual([f["t_ms"] for f in d.features], [None, 6000, 12000])   # matched by name
        self.assertEqual(d.duration_ms, 40000)
        self.assertEqual(names(d), [["Base"], ["Sketch1", "Extrude1"]])
        early = draft_from_recording(timeline, session, audio_start_ms=-2000, audio_duration_ms=50000)
        self.assertEqual([f["t_ms"] for f in early.features], [None, 9000, 15000])
        self.assertEqual(early.duration_ms, 50000)


class EditTests(unittest.TestCase):
    def test_merge_makes_one_reasoning_step_of_several_operations(self):
        d = draft()
        d.merge(0)
        self.assertEqual(names(d), [["Sketch1", "Extrude1", "Fillet1"], ["Sketch2", "Extrude2"]])
        self.assertEqual(ranges(d), [(0, 26500), (26500, 40000)])
        self.assertIn("Round the corners", d.view()["steps"][0]["text"])
        with self.assertRaises(DraftError):
            d.merge(1)

    def test_merge_keeps_the_designers_own_words(self):
        d = draft()
        d.set_text(1, "Rounded for safety.")
        d.merge(0)
        self.assertEqual(d.view()["steps"][0]["text"],
                         "I start with a wide base. One centimetre is enough to be stiff. Rounded for safety.")
        self.assertTrue(d.view()["steps"][0]["text_edited"])

    def test_split_between_two_features(self):
        d = draft()
        d.merge(0)
        d.split(0, 2)
        self.assertEqual(names(d), [["Sketch1", "Extrude1"], ["Fillet1"], ["Sketch2", "Extrude2"]])
        self.assertEqual(ranges(d), [(0, 13500), (13500, 26500), (26500, 40000)])
        for bad in (0, 3, True):
            with self.assertRaises(DraftError):
                d.split(0, bad)

    def test_move_a_sentence_to_the_neighbouring_step(self):
        d = draft()
        d.move_sentence(0, +1)        # "One centimetre ..." belongs to the fillet step
        self.assertEqual(ranges(d)[0], (0, 9000))
        self.assertEqual(d.view()["steps"][1]["sentences"][0]["text"], "One centimetre is enough to be stiff.")
        d.move_sentence(1, -1)        # and back
        self.assertEqual([s["text"] for s in d.sentences(0)],
                         ["I start with a wide base.", "One centimetre is enough to be stiff."])
        with self.assertRaises(DraftError):
            d.move_sentence(0, -1)

    def test_boundaries_keep_steps_apart(self):
        d = draft()
        d.set_boundary(0, 20000)
        self.assertEqual(ranges(d)[:2], [(0, 20000), (20000, 26500)])
        for bad in (100, 26400):
            with self.assertRaises(DraftError):
                d.set_boundary(0, bad)
        with self.assertRaises(DraftError):
            d.set_boundary(2, 39000)

    def test_duration_follows_the_audio_but_keeps_every_step(self):
        d = draft()
        d.set_duration(60000)
        self.assertEqual(ranges(d)[-1], (26500, 60000))
        d.set_duration(1000)
        self.assertEqual(ranges(d)[-1], (26500, 36000))     # the last sentence ends at 36 s

    def test_rename_and_revert_text(self):
        d = draft()
        d.rename(1, "  Safe   edges ")
        d.set_text(1, "Typed")
        self.assertEqual(d.view()["steps"][1]["title"], "Safe edges")
        d.set_text(1, None)
        self.assertEqual(d.view()["steps"][1]["text"], "Round the corners so it does not cut your hand.")
        d.rename(1, "")
        self.assertEqual(d.view()["steps"][1]["title"], "Round the corners so it does not cut your hand")

    def test_new_transcript_keeps_the_grouping(self):
        d = draft()
        d.merge(1)
        d.set_segments([{"start_ms": 30000, "end_ms": 45000, "text": "Later words."}])
        self.assertEqual(names(d), [["Sketch1", "Extrude1"], ["Fillet1", "Sketch2", "Extrude2"]])
        self.assertEqual(ranges(d)[-1][1], 45000)
        with self.assertRaises(DraftError):
            d.set_segments([{"start_ms": 5, "text": "b"}, {"start_ms": 1, "text": "a"}])


class SaveTests(unittest.TestCase):
    def test_round_trip_and_timeline_check(self):
        d = draft()
        d.merge(0)
        d.rename(0, "Base")
        again = Draft.from_dict(json.loads(json.dumps(d.to_dict())), FEATURES)
        self.assertEqual(again.view(), d.view())
        changed = [dict(f) for f in FEATURES]
        changed[2]["name"] = "Fillet7"
        with self.assertRaises(DraftError):
            Draft.from_dict(d.to_dict(), changed)
        broken = d.to_dict()
        broken["steps"][0]["features"] = [0, 2]
        with self.assertRaises(DraftError):
            Draft.from_dict(broken)

    def test_pair_slices_one_recording(self):
        d = draft()
        d.set_text(1, "Rounded for safety.")
        pair = d.to_pair("Stand.f3d", "Phone stand", audio="Stand.webm")
        first, second, third = pair["steps"]
        self.assertEqual(first["features"][1], {"index": 1, "name": "Extrude1", "kind": "ExtrudeFeature"})
        self.assertEqual((first["audio_offset_ms"], first["duration_ms"], first["audio_slice"]), (0, 13500, True))
        self.assertEqual(first["cues"], [{"at_ms": 1000, "label": "I start with a wide base."},
                                         {"at_ms": 9000, "label": "One centimetre is enough to be stiff."}])
        self.assertEqual((second["transcript"], second["reasoning_source"]), ("Rounded for safety.", "author"))
        self.assertNotIn("cues", second)
        self.assertEqual(third["audio_offset_ms"], 26500)
        self.assertEqual(pair["authoring"]["format"], "excadmple-authoring")


class _Attributes:
    def __init__(self, values):
        self.values = values

    def itemByName(self, group, name):
        value = self.values.get((group, name))
        return None if value is None else types.SimpleNamespace(value=value)


class PlayerReadsTheTutorialTests(unittest.TestCase):
    """The player's side: the same JSON beside the .f3d or inside it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        (self.folder / "Stand.f3d").write_bytes(b"not a real archive")
        (self.folder / "Stand.webm").write_bytes(b"audio")
        self.features = [FeatureInfo(f["index"], f["name"], f["kind"]) for f in FEATURES]
        self.pair = draft().to_pair("Stand.f3d", "Phone stand", audio="Stand.webm")

    def model(self, values):
        return types.SimpleNamespace(design=types.SimpleNamespace(attributes=_Attributes(values)))

    def test_embedded_tutorial_is_read_from_the_imported_design(self):
        text = json.dumps(self.pair)
        values = {(EMBED_GROUP, name): value for name, value in embedded_chunks(text)}
        package = open_package(self.folder / "Stand.f3d")
        self.assertTrue(package.needs_populate)
        steps = package.populate_from_features(self.features, model=self.model(values))
        self.assertEqual(package.data["title"], "Phone stand")
        self.assertEqual([s["title"] for s in steps][0], "I start with a wide base")
        self.assertEqual(steps[2]["media"], {"audio": "Stand.webm", "offset_ms": 26500, "slice": True})
        self.assertEqual(steps[0]["duration_ms"], 13500)
        media = package.player_data()["steps"][0]["media"]
        self.assertEqual((media["offset_ms"], media["slice"]), (0, True))

    def test_long_text_is_split_into_chunks(self):
        text = "x" * 130001
        chunks = embedded_chunks(text)
        self.assertEqual(chunks[0], ("tutorial-count", "3"))
        self.assertEqual("".join(v for _, v in chunks[1:]), text)

    def test_f3d_without_a_tutorial(self):
        package = open_package(self.folder / "Stand.f3d")
        with self.assertRaisesRegex(PackageError, "no exCADmple tutorial inside"):
            package.populate_from_features(self.features, model=self.model({}))
        self.assertIsNone(read_embedded(self.model({}).design))

    def test_incomplete_or_damaged(self):
        with self.assertRaisesRegex(PackageError, "incomplete"):
            read_embedded(self.model({(EMBED_GROUP, "tutorial-count"): "2",
                                      (EMBED_GROUP, "tutorial-0"): "{"}).design)
        with self.assertRaisesRegex(PackageError, "damaged"):
            read_embedded(self.model({(EMBED_GROUP, "tutorial-count"): "1",
                                      (EMBED_GROUP, "tutorial-0"): "{"}).design)

    def test_same_json_beside_the_f3d(self):
        path = self.folder / "Stand.json"
        path.write_text(json.dumps(self.pair), encoding="utf-8")
        package = open_package(path)
        steps = package.populate_from_features(self.features)
        self.assertEqual(len(steps), 3)


if __name__ == "__main__":
    unittest.main()
