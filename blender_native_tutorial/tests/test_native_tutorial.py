"""Run: python -m unittest discover -s tests -v"""
import ast
import importlib.util
import copy
import json
import math
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load_pure(name):
    path=ROOT/'src/native_tutorial'/(name+'.py')
    spec=importlib.util.spec_from_file_location('pure_'+name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module

engine=load_pure('engine')
starter=load_pure('starter')


class AuthoredNativeTutorialTests(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads((ROOT/'src/native_tutorial/lesson.json').read_text())

    def test_blender_builtin_operators_explicit(self):
        valid=engine.validate_spec(self.spec)
        self.assertEqual(len(valid['steps']),4)
        ops=[step['operator'] for step in valid['steps']]
        self.assertEqual(ops,[
            'mesh.extrude_region_move','mesh.bevel','mesh.inset','mesh.extrude_region_move'])
        self.assertTrue(all(s.get('why_source')=='authored-example' for s in valid['steps']))

    def test_disallow_arbitrary_native_code_and_unsupported_commands(self):
        data=copy.deepcopy(self.spec)
        data['steps'][0]['operator']='wm.open_mainfile'
        with self.assertRaises(ValueError):engine.validate_spec(data)
        data=copy.deepcopy(self.spec)
        data['steps'][0]['args']={'__import__':'os'}
        with self.assertRaises(ValueError):engine.validate_spec(data)
        data=copy.deepcopy(self.spec)
        data['steps'][0]['select']='execute_python'
        with self.assertRaises(ValueError):engine.validate_spec(data)

    def test_reject_malformed_schema_and_unverified_design_rationale(self):
        d=copy.deepcopy(self.spec)
        d['steps'][0]['why_source']='AI-inferred-from-geometry'
        with self.assertRaises(ValueError):engine.validate_spec(d)
        d=copy.deepcopy(self.spec)
        d['steps'].append(d['steps'][0])
        with self.assertRaises(ValueError):engine.validate_spec(d)
        d=copy.deepcopy(self.spec)
        d['steps'][0]['duration']=-12
        with self.assertRaises(ValueError):engine.validate_spec(d)
        d=copy.deepcopy(self.spec)
        d['steps'][0]['args']={'distance':float('nan')}
        with self.assertRaises(ValueError):engine.validate_spec(d)

    def test_practice_mesh_is_watertight_and_has_selectable_rear_face(self):
        vertices,faces=starter.practice_mesh()
        self.assertEqual(len(vertices),12)
        self.assertEqual(len(faces),10)
        counts=Counter()
        for f in faces:
            for a,b in zip(f,f[1:]+f[:1]):counts[tuple(sorted((a,b)))]+=1
        self.assertTrue(all(n==2 for n in counts.values()))
        rear_top=[f for f in faces if all(abs(vertices[i][2]-starter.THICKNESS)<1e-5
                       and vertices[i][1]>=starter.REAR_Y-1e-5 for i in f)]
        self.assertEqual(len(rear_top),1)

    def test_gpu_geometry_reconstructed_from_compiled_operator_snapshots(self):
        frame={'vertices':[[0,0,0],[1,0,0],[1,1,0],[0,1,0]],
               'faces':[[0,1,2,3]],'selected_faces':[0],
               'triangles':[[0,1,2],[0,2,3]],'triangle_faces':[0,0],
               'selected_edges':[[0,1]],'target':[.5,.5,0]}
        regular,highlight,edges=engine.triangles(frame)
        self.assertEqual(len(regular),0)
        self.assertEqual(len(highlight),6)
        self.assertEqual(len(edges),8)
        self.assertEqual(engine.selected_centroid(frame),[.5,.5,0])

    def test_native_compiler_actually_calls_bpy_ops(self):
        src=(ROOT/'src/native_tutorial/native_compiler.py').read_text()
        tree=ast.parse(src)
        ops=['mesh.extrude_region_move','mesh.bevel','mesh.inset',
             'transform.translate','transform.rotate','transform.resize','mesh.subdivide']
        for op in ops:self.assertIn('bpy.ops.'+op,src)
        self.assertIn('bpy.ops.object.mode_set',src)
        self.assertIn('bmesh.from_edit_mesh',src)
        self.assertNotIn('eval(',src)
        self.assertNotIn('exec(',src)

    def test_compiled_timeline_seeking_across_steps_and_phases(self):
        f={'vertices':[[0,0,0],[1,0,0],[0,1,0]],
           'faces':[[0,1,2]],'selected_faces':[0]}
        compiled={'format':engine.COMPILED_FORMAT,'steps':[
            dict(s,frames=[copy.deepcopy(f) for _ in range(5)]) for s in self.spec['steps']]}
        engine.validate_compiled(compiled)
        self.assertGreater(engine.total_seconds(compiled),40)
        at=engine.position(compiled,.01)
        self.assertEqual(at['stage'],'TOOL')
        self.assertEqual(at['sample'],0)
        at=engine.position(compiled,6.5)
        self.assertEqual(at['stage'],'OPERATE')
        self.assertGreater(at['sample'],0)
        at=engine.position(compiled,engine.total_seconds(compiled))
        self.assertEqual(at['stage'],'WHY')
        self.assertEqual(at['index'],len(self.spec['steps'])-1)
        self.assertEqual(at['sample'],4)
        p=engine.position(compiled,engine.step_start(compiled,2))
        self.assertEqual(p['step']['operator'],'mesh.inset')

    def test_sidebar_contains_controls_only_and_all_didactic_material_in_viewport(self):
        source=(ROOT/'src/native_tutorial/__init__.py').read_text()
        tree=ast.parse(source)
        panel=source.split('class EXCAD_PT_player(',1)[1].split('\nCLASSES=',1)[0]
        self.assertNotIn('step.get(',panel)
        self.assertNotIn('stage',panel)
        self.assertNotIn('why_source',panel)
        self.assertIn('EXCAD_OT_transport',panel)
        self.assertIn('excadmple_scrub',panel)
        self.assertIn('excadmple_speed',panel)
        draw=source.split('def _draw_2d():',1)[1].split('\ndef _start_in_context',1)[0]
        for word in ('TOOL','SELECT','OPERATE','PARAMETER','WHY'):
            self.assertIn(word,draw)
        self.assertIn("'POST_VIEW'",source)
        self.assertIn("'POST_PIXEL'",source)
        self.assertIn('subprocess.Popen',source)
        self.assertIn('--background',source)
        self.assertNotIn('bpy.ops.mesh.',draw)
        self.assertNotIn('bpy.data.objects.new',draw)


if __name__=='__main__':unittest.main()
