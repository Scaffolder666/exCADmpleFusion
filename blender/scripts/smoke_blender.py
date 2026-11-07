"""Integration smoke test run in a real Blender background process."""
from pathlib import Path
import sys
import bpy
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import excadmple_blender as plugin
from excadmple_blender.core import step_at_frame,caption_at_frame,pointer_at_frame

plugin.register()
scene=bpy.context.scene
# Protect a real pre-existing user mesh while loading and playing references.
mesh=bpy.data.meshes.new("User original mesh")
mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
original=bpy.data.objects.new("USER - Independent geometry",mesh)
scene.collection.objects.link(original)
original.location=(6,0,.4)
snapshot=tuple(original.location),len(original.data.vertices)
path=root/"excadmple_blender"/"demo.json"
data=plugin.load_example(path)
result=plugin.build_demo(scene,data,path.parent)
assert result["objects"]==16,result
assert result["audio_tracks"]==9,result
col=plugin.get_reference(scene)
base=col.objects.get("exCADmple | 01 Base extrude")
back=col.objects.get("exCADmple | 02 Angled back support")
lip=col.objects.get("exCADmple | 03 Front lip extrude")
assert base and back and lip
assert all(o.hide_select for o in col.objects), "References must be unselectable"
# HiM-inspired Extrude: vertex positions change, not the object's scale.
base_key=base.data.shape_keys.key_blocks["Extrude"]
lip_key=lip.data.shape_keys.key_blocks["Extrude"]
base_sketch=col.objects.get("exCADmple | 01 Base extrude — sketch")
base_gizmo=col.objects.get("exCADmple | 01 Base extrude — manipulator")
lip_sketch=col.objects.get("exCADmple | 03 Front lip extrude — sketch")
lip_gizmo=col.objects.get("exCADmple | 03 Front lip extrude — manipulator")
assert all((base_sketch,base_gizmo,lip_sketch,lip_gizmo))
assert len(col.objects)==16,len(col.objects)
scene.frame_set(1)
start=base_key.value
assert abs(start)<.01,start
scene.frame_set(20)
assert base_sketch.data.bevel_factor_end>.5
assert base_key.value<.02
scene.frame_set(82)
assert base_key.value>.05,base_key.value
assert tuple(base.scale)==(1.,1.,1.),tuple(base.scale)
scene.frame_set(120)
assert base_key.value>.99,base_key.value
depsgraph=bpy.context.evaluated_depsgraph_get()
eval_base=base.evaluated_get(depsgraph)
evaluated_mesh=eval_base.to_mesh()
assert max(v.co.z for v in evaluated_mesh.vertices)>.25
eval_base.to_mesh_clear()
scene.frame_set(121)
start=back.scale.z
scene.frame_set(200)
assert back.scale.z>start*5,(start,back.scale.z)
scene.frame_set(241)
assert lip_key.value<.02,lip_key.value
scene.frame_set(300)
assert lip_key.value>.05,lip_key.value
scene.frame_set(360)
assert lip_key.value>.99,lip_key.value
assert tuple(lip.scale)==(1.,1.,1.)
assert (tuple(original.location),len(original.data.vertices))==snapshot
assert original.display_type=="TEXTURED"
assert scene.frame_end==1080
assert "EXTRUDE" in step_at_frame(data,300)["tool"]
assert caption_at_frame(data["steps"][0],90)
assert pointer_at_frame(data["steps"][2],320)[0]>0
scene.excadmple_focus=True
scene.frame_set(300)
plugin._session["step_id"]=None
plugin.update_focus(scene)
assert lip.display_type=="TEXTURED"
assert base.display_type=="TEXTURED"  # completed geometry remains visible
assert original.display_type=="TEXTURED"
assert lip_sketch.hide_get() is False
assert base_sketch.hide_get() is True
# All 9 steps contribute to ONE cumulative reference design, not an
# unrelated command gallery. Test actual evaluated animation/modifiers.
assert len(data["steps"])==9,len(data["steps"])
assert [s["id"] for s in data["steps"]]==[
    "base","support","lip","base_round","cable","ribs",
    "pads","back_window","fit",
]
scene.frame_set(480)
bevel=next(m for m in base.modifiers if m.type=="BEVEL")
assert bevel.width>.10,bevel.width
assert lip.hide_get() is False and back.hide_get() is False
scene.frame_set(600)
lip_bool=next(m for m in lip.modifiers if m.type=="BOOLEAN")
assert lip_bool.object is not None
assert abs(lip_bool.object.location.y+.94)<.01
assert base.hide_get() is False and lip.hide_get() is False
scene.frame_set(720)
ribs=[o for o in col.objects if o.name.startswith("exCADmple | 06 Support rib")]
assert len(ribs)==2,len(ribs)
assert all(o.hide_get() is False for o in ribs)
assert all(o.data.shape_keys.key_blocks["Gusset height"].value>.99 for o in ribs)
scene.frame_set(840)
pads=[o for o in col.objects if o.name.startswith("exCADmple | 07 Grip pad")]
assert len(pads)==4,len(pads)
assert all(o.scale.x>.19 and o.hide_get() is False for o in pads)
scene.frame_set(960)
back_bool=next(m for m in back.modifiers if m.type=="BOOLEAN")
assert back_bool.object is not None
assert abs(back_bool.object.location.x+2.8)<.01
scene.frame_set(1080)
phone=col.objects.get("exCADmple | 09 Device fit proxy")
assert phone is not None and phone.hide_get() is False
assert abs(phone.location.y-.45)<.01
assert back.hide_get() is False and base.hide_get() is False
scene.frame_set(600)
assert phone.hide_get() is True
assert (tuple(original.location),len(original.data.vertices))==snapshot

