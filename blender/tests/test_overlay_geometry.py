"""Pure layout/input tests: no Blender installation required."""
import importlib.util
import sys
from pathlib import Path
import unittest

FILE = Path(__file__).resolve().parents[1] / "excadmple_blender" / "overlay_geometry.py"
spec = importlib.util.spec_from_file_location("excadmple_overlay_geometry", FILE)
geometry = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = geometry
spec.loader.exec_module(geometry)


class SingleViewportOverlayTests(unittest.TestCase):
    def test_single_right_panel_occupies_only_part_of_viewport(self):
        layout = geometry.panel_layout(1280, 780, 1, 3)
        self.assertIsNotNone(layout)
        rect = layout["bounds"]
        self.assertLess(rect.w, 350)
        self.assertGreater(rect.x, 850)
        self.assertLess(rect.y + rect.h, 780)
        self.assertEqual(len(layout["cards"]), 3)

    def test_controls_are_interactive(self):
        layout = geometry.panel_layout(1280, 780, 1, 3)
        for key in ("play_pause", "next", "previous", "close",
                    "progress", "speed_minus", "speed_plus"):
            r = layout["buttons"][key]
            hit = geometry.hit_test(layout, r.x + r.w / 2, r.y + r.h / 2)
            self.assertEqual(hit, key)

    def test_specific_step_cards_hit_test(self):
        layout = geometry.panel_layout(1280, 780, 3, 7)
        self.assertEqual(len(layout["cards"]), 4)
        for idx, r in layout["cards"]:
            self.assertEqual(geometry.hit_test(layout, r.x+25,r.y+26),
                             "step:"+str(idx))

    def test_any_click_outside_panel_passes_to_blender(self):
        layout = geometry.panel_layout(1280, 780, 2, 5)
        self.assertIsNone(geometry.hit_test(layout, 350, 400))
        self.assertIsNone(geometry.hit_test(layout, 10, 10))
        self.assertEqual(geometry.hit_test(layout, layout["bounds"].x+8,
                                           layout["bounds"].y+9), "panel")

    def test_small_window_suppresses_unusable_overlay(self):
        self.assertIsNone(geometry.panel_layout(390,780,1,3))
        self.assertIsNone(geometry.panel_layout(1200,330,1,3))

    def test_short_and_medium_viewports_never_overlap_speed_and_rationale(self):
        for height in range(435, 781, 5):
            for step_count in (1, 3, 20):
                with self.subTest(height=height, steps=step_count):
                    layout=geometry.panel_layout(1000, height, step_count-1, step_count)
                    self.assertIsNotNone(layout)
                    speed=layout["buttons"]["speed_minus"]
                    safe_top=speed.y + speed.h + 12
                    self.assertGreaterEqual(layout["why"].y, safe_top)
                    transcript=layout["transcript"]
                    if transcript is not None:
                        self.assertGreaterEqual(transcript.y, safe_top)
                        self.assertLessEqual(
                            transcript.y+transcript.h, layout["why"].y)
                    for index, card in layout["cards"]:
                        self.assertGreaterEqual(card.y, layout["why"].y+layout["why"].h)

    def test_nearby_step_window_clamped(self):
        first = geometry.panel_layout(1400,700,0,20)
        self.assertEqual(first["cards"][0][0],0)
        last = geometry.panel_layout(1400,700,19,20)
        self.assertEqual(last["cards"][-1][0],19)

if __name__ == "__main__":
    unittest.main()
