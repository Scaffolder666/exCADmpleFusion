"""Pure data contract tests for the 20-step HiM-inspired reference gallery."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("excadmple_gallery_core",ROOT/"excadmple_blender"/"core.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class GalleryDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=ROOT/"excadmple_blender"/"him_showcase.json"
        cls.example=mod.load_example(cls.path)

    def test_complete_gallery(self):
        steps=self.example["steps"]
        self.assertEqual(len(steps),20)
        self.assertEqual(set(s["operation"]["type"] for s in steps),set(mod.SHOWCASE_OPERATIONS))
        self.assertEqual(len(set(s["id"] for s in steps)),20)

    def test_illustrative_provenance(self):
        self.assertEqual(self.example["geometry_preset"],"him_feature_showcase_v1")
        self.assertTrue(all("Illustrative" in step["reasoning"] for step in self.example["steps"]))

    def test_all_steps_selectable_and_timed(self):
        for s in self.example["steps"]:
            self.assertEqual(mod.step_at_frame(self.example,s["start"])["id"],s["id"])
            self.assertEqual(mod.step_at_frame(self.example,s["end"])["id"],s["id"])
            self.assertTrue(mod.caption_at_frame(s,s["end"]))
            self.assertTrue(0 <= mod.pointer_at_frame(s,s["start"])[0] <= 1)

    def test_unsupported_operation_rejected(self):
        obj=json.loads(json.dumps(self.example))
        obj["steps"][0]["operation"]["type"]="invented_feature"
        with self.assertRaises(mod.ExampleError):
            mod.validate_example(obj)

    def test_missing_extrude_profile_rejected(self):
        obj=json.loads(json.dumps(self.example))
        obj["steps"][0].pop("animation")
        with self.assertRaises(mod.ExampleError):
            mod.validate_example(obj)


if __name__=="__main__":
    unittest.main()
