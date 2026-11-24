"""Run against REAL Blender Python (not a stubbed Python interpreter).

blender --background --factory-startup --python blender_expert/selftest.py
"""
from pathlib import Path
import sys
import bpy
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import excadmple_blender as expert

scene=bpy.context.scene
original=set(bpy.data.objects.keys())
assert len(expert.SAMPLE)==12
n=expert.build_example(scene)
assert n==12
assert scene.get(expert.LESSON_KEY)
assert len(expert.RUNTIME["models"])==5

# Stage 0 hides all teacher objects until the first confirmation.
expert._rebuild(0,0)
assert all(obj.hide_get() for obj in expert.RUNTIME["models"].values())

expert._rebuild(1,3)
base=expert.RUNTIME["models"]["Base"]
assert not base.hide_get()
assert all(obj.hide_select for obj in expert.RUNTIME["models"].values())
assert abs(base.location.x-7.5)<1.e-6
assert abs(base.dimensions.x-5.6)<.001

expert._rebuild(10,3)
assert base.modifiers.get("expert_bevel") is not None
expert._rebuild(1,3)
assert base.modifiers.get("expert_bevel") is None

# The original scene objects remain as they were.
assert original.issubset(set(bpy.data.objects.keys()))
print("PASS: 12 steps, 5 teacher objects, independent selection, seek and reset")