# Reload the same preset into the same working Scene. This is the
# prerequisite for later switching between several curated examples.
# The learner's geometry survives and the prior reference is replaced.
reloaded=plugin.build_demo(scene,data,path.parent)
assert reloaded["audio_tracks"]==9,reloaded
col=plugin.get_reference(scene)
assert col is not None and len(col.objects)==16
assert sum(1 for c in scene.collection.children if c.get('excadmple_reference_collection'))==1
assert all(o.hide_select for o in col.objects)
assert (tuple(original.location),len(original.data.vertices))==snapshot
assert original.name in scene.objects
sound_strips=[
    strip for strip in scene.sequence_editor.strips
    if strip.name.startswith("exCADmple voice:")
]
assert len(sound_strips)==9, ("Narration duplicated during reload",len(sound_strips))

# Pack generated WAV audio in the scene so the .blend artifact is portable.
bpy.ops.file.pack_all()
packed=sum(1 for sound in bpy.data.sounds if sound.packed_file is not None)
assert packed>=9,("Expected nine packed narration WAV files",packed)
destination=Path("/tmp/excadmple_blender_smoke.blend")
bpy.ops.wm.save_as_mainfile(filepath=str(destination))
assert destination.exists() and destination.stat().st_size>10000
print("EXCADMPLE BLENDER TEST PASSED",result,str(destination),destination.stat().st_size)

# Scene isolation: avoid deleting a reference collection in another Scene.
second=bpy.data.scenes.new("Unrelated user Scene")
second_ref=bpy.data.collections.new(plugin.REF_NAME)
second_ref["excadmple_reference_collection"]=True
second.collection.children.link(second_ref)
other_obj=bpy.data.objects.new("USER Scene B test reference",mesh)
second_ref.objects.link(other_obj)
assert plugin.get_reference(scene)==col
assert plugin.get_reference(second)==second_ref
plugin.unlink_reference(scene)
assert plugin.get_reference(scene) is None
assert plugin.get_reference(second)==second_ref
assert other_obj.name in second_ref.objects
assert original.name in scene.objects
plugin.unregister()
