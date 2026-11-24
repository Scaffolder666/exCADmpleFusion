"""Pure-Python tests for the non-invasive Fusion virtual expert event bridge."""
import importlib.util
import json
import pathlib
import tempfile
import unittest

FILE = pathlib.Path(__file__).resolve().parents[2] / "core" / "playback" / "virtual_expert.py"
spec = importlib.util.spec_from_file_location("virtual_expert", FILE)
expert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(expert)


class ExpertTests(unittest.TestCase):
    def test_progress_phases(self):
        self.assertEqual(
            [expert.semantic_phase(i) for i in [0, .24, .25, .50, .75, 1]],
            [0, 0, 1, 2, 3, 3])

    def test_reference_event_is_pure_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "event.json"
            sender = expert.VirtualExpert(output=path)
            step = {"id":"extrude1", "title":"Extrude support",
                    "tools":["Extrude"],
                    "source_features":[{"parameters":[
                        {"name":"distance","expression":"25 mm"}]}],
                    "cues":[{"at_ms":0,"label":"Support the phone at the proper height."}]}
            sender.set_step(0,step)
            self.assertTrue(path.exists())
            sender.frame(0,step,.85)
            data = json.loads(path.read_text())
            # Frames are throttled, so publish a deterministic final frame:
            sender.publish(.85,True,force=True)
            data = json.loads(path.read_text())
            self.assertEqual(data["phase"],3)
            self.assertEqual(data["tool"],"Extrude")
            self.assertIn("distance = 25 mm",data["parameters"])
            self.assertEqual(data["reason"],"Support the phone at the proper height.")
            sender.pause()
            self.assertFalse(json.loads(path.read_text())["playing"])
            sender.close()
            self.assertFalse(path.exists())


if __name__=="__main__":
    unittest.main()
