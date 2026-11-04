"""Pure playback tests run without bpy."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("excadmple_core",ROOT/"excadmple_blender"/"core.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class PlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=m.load_example(ROOT/"excadmple_blender"/"demo.json")

    def test_step_intervals(self):
        self.assertEqual([m.step_at_frame(self.data,f)["id"] for f in (1,120,121,240,241,360)],
                         ["base","base","support","support","lip","lip"])

    def test_cursor_interpolation(self):
        x,y=m.pointer_at_frame(self.data["steps"][0],11)
        self.assertAlmostEqual(x,.165)
        self.assertAlmostEqual(y,.67)

    def test_captions_and_progress(self):
        first=self.data["steps"][0]
        self.assertIn("footprint",m.caption_at_frame(first,1))
        self.assertIn("extrude",m.caption_at_frame(first,61))
        self.assertAlmostEqual(m.progress_in_step(first,120),1)

    def test_reject_outside_cursor(self):
        d=json.loads(json.dumps(self.data))
        d["steps"][0]["pointer"][1]["x"]=2
        with self.assertRaises(m.ExampleError): m.validate_example(d)

    def test_reject_unsupported_geometry(self):
        d=json.loads(json.dumps(self.data))
        d["geometry_preset"]="unknown"
        with self.assertRaises(m.ExampleError): m.validate_example(d)

if __name__=="__main__": unittest.main()
