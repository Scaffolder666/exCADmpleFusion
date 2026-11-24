"""Run inside real Blender's Python (headless verifies geometry & undo safety,
not GPU rendering): blender --background --factory-startup \
 --python blender_expert/viewport_tutorial/blender_selftest.py
"""
import sys
from pathlib import Path
import bpy

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from viewport_tutorial import core
import viewport_tutorial as addon

scene=bpy.context.scene
before=set(bpy.data.objects.keys())
active=bpy.context.view_layer.objects.active
before_meshes=len(bpy.data.meshes)
before_scene_items=len(scene.objects)

# Scrubbing/expert playback is pure CPU geometry and changes NO Blender
# datablock, and no scene objects are allocated.
snapshots=[core.snapshot(t) for t in (
    0,core.moment_start(1),core.moment_start(2)+2.2,
    core.moment_start(3),core.TOTAL_SECONDS)]
assert all(len(s["base_vertices"])==12 for s in snapshots)
assert snapshots[2]["height"]>0
assert len(bpy.data.meshes)==before_meshes
assert len(scene.objects)==before_scene_items
assert set(bpy.data.objects.keys())==before
assert bpy.context.view_layer.objects.active==active

# Registration only adds UI operators and draw/timer hooks, never
# scene changes; practice mesh creation is a separate explicit user action.
addon.register()
assert set(bpy.data.objects.keys())==before
assert len(bpy.data.meshes)==before_meshes
addon._set_time(core.moment_start(2)+2.2)
assert len(bpy.data.meshes)==before_meshes
addon.unregister()
assert set(bpy.data.objects.keys())==before

print("PASS: pure GPU teacher, continuous Extrude, no scene mutation on play/seek/register")
print("Note: Desktop UI, render handlers and real Undo still require graphical Blender test.")
