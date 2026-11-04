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
assert result["objects"]==3,result
assert result["audio_tracks"]==3,result
col=plugin.get_reference(scene)
base=col.objects.get("exCADmple | 01 Base extrude")
back=col.objects.get("exCADmple | 02 Angled back support")
lip=col.objects.get("exCADmple | 03 Front lip extrude")
assert base and back and lip
scene.frame_set(1)
start=base.scale.z
scene.frame_set(119)
assert base.scale.z>start*5,(start,base.scale.z)
scene.frame_set(121)
start=back.scale.z
scene.frame_set(200)
assert back.scale.z>start*5,(start,back.scale.z)
scene.frame_set(241)
start=lip.scale.z
scene.frame_set(360)
assert lip.scale.z>start*5,(start,lip.scale.z)
assert (tuple(original.location),len(original.data.vertices))==snapshot
assert original.display_type=="TEXTURED"
assert scene.frame_end==360
assert "EXTRUDE" in step_at_frame(data,300)["tool"]
assert caption_at_frame(data["steps"][0],90)
assert pointer_at_frame(data["steps"][2],320)[0]>0
scene.excadmple_focus=True
scene.frame_set(300)
plugin._session["step_id"]=None
plugin.update_focus(scene)
assert lip.display_type=="TEXTURED"
assert base.display_type=="WIRE"
assert original.display_type=="TEXTURED"
# Pack generated WAV audio in the scene so the .blend artifact is portable.
bpy.ops.file.pack_all()
packed=sum(1 for sound in bpy.data.sounds if sound.packed_file is not None)
assert packed>=3,("Expected three packed narration WAV files",packed)
destination=Path("/tmp/excadmple_blender_smoke.blend")
bpy.ops.wm.save_as_mainfile(filepath=str(destination))
assert destination.exists() and destination.stat().st_size>10000
print("EXCADMPLE BLENDER TEST PASSED",result,str(destination),destination.stat().st_size)
plugin.unregister()
