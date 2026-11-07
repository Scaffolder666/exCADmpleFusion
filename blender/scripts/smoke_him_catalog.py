"""Real Blender 4.5 integration for a 20-operation animation catalog.

Confirms animated parameters / geometry at the beginning and end of every
demonstration, independent user geometry, step focus and saving to .blend.
"""
import bpy
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import excadmple_blender as app
from excadmple_blender.core import SHOWCASE_OPERATIONS

app.register()
scene=bpy.context.scene

# User content is created before loading the reference and must stay intact.
mesh=bpy.data.meshes.new("Independent User CAD Model")
mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
mesh.update()
user=bpy.data.objects.new("USER OWNED - unaffected by HiM catalog",mesh)
scene.collection.objects.link(user)
user.location=(8,2,.75)
before=(tuple(user.location),tuple(user.scale),len(user.data.vertices),tuple(user.data.vertices[0].co))

data=app.load_example(root/"excadmple_blender"/"him_showcase.json")
assert len(data["steps"])==20
assert set(step["operation"]["type"] for step in data["steps"]) == set(SHOWCASE_OPERATIONS)
stats=app.build_showcase(scene,data)
assert stats["steps"] == 20, stats
col=app.get_reference(scene)
assert len(col.objects) >= 25,len(col.objects)\nassert all(o.hide_select for o in col.objects), "Gallery references must be unselectable"
assert len([obj for obj in bpy.data.objects if obj == user])==1

def step_objects(step):
    return [obj for obj in col.objects if obj.get("excadmple_step")==step["id"]]

def primary(step):
    objects=step_objects(step)
    return next((o for o in objects if not o.get("excadmple_auxiliary")), objects[0])

def eval_verts(obj):
    dg=bpy.context.evaluated_depsgraph_get()
    evaluated=obj.evaluated_get(dg)
    mesh=evaluated.to_mesh()
    try:
        return [tuple(v.co) for v in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()

for step in data["steps"]:
    objects=step_objects(step)
    assert objects,step["id"]
    scene.frame_set(step["start"])
    app._session["step_id"]=None
    app.update_focus(scene)
    focus_names=[o.name for o in objects]
    assert all(o.hide_get() is False for o in objects),(step["id"],focus_names)
    assert all(o.hide_get() is True for o in col.objects if o not in objects)
    one=primary(step)
    begin_vertices=eval_verts(one)
    beginning=(tuple(one.location),tuple(one.scale),len(begin_vertices))
    scene.frame_set(step["end"])
    end_vertices=eval_verts(one)
    ending=(tuple(one.location),tuple(one.scale),len(end_vertices))
    kind=step["operation"]["type"]
    if kind == "extrude":
        shape=one.data.shape_keys.key_blocks["Extrude"]
        assert shape.value > .99,(kind,shape.value)
        assert max(v[2] for v in eval_verts(one))>1
    elif kind == "revolve":
        mod=next(m for m in one.modifiers if m.type=="SCREW")
        assert abs(mod.angle-6.283185307)<.001,mod.angle
        begin_span=max(v[1] for v in begin_vertices)-min(v[1] for v in begin_vertices)
        end_span=max(v[1] for v in end_vertices)-min(v[1] for v in end_vertices)
        assert end_span>begin_span+.5,(kind,begin_span,end_span)
    elif kind in ("fillet","chamfer"):
        mod=next(m for m in one.modifiers if m.type=="BEVEL")
        assert mod.width>.2
        assert len(begin_vertices)==len(end_vertices),(kind,beginning,ending)
        motion=max(
            max(abs(a[k]-b[k]) for k in range(3))
            for a,b in zip(begin_vertices,end_vertices)
        )
        assert motion>.05,(kind,motion)
    elif kind == "shell":
        mod=next(m for m in one.modifiers if m.type=="SOLIDIFY")
        assert mod.thickness >= .19
    elif kind == "hole":
        mod=next(m for m in one.modifiers if m.type=="BOOLEAN")
        assert mod.object is not None
        assert len(eval_verts(one)) > 8
    elif kind in ("draft","loft"):
        assert any(k.value>.99 for k in one.data.shape_keys.key_blocks if k.name != "Basis")
    elif kind in ("sweep","thread"):
        assert one.data.bevel_factor_end>.99
    else:
        moved=any(
            o.animation_data is not None or (o.data and getattr(o.data,"animation_data",None) is not None)
            for o in objects
        )
        assert moved,(kind,"No motion data in feature step")
    print("EXCADMPLE_HIM_OPERATION_OK",kind,len(objects))

after=(tuple(user.location),tuple(user.scale),len(user.data.vertices),tuple(user.data.vertices[0].co))
assert before == after,(before,after)
assert user.hide_get() is False
assert scene.frame_end==data["steps"][-1]["end"]

output=Path("/tmp/excadmple_blender_him_catalog.blend")
bpy.ops.wm.save_as_mainfile(filepath=str(output))
assert output.is_file() and output.stat().st_size>100000
print("EXCADMPLE_HIM_CATALOG_PASSED",len(data["steps"]),len(col.objects),output.stat().st_size)
app.unregister()
