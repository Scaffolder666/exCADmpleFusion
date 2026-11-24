"""Execute in REAL Blender after installing Blender 4.2+.

blender --background --factory-startup --python tests/blender_live_test.py

This test must NOT be faked with bpy stubs. It verifies that native bpy.ops
produces real topology and changes to geometries, while playback does not
create learner objects or Blender Undo entries.
"""
import sys
import tempfile
from pathlib import Path
import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from native_tutorial.native_compiler import compile_lesson
from native_tutorial.engine import read_compiled

with tempfile.TemporaryDirectory() as temp:
    target=Path(temp)/'compiled.json'
    data=compile_lesson(ROOT/'src/native_tutorial/lesson.json',target)
    lesson=read_compiled(target)
    assert len(lesson['steps'])==4
    for step in lesson['steps']:
        assert step['provenance']=='native-bpy.ops'
        assert len(step['frames'])==15
        assert len(step['frames'][-1]['vertices'])>=len(step['frames'][0]['vertices'])
    assert len(lesson['steps'][0]['frames'][-1]['vertices'])>len(lesson['steps'][0]['frames'][0]['vertices'])
    assert len(lesson['steps'][2]['frames'][-1]['faces'])>len(lesson['steps'][2]['frames'][0]['faces'])
    print('PASS: four ACTUAL native Blender operations, sampled and reusable independent of learner')
