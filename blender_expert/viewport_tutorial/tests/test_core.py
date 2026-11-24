"""Pure-Python regression tests: no Blender installation is required.

python -m unittest discover -s blender_expert/viewport_tutorial/tests -v

The addon imports Blender; load only its pure core.py for tests.
"""
import importlib.util
import math
import sys
import unittest
from collections import Counter
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "core.py"
spec=importlib.util.spec_from_file_location("excadmple_pure_tutorial",CORE)
core=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=core
spec.loader.exec_module(core)


class GeometryTests(unittest.TestCase):
    def test_rear_strip_is_a_real_face_not_fake_overlay(self):
        vertices,faces=core.practice_base_mesh()
        self.assertEqual(len(vertices),12)
        self.assertEqual(len(faces),10)
        face=[p for p in faces if all(
            math.isclose(vertices[i][2],core.BASE_THICKNESS) and
            vertices[i][1]>=core.REAR_START_Y for i in p)]
        self.assertEqual(len(face),1)
        self.assertTrue(all(vertices[i][1]>=core.REAR_START_Y for i in face[0]))

    def test_base_closed_manifold_and_correct_topology(self):
        vertices,faces=core.practice_base_mesh()
        edges=Counter()
        for quad in faces:
            for a,b in zip(quad,quad[1:]+quad[:1]):
                edges[tuple(sorted((a,b)))]+=1
        self.assertTrue(edges)
        self.assertTrue(all(count==2 for count in edges.values()))
        self.assertEqual(len(core.unique_edges(vertices,faces)),len(edges))

    def test_teacher_footprint_is_offset_and_learner_at_origin(self):
        learner,_=core.practice_base_mesh()
        teacher,_=core.practice_base_mesh(core.OFFSET_X)
        self.assertAlmostEqual(teacher[0][0]-learner[0][0],core.OFFSET_X)
        self.assertTrue(min(x for x,y,z in teacher)>max(x for x,y,z in learner))

    def test_extrude_mesh_contains_only_top_and_side_faces(self):
        vertices,quads=core.extrude_wall_mesh(core.EXTRUDE_DISTANCE)
        self.assertEqual(len(vertices),8)
        self.assertEqual(len(quads),5)
        self.assertAlmostEqual(max(v[2] for v in vertices),
                               core.BASE_THICKNESS+core.EXTRUDE_DISTANCE)
        self.assertEqual(core.extrude_wall_mesh(0),([],[]))
        self.assertEqual(len(core.quads_to_triangles(vertices,quads)),30)


class PlaybackTests(unittest.TestCase):
    def test_all_five_stages_seekable(self):
        self.assertEqual(len(core.PHASES),5)
        self.assertEqual([core.moment_at(core.moment_start(i)).name
                          for i in range(len(core.PHASES))],
                         ["tool","face","extrude","parameter","why"])

    def test_extrusion_grows_continuously_and_can_be_rewound(self):
        start=core.moment_start(2)
        duration=core.PHASES[2][1]
        self.assertEqual(core.extrude_height(start),0)
        h1=core.extrude_height(start+duration*.25)
        h2=core.extrude_height(start+duration*.50)
        h3=core.extrude_height(start+duration*.75)
        self.assertTrue(0<h1<h2<h3<core.EXTRUDE_DISTANCE)
        self.assertAlmostEqual(h2,core.EXTRUDE_DISTANCE*.5)
        self.assertEqual(core.extrude_height(core.moment_start(3)),
                         core.EXTRUDE_DISTANCE)
        self.assertEqual(core.extrude_height(start),0)
        self.assertEqual(core.extrude_height(core.TOTAL_SECONDS),
                         core.EXTRUDE_DISTANCE)

    def test_snapshot_is_deterministic_and_no_scene_mutation(self):
        a=core.snapshot(6.25)
        b=core.snapshot(6.25)
        self.assertEqual(a,b)
        self.assertGreater(a["height"],0)
        self.assertIsInstance(a["wall_vertices"],list)

    def test_reference_face_follows_extruded_top(self):
        for t in (0,core.moment_start(2)+2.2,core.TOTAL_SECONDS):
            snapshot=core.snapshot(t)
            self.assertTrue(all(math.isclose(p[2],
                 core.BASE_THICKNESS+snapshot["height"]+.005)
                 for p in snapshot["face"]))

    def test_clamp_bounds(self):
        self.assertEqual(core.moment_at(-100).index,0)
        self.assertEqual(core.moment_at(1.e10).index,4)
        self.assertEqual(core.extrude_height(-100),0)

    def test_sidebar_contains_only_playback_education_is_viewport_drawn(self):
        code=(CORE.parent/"__init__.py").read_text()
        begin=code.index("class EXCADV_PT_playback")
        end=code.index("CLASSES=",begin)
        panel=code[begin:end]
        self.assertIn("excad_viewport_playback",panel)
        self.assertNotIn("moment.title",panel)
        self.assertNotIn("moment.hint",panel)
        # Strict contract: the N-panel is an actual playback controller,
        # never a second tutorial. Every operator must be a transport
        # control; every property must be speed or seek.
        import re
        operator_ids=re.findall(r'\.operator\("([^"]+)"',panel)
        self.assertTrue(operator_ids)
        self.assertEqual(set(operator_ids),{"view3d.excad_viewport_playback"})
        prop_ids=re.findall(r'\.prop\(context\.window_manager,"([^"]+)"',panel)
        self.assertEqual(set(prop_ids),{"excad_viewport_time","excad_viewport_speed"})
        self.assertNotIn("l.label(",panel)
        self.assertNotIn("row.label(",panel)
        self.assertNotIn("blf.",panel)
        self.assertNotIn("bpy.data",panel)
        # All instruction must instead live inside POST_PIXEL drawings
        # anchored to the 3D source geometry.
        viewport=code[code.index("def _draw_reference_2d("):code.index("def _redraw(")]
        for source in ("moment.title","moment.hint",
                       'moment.name=="tool"','moment.name=="face"',
                       'moment.name=="extrude"','moment.name=="parameter"',
                       'moment.name=="why"'):
            self.assertIn(source,viewport)
        self.assertIn("POST_VIEW",code)
        self.assertIn("POST_PIXEL",code)
        self.assertIn("bpy.data.objects.new",code)  # explicit learner action only
        draw_region=code[code.index("def _draw_reference_3d("):code.index("class EXCADV_OT_create_practice")]
        self.assertNotIn("bpy.data.objects.new",draw_region)
        self.assertNotIn("bpy.ops.",draw_region)


if __name__=="__main__":
    unittest.main()
