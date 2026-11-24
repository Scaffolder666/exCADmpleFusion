"""Run: python -m unittest tests.test_operation_walkthrough -v

Exercises real tutorial parsing, video cut seek offsets, safety validation,
and the authoring helper without importing Autodesk Fusion.
"""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from core.tutorial.packages import PackageError, open_package

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "walkthrough" / "attach_clips.py"
spec = importlib.util.spec_from_file_location("attach_clips", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OperationWalkthroughTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.data = json.loads((ROOT / "examples" / "phone_stand.json").read_text(encoding="utf-8"))
        self.movie = self.folder / "session.mp4"
        self.movie.write_bytes(b"example video bytes")

    def tearDown(self):
        self.tmp.cleanup()

    def tutorial(self, data=None, name="input.json"):
        p=self.folder / name
        p.write_text(json.dumps(data or self.data),encoding="utf-8")
        return p

    def test_real_video_and_walkthrough_moments_are_exposed(self):
        step=self.data["steps"][0]
        step["media"]["video"]="session.mp4"
        step["media"]["video_offset_ms"]=7000
        step["media"]["video_duration_ms"]=4800
        step["media"]["video_focus"]={"x":.3,"y":.5,"scale":1.8}
        step["walkthrough"]=[
            {"at_ms":0,"kind":"tool","title":"Find Sketch"},
            {"at_ms":1800,"kind":"how","title":"Draw profile","video_start_ms":0,"video_end_ms":3000},
            {"at_ms":6300,"kind":"why","title":"Why","description":"Author provided reason."}
        ]
        pkg=open_package(self.tutorial())
        loaded=pkg.player_data()["steps"][0]
        self.assertEqual(loaded["media"]["video_offset_ms"],7000)
        self.assertEqual(loaded["media"]["video_focus"]["scale"],1.8)
        self.assertEqual(loaded["walkthrough"][1]["video_end_ms"],3000)
        self.assertTrue(loaded["media"]["video"].startswith("file:"))
        pkg.close()

    def test_reject_invalid_authored_moments(self):
        self.data["steps"][0]["walkthrough"]=[
            {"at_ms":5000,"kind":"tool"},
            {"at_ms":3000,"kind":"how"}
        ]
        with self.assertRaises(PackageError):
            open_package(self.tutorial())

    def test_reject_video_focus_scale(self):
        self.data["steps"][0]["media"]["video_focus"]={"scale":25}
        with self.assertRaises(PackageError):
            open_package(self.tutorial())

    def test_attach_cuts_without_reencoding_or_overwriting(self):
        source=self.tutorial()
        cuts={"cuts":[{"step_id":"base","video_offset_ms":12500,
            "video_end_ms":19000,"video_focus":{"x":.5,"y":.3,"scale":2},
            "walkthrough":[
                {"at_ms":0,"kind":"tool","title":"Select Sketch"},
                {"at_ms":1700,"kind":"how","title":"Draw outline",
                 "video_start_ms":0,"video_end_ms":4100},
                {"at_ms":6600,"kind":"geometry","title":"Inspect input"}]}]}
        mapping=self.tutorial(cuts,"cuts.json")
        result=self.folder/"output.json"
        count,path=module.attach(source,self.movie,mapping,result)
        self.assertEqual(count,1)
        self.assertEqual(path,result)
        self.assertNotIn("video",self.data["steps"][0].get("media",{}))
        package=open_package(result)
        self.assertEqual(package.player_data()["steps"][0]["media"]["video_offset_ms"],12500)
        self.assertEqual(package.player_data()["steps"][0]["walkthrough"][1]["video_end_ms"],4100)

    def test_reject_cut_beyond_source_segment(self):
        source=self.tutorial()
        cuts={"cuts":[{"step_id":"base","video_offset_ms":3000,"video_end_ms":4000,
            "walkthrough":[{"at_ms":0,"kind":"how","video_start_ms":2000}]}]}
        mapping=self.tutorial(cuts,"cuts.json")
        with self.assertRaises(module.CutError):
            module.attach(source,self.movie,mapping,self.folder/"out.json")


if __name__=="__main__":
    unittest.main()
