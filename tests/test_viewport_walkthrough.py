"""Unit and UI-contract tests for in-viewport CAD demonstrations.

Run with: python -m unittest tests.test_viewport_walkthrough -v
Pure Python: never imports Autodesk Fusion or manipulates CAD geometry.
"""
import json
import unittest
from pathlib import Path

from core.tutorial.viewport_storyboard import storyboard, frame
from core.tutorial.packages import open_package

ROOT = Path(__file__).resolve().parents[1]


class StoryboardTests(unittest.TestCase):
    def test_sketch_and_extrude_each_get_actual_tool_how_and_geometry_phases(self):
        step={"id":"support","title":"Make support","duration_ms":12000,
              "tools":["Sketch","Extrude"],"source_features":[
                  {"kind":"Sketch"},{"kind":"ExtrudeFeature"}],
              "parameters":[{"name":"distance","expression":"25 mm"}]}
        moments=storyboard(step)
        self.assertEqual([m["phase"] for m in moments],
                         ["tool","how","geometry","tool","how","geometry"])
        self.assertEqual([moments[0]["operation"],moments[3]["operation"]],
                         ["Sketch","Extrude"])
        self.assertTrue(all(a["at_ms"]<=b["at_ms"] for a,b in zip(moments,moments[1:])))
        first=frame(step,0,1200,True,[{"label":"Sketch","found":True,"path":["SOLID","CREATE","Sketch"]}])
        self.assertEqual(first["phase"],"how")
        self.assertEqual(first["tool"],"Sketch")
        second=frame(step,0,8500,True,[{"label":"Extrude","found":True,"path":["SOLID","CREATE","Extrude"]}])
        self.assertEqual(second["phase"],"how")
        self.assertEqual(second["tool"],"Extrude")
        self.assertIn("distance  25 mm",second["parameters"])

    def test_no_video_or_unverified_reasoning_fabricated(self):
        step={"id":"s","title":"Sketch","duration_ms":5000,"tools":["Sketch"],
              "cues":[{"at_ms":0,"label":"This is a hypothetical explanation"}],
              "reasoning_source":"simulated"}
        f=frame(step,1,4900,False)
        self.assertEqual(f["reason"],"")
        self.assertFalse(f["has_operation_footage"])
        self.assertEqual(f["source"],"reconstructed")
        self.assertNotIn("why",[m["phase"] for m in storyboard(step)])

    def test_authored_cut_and_reasoning_are_time_aligned(self):
        step={"id":"feature1","title":"Extrude","duration_ms":8000,
              "tools":["Extrude"],"reasoning_source":"recorded",
              "cues":[{"at_ms":2000,"label":"First thought"},
                      {"at_ms":6500,"label":"Maintain clearance"}],
              "media":{"video":"file:///tmp/session.mp4","video_offset_ms":5000,
                       "video_duration_ms":10000},
              "walkthrough":[
                 {"at_ms":0,"kind":"tool","title":"Click Extrude"},
                 {"at_ms":1600,"kind":"how","title":"Set distance",
                  "video_start_ms":2000,"video_end_ms":5400,
                  "video_focus":{"x":.7,"y":.2,"scale":2}},
                 {"at_ms":6000,"kind":"why","title":"Explain tradeoff"}]}
        at_how=frame(step,0,2600,True)
        self.assertEqual(at_how["phase"],"how")
        self.assertEqual(at_how["video_offset_ms"],5000)
        self.assertEqual(at_how["video_start_ms"],2000)
        self.assertEqual(at_how["video_end_ms"],5400)
        self.assertEqual(at_how["video_focus"]["scale"],2)
        self.assertTrue(at_how["show_video"])
        at_tool=frame(step,0,500,True)
        self.assertFalse(at_tool["show_video"])
        at_why=frame(step,0,7000,False)
        self.assertEqual(at_why["phase"],"why")
        self.assertEqual(at_why["reason"],"Maintain clearance")

    def test_controller_only_and_viewport_includes_video(self):
        controller=(ROOT/"ui/reference/index.html").read_text(encoding="utf-8")
        viewport=(ROOT/"ui/viewport_walkthrough/index.html").read_text(encoding="utf-8")
        self.assertIn('id="rail" class="rail" aria-label="Design steps" hidden',controller)
        self.assertIn('id="play"',controller)
        self.assertNotIn('id="walkVideo"',controller)
        self.assertIn('id="video"',viewport)
        self.assertIn('id="reason"',viewport)
        self.assertIn('id="toolFocus"',viewport)
        self.assertIn('id="dragHandle"',viewport)
        presenter=(ROOT/"core/playback/viewport_presenter.py").read_text(encoding="utf-8")
        self.assertIn("palettes.addTransparent",presenter)
        main=(ROOT/"exCADmpleFusion.py").read_text(encoding="utf-8")
        self.assertNotIn("                _create_tool_palette()",main)
        self.assertIn("_create_viewport_walkthrough()",main)

    def test_existing_phone_stand_still_loads(self):
        package=open_package(ROOT/"examples/phone_stand.json")
        self.assertEqual(len(package.data["steps"]),9)
        self.assertTrue(package.player_data()["steps"][0]["has_geometry"])
        package.close()


if __name__ == "__main__":
    unittest.main()
