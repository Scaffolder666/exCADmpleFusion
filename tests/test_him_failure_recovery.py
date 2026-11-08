"""Failure injection against the Fusion API stub; not native kernel validation."""
import types
import unittest
from unittest.mock import patch
from tests.test_him_native import build, session_for, Coll, Group, box, param
import adsk.fusion


class RecoveryTests(unittest.TestCase):
    def make_wireframe(self):
        design, entities, groups = build()
        for token in ('body0', 'body1', 'body2'):
            entities[token].edges = Coll([types.SimpleNamespace(geometry=token)])
        entities['fi1'].faces = Coll([types.SimpleNamespace(boundingBox=box())])
        manager = types.SimpleNamespace(get=lambda: types.SimpleNamespace(copy=lambda face: face))
        self.enterContext(patch.object(adsk.fusion, 'TemporaryBRepManager', manager, create=True))
        _, session = session_for(design, dim=True)
        return design, entities, groups, session

    def test_failed_overlay_draw_restores_shading_and_labels_fallback(self):
        design, entities, groups, session = self.make_wireframe()
        with patch.object(Group, 'addBRepBody', side_effect=RuntimeError('GPU draw failed')):
            shown = session.frame(1, 0.4)
        self.assertFalse(shown['wireframe'])
        self.assertIn('could not be drawn', shown['context_fallback'])
        self.assertEqual(entities['body1'].opacity, 1)
        self.assertEqual(entities['body0'].opacity, .2)
        self.assertAlmostEqual(param(entities, 'fi1').value, .2 * (.02 + .98 * .4))
        session.show_overview()
        self.assertTrue(all(not g.isValid for g in groups))
        self.assertEqual(entities['body0'].opacity, .6)
        self.assertEqual(design.timeline.markerPosition, design.timeline.count)

    def test_existing_body_never_highlighted_when_face_copy_fails(self):
        _, entities, _, session = self.make_wireframe()
        adsk.fusion.TemporaryBRepManager.get = lambda: types.SimpleNamespace(copy=lambda face: None)
        shown = session.frame(1, .4)
        self.assertFalse(shown['wireframe'])
        self.assertEqual(session.him.group.bodies, [])
        self.assertEqual(entities['body1'].opacity, 1)
        session.stop()

    def test_overview_does_not_claim_success_when_restore_fails(self):
        design, _, groups, session = self.make_wireframe()
        session.frame(1, .4)
        with patch.object(session.him.journal, 'restore', side_effect=RuntimeError('locked parameter')):
            with self.assertRaisesRegex(RuntimeError, 'locked parameter'):
                session.show_overview()
        self.assertNotEqual(session.current, ('overview',))
        self.assertTrue(all(not g.isValid for g in groups))
        session.show_overview()  # journal retained for a successful retry
        self.assertEqual(len(session.him.journal), 0)
        self.assertEqual(design.timeline.markerPosition, design.timeline.count)

    def test_failed_native_frame_restores_full_timeline(self):
        design, _, groups, session = self.make_wireframe()
        session.frame(1, .4)
        with patch.object(session.him, '_render', side_effect=RuntimeError('kernel error')):
            shown = session.frame(1, .5)
        self.assertEqual(shown['mode'], 'error')
        self.assertIn('kernel error', shown['fallback'])
        self.assertEqual(design.timeline.markerPosition, design.timeline.count)
        self.assertEqual(len(session.him.journal), 0)
        self.assertTrue(all(not g.isValid for g in groups))

    def test_parameter_fallback_cannot_succeed_when_restore_fails(self):
        design, _, groups = build(fillet_minimum=.1)
        _, session = session_for(design)
        session.frame(1, .8)
        with patch.object(session.him.journal, 'restore', side_effect=RuntimeError('locked parameter')):
            shown = session.frame(1, .01)
        self.assertEqual(shown['mode'], 'error')
        self.assertIn('restoration failed', shown['fallback'])
        self.assertTrue(all(not g.isValid for g in groups))
        session.show_overview()
        self.assertEqual(len(session.him.journal), 0)

    def test_stop_restores_the_original_nonfinal_timeline_marker(self):
        design, entities, groups = build()
        design.timeline.markerPosition = 1
        _, session = session_for(design, dim=True)
        session.frame(1, .5)
        self.assertNotEqual(design.timeline.markerPosition, 1)
        session.stop()
        self.assertEqual(design.timeline.markerPosition, 1)
        self.assertEqual(param(entities, 'fi1').value, .2)
        self.assertTrue(all(not g.isValid for g in groups))
