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

    def test_world_ghost_pointer_follows_preset_geometry(self):
        step=self.data["steps"][0]
        self.assertEqual(m.pointer_world_at_frame(step,step["start"]),
                         tuple(step["pointer_world"][0]["xyz"]))
        midway=m.pointer_world_at_frame(step,step["start"]+32)
        a=step["pointer_world"][1]["xyz"]
        b=step["pointer_world"][2]["xyz"]
        self.assertAlmostEqual(midway[0],(a[0]+b[0])/2)
        self.assertAlmostEqual(midway[1],(a[1]+b[1])/2)
        self.assertEqual(m.pointer_world_at_frame(step,step["end"]),
                         tuple(step["pointer_world"][-1]["xyz"]))
        self.assertEqual(step["pointer_world"][2]["event"],"click")
        self.assertEqual(step["pointer_world"][3]["event"],"drag")

    def test_ghost_world_pointer_is_optional_and_validated(self):
        from copy import deepcopy
        example=deepcopy(self.data)
        example["steps"][0].pop("pointer_world")
        m.validate_example(example)
        self.assertIsNone(m.pointer_world_at_frame(example["steps"][0],70))
        bad=deepcopy(self.data)
        bad["steps"][0]["pointer_world"][0]["xyz"][0]=float("nan")
        with self.assertRaises(m.ExampleError):
            m.validate_example(bad)
        bad=deepcopy(self.data)
        bad["steps"][0]["pointer_world"][2]["event"]="mouse_takeover"
        with self.assertRaises(m.ExampleError):
            m.validate_example(bad)

    def test_captions_and_progress(self):
        first=self.data["steps"][0]
        self.assertIn("footprint",m.caption_at_frame(first,1))
        self.assertIn("extrude",m.caption_at_frame(first,61))
        self.assertAlmostEqual(m.progress_in_step(first,120),1)

    def test_reject_outside_cursor(self):
        d=json.loads(json.dumps(self.data))
        d["steps"][0]["pointer"][1]["x"]=2
        with self.assertRaises(m.ExampleError): m.validate_example(d)

    def test_him_style_extrude_operation_phases(self):
        first=self.data["steps"][0]
        self.assertEqual(m.operation_phase(first,1),"SKETCH PROFILE")
        self.assertEqual(m.operation_phase(first,23),"EXTRUDE TOOL")
        self.assertEqual(m.operation_phase(first,80),"DRAG EXTRUDE HANDLE")
        self.assertEqual(m.operation_phase(self.data["steps"][1],150),"ROTATE / EXTRUDE")

    def test_extrude_data_validation_and_geometry_parameters(self):
        for idx in (0,2):
            item=m.validate_extrude_animation(self.data["steps"][idx]["animation"])
            self.assertEqual(len(item["profile_xy"]),4)
            self.assertGreater(item["distance"],0)
        bad=json.loads(json.dumps(self.data))
        bad["steps"][0]["animation"]["distance"]=-3
        with self.assertRaises(m.ExampleError): m.validate_example(bad)
        bad=json.loads(json.dumps(self.data))
        bad["steps"][0]["animation"]["profile_xy"]=[[0,0],[1,0],[2,0]]
        with self.assertRaises(m.ExampleError): m.validate_example(bad)

    def test_reject_unsupported_geometry(self):
        d=json.loads(json.dumps(self.data))
        d["geometry_preset"]="unknown"
        with self.assertRaises(m.ExampleError): m.validate_example(d)

if __name__=="__main__": unittest.main()
