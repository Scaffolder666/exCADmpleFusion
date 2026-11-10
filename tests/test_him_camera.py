"""Camera math and feature-entry policy, using stubs rather than Fusion Desktop."""
import types
import unittest
from unittest.mock import patch
from core.playback.him_camera import focus_geometry
from tests.test_him_native import build, session_for


def point(x, y, z):
    return types.SimpleNamespace(x=x, y=y, z=z)


class CameraTests(unittest.TestCase):
    def viewport(self, orthographic=True):
        self.extents = []
        def set_extents(w, h):
            self.extents.append((w, h))
            return orthographic
        camera = types.SimpleNamespace(eye=point(10, 20, 30), target=point(0, 0, 0),
                                       setExtents=set_extents)
        return types.SimpleNamespace(camera=camera)

    def test_bounds_center_preserves_view_direction_and_adds_margin(self):
        viewport = self.viewport()
        body = types.SimpleNamespace(boundingBox=types.SimpleNamespace(
            minPoint=point(10, 0, 0), maxPoint=point(14, 2, 2)))
        self.assertTrue(focus_geometry(viewport, [body], point))
        self.assertEqual(vars(viewport.camera.target), dict(x=12, y=1, z=1))
        self.assertEqual(vars(viewport.camera.eye), dict(x=22, y=21, z=31))
        self.assertGreater(self.extents[0][0], 4)
        self.assertTrue(viewport.camera.isSmoothTransition)
        self.assertFalse(viewport.camera.isFitView)

    def test_no_geometry_leaves_camera_untouched(self):
        viewport = self.viewport()
        before = dict(vars(viewport.camera))
        self.assertFalse(focus_geometry(viewport, [], point))
        self.assertEqual(vars(viewport.camera), before)

    def test_perspective_uses_native_sphere_extents(self):
        viewport = self.viewport(False)
        _, entities, _ = build()
        self.assertTrue(focus_geometry(viewport, [entities['body1']], point))
        self.assertGreater(viewport.camera.viewExtents, 0)

    def test_unchecked_frames_never_request_camera_focus(self):
        design, _, _ = build()
        _, session = session_for(design)
        with patch.object(session.him, 'focus_feature') as focus:
            session.frame(0, .2)
            session.frame(0, .4)
            session.frame(1, .3)
            focus.assert_not_called()

    def test_checked_focuses_once_per_feature_not_every_frame(self):
        design, _, _ = build()
        _, session = session_for(design)
        session.him.auto_focus = True
        with patch.object(session.him, 'focus_feature') as focus:
            session.frame(0, .2)
            session.frame(0, .4)
            self.assertEqual(focus.call_count, 1)
            session.frame(1, .3)
            self.assertEqual(focus.call_count, 2)
            session.set_auto_focus(False)
            session.frame(2, .4)
            self.assertEqual(focus.call_count, 2)
