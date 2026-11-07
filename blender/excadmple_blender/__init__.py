bl_info = {
    "name": "exCADmple — Design Reasoning Player (Prototype)",
    "author": "exCADmple research prototype",
    "version": (0, 2, 0), "blender": (4, 1, 0),
    "location": "3D View > Sidebar > exCADmple",
    "description": "Explore design animations, recorded cursor paths, synchronized transcripts and audio",
    "category": "3D View",
}
import bpy
import blf
import gpu
import json
import math
import textwrap
from pathlib import Path
from bpy.app.handlers import persistent
from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, StringProperty
from gpu_extras.batch import batch_for_shader
from .core import load_example, step_at_frame, caption_at_frame, pointer_at_frame, operation_phase, progress_in_step
from .procedural import build_extrusion

REF_NAME = "exCADmple | Recorded example (read-only)"
_session = {"draw_handler": None, "step_id": None}

def example_for_scene(scene):
    raw = scene.get("excadmple_example", "")
    if not raw: return None
    try: return json.loads(raw)
    except Exception: return None

def get_reference(scene):
    return bpy.data.collections.get(REF_NAME)

def add_cube(name, collection, color):
    # Reference shapes are synthetic and NEVER claim to be recovered F3D history.
    verts=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    mesh=bpy.data.meshes.new(name+" mesh")
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    collection.objects.link(obj)
    mat=bpy.data.materials.get("exCADmple Reference Blue")
    if not mat:
        mat=bpy.data.materials.new("exCADmple Reference Blue")
        mat.diffuse_color=(.27,.53,.81,1)
        mat.use_nodes=True
        node=mat.node_tree.nodes.get("Principled BSDF")
        if node:
            node.inputs["Base Color"].default_value=(.27,.53,.81,1)
            node.inputs["Roughness"].default_value=.38
    obj.data.materials.append(mat)
    obj.color=color
    obj["excadmple_reference"]=True
    return obj

def key_pose(obj,frame,location,scale,angle_deg=0.0):
    obj.location=location
    obj.scale=scale
    obj.rotation_euler=(math.radians(angle_deg),0,0)
    for key in ("location","scale","rotation_euler"):
        obj.keyframe_insert(data_path=key,frame=frame)

def unlink_reference(scene):
    col=get_reference(scene)
    if col:
        for obj in list(col.objects):
            bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.collections.remove(col)
    ed=scene.sequence_editor
    if ed:
        strips=getattr(ed,"strips",None) or getattr(ed,"sequences",None)
        if strips:
            for strip in list(strips):
                if strip.name.startswith("exCADmple voice:"):
                    strips.remove(strip)

def add_narration(scene,data,root):
    ed=scene.sequence_editor_create()
    strips=getattr(ed,"strips",None) or getattr(ed,"sequences",None)
    count=0
    for step in data["steps"]:
        rel=step.get("audio","")
        if not rel or ".." in Path(rel).parts or Path(rel).is_absolute():
            continue
        wav=(Path(root)/rel).resolve()
        if not wav.is_file():
            continue
        strip=strips.new_sound("exCADmple voice: "+step["id"],str(wav),channel=8,frame_start=step["start"])
        strip.volume=.9
        count+=1
    return count

def build_demo(scene,data,root):
    # This spike deliberately accepts ONLY the phone_stand_v1 geometry preset.
    unlink_reference(scene)
    col=bpy.data.collections.new(REF_NAME)
    scene.collection.children.link(col)
    x=-2.8
    # Shape-key extrusion animates actual profile vertices, not cube scale.
    base, base_sketch, base_gizmo=build_extrusion(
        col,data["steps"][0],"exCADmple | 01 Base extrude"
    )
    back=add_cube("exCADmple | 02 Angled back support",col,(.31,.62,.90,1))
    back["excadmple_step"]="support"
    key_pose(back,1,(x,.75,.27),(.05,.09,.005))
    key_pose(back,120,(x,.75,.27),(.05,.09,.005))
    key_pose(back,121,(x,.75,.27),(1.42,.10,.005))
    key_pose(back,184,(x,.75,1.15),(1.42,.10,.95),0)
    key_pose(back,240,(x,.95,1.08),(1.42,.10,.95),-18)
    key_pose(back,360,(x,.95,1.08),(1.42,.10,.95),-18)
    lip, lip_sketch, lip_gizmo=build_extrusion(
        col,data["steps"][2],"exCADmple | 03 Front lip extrude"
    )
    scene.render.fps=int(data.get("fps",24))
    scene.frame_start=data["steps"][0]["start"]
    scene.frame_end=data["steps"][-1]["end"]
    scene["excadmple_example"]=json.dumps(data,separators=(",",":"))
    scene["excadmple_is_mock"]=True
    scene.frame_set(scene.frame_start)
    num_audio=add_narration(scene,data,root)
    _session["step_id"]=None
    update_focus(scene)
    return {"objects":3,"audio_tracks":num_audio}

def update_focus(scene):
    data=example_for_scene(scene)
    col=get_reference(scene)
    if not data or not col: return
    step=step_at_frame(data,scene.frame_current)
    if _session.get("step_id")==step["id"] and scene.get("excadmple_focus_last")==scene.excadmple_focus:
        return
    _session["step_id"]=step["id"]
    scene["excadmple_focus_last"]=scene.excadmple_focus
    for obj in col.objects:
        target=obj.get("excadmple_step")==step["id"]
        # Sketch and manipulator are aids for the current operation only.
        if obj.get("excadmple_auxiliary"):
            obj.hide_set(not target)
            continue
        obj.display_type="TEXTURED" if (not scene.excadmple_focus or target) else "WIRE"
        obj.show_in_front=bool(target and scene.excadmple_focus)
    # No user-created objects (outside REF_NAME) are touched.

@persistent
def on_frame(scene,_depsgraph=None):
    if example_for_scene(scene):
        update_focus(scene)

def draw_overlay():
    ctx=bpy.context
    if ctx.area is None or ctx.area.type!="VIEW_3D" or ctx.region is None: return
    scene=ctx.scene
    data=example_for_scene(scene)
    if not data or not scene.excadmple_overlay: return
    step=step_at_frame(data,scene.frame_current)
    w,h=ctx.region.width,ctx.region.height
    x,y=pointer_at_frame(step,scene.frame_current)
    loc=(x*w,y*h)
    trail=[]
    for frame in range(max(step["start"],scene.frame_current-18),scene.frame_current+1,2):
        px,py=pointer_at_frame(step,frame)
        trail.append((px*w,py*h))
    gpu.state.blend_set("ALPHA")
    shader=gpu.shader.from_builtin("UNIFORM_COLOR")
    if len(trail)>1:
        batch=batch_for_shader(shader,"LINE_STRIP",{"pos":trail})
        shader.bind()
        shader.uniform_float("color",(.16,.54,.98,.70))
        gpu.state.line_width_set(3.)
        batch.draw(shader)
    points=[loc,(loc[0]+4,loc[1]-17),(loc[0]+8,loc[1]-10),(loc[0]+15,loc[1]-9)]
    triangles=[points[0],points[1],points[2],points[0],points[2],points[3]]
    batch=batch_for_shader(shader,"TRIS",{"pos":triangles})
    shader.bind()
    shader.uniform_float("color",(.98,.74,.20,.96))
    batch.draw(shader)
    gpu.state.line_width_set(1.)
    gpu.state.blend_set("NONE")
    font=0
    blf.size(font,14)
    blf.color(font,.96,.96,.95,1)
    blf.position(font,loc[0]+19,loc[1]+3,0)
    blf.draw(font,"REPLAY  "+operation_phase(step,scene.frame_current))
    if step.get("animation",{}).get("type")=="extrude":
        spec=step["animation"]
        phase=progress_in_step(step,scene.frame_current)
        growth=max(0,min(1,(phase-.31)/.69))
        if phase<.31: growth=0
        blf.position(font,loc[0]+19,loc[1]-18,0)
        blf.draw(font,"DISTANCE   %.2f / %.2f BU"%(growth*spec["distance"],spec["distance"]))
    blf.size(font,17)
    blf.color(font,1,1,1,1)
    blf.position(font,22,max(32,h-40),0)
    blf.draw(font,"exCADmple  |  "+step["title"])
    blf.size(font,14)
    blf.position(font,22,30,0)
    blf.draw(font,caption_at_frame(step,scene.frame_current)[:max(28,int(w/9))])

class EXCADMPLE_OT_load_demo(bpy.types.Operator):
    bl_idname="excadmple.load_demo"
    bl_label="Load Example"
    bl_description="Build a separate read-only animated example; preserve all other objects"
    def execute(self,context):
        path=Path(__file__).parent/"demo.json"
        data=load_example(path)
        stats=build_demo(context.scene,data,path.parent)
        self.report({"INFO"},"Loaded %d animated objects and %d audio tracks"%(stats["objects"],stats["audio_tracks"]))
        return {"FINISHED"}

class EXCADMPLE_OT_import(bpy.types.Operator,ImportHelper):
    bl_idname="excadmple.import_example"
    bl_label="Import Example JSON"
    filename_ext=".json"
    filter_glob: StringProperty(default="*.json",options={"HIDDEN"})
    def execute(self,context):
        try:
            data=load_example(self.filepath)
            build_demo(context.scene,data,Path(self.filepath).parent)
        except Exception as error:
            self.report({"ERROR"},str(error))
            return {"CANCELLED"}
        return {"FINISHED"}

class EXCADMPLE_OT_go_step(bpy.types.Operator):
    bl_idname="excadmple.go_step"
    bl_label="Jump to step"
    frame: bpy.props.IntProperty(default=1,min=1)
    def execute(self,context):
        context.scene.frame_set(self.frame)
        return {"FINISHED"}

class EXCADMPLE_OT_play(bpy.types.Operator):
    bl_idname="excadmple.play_pause"
    bl_label="Play / Pause"
    def execute(self,context):
        bpy.ops.screen.animation_play()
        return {"FINISHED"}

class EXCADMPLE_PT_sidebar(bpy.types.Panel):
    bl_label="exCADmple"
    bl_idname="EXCADMPLE_PT_sidebar"
    bl_space_type="VIEW_3D"
    bl_region_type="UI"
    bl_category="exCADmple"
    def draw(self,context):
        layout=self.layout
        scene=context.scene
        data=example_for_scene(scene)
        row=layout.row(align=True)
        row.operator("excadmple.load_demo",text="Load Demo",icon="FILE_REFRESH")
        row.operator("excadmple.import_example",text="Import JSON",icon="IMPORT")
        if not data:
            layout.label(text="Load an example to explore it.")
            return
        layout.label(text=data.get("title","Example"),icon="OUTLINER_OB_MESH")
        layout.label(text="ILLUSTRATIVE REENACTMENT — NOT ORIGINAL HISTORY",icon="INFO")
        box=layout.box()
        box.label(text="Design process",icon="ACTION")
        for i,step in enumerate(data["steps"]):
            row=box.row(align=True)
            op=row.operator("excadmple.go_step",text=str(i+1)+"  "+step["title"],
                            depress=step["start"]<=scene.frame_current<=step["end"])
            op.frame=step["start"]
        row=layout.row(align=True)
        row.operator("excadmple.play_pause",text="Play / Pause",icon="PLAY")
        row.prop(scene,"frame_current",text="Frame")
        layout.prop(scene,"excadmple_overlay",text="Recorded cursor + subtitles")
        layout.prop(scene,"excadmple_focus",text="Focus on current reference step")
        step=step_at_frame(data,scene.frame_current)
        box=layout.box()
        box.label(text="Operation replay",icon="TOOL_SETTINGS")
        tool=box.row()
        tool.alert=True
        tool.label(text=operation_phase(step,scene.frame_current),icon="EVENT_E")
        if step.get("animation",{}).get("type")=="extrude":
            box.label(text="Distance: %.2f BU"%(step["animation"]["distance"]))
        box=layout.box()
        box.label(text="Why this decision?",icon="TEXT")
        for line in textwrap.wrap(step.get("reasoning",""),width=41):
            box.label(text=line)
        box=layout.box()
        box.label(text="Synchronized transcript",icon="SPEAKER")
        for line in textwrap.wrap(caption_at_frame(step,scene.frame_current),width=41):
            box.label(text=line)
        layout.label(text="Reference (left) | Your work (anywhere)",icon="INFO")
        layout.label(text="Your objects are never played or dimmed.",icon="INFO")

CLASSES=(EXCADMPLE_OT_load_demo,EXCADMPLE_OT_import,EXCADMPLE_OT_go_step,
         EXCADMPLE_OT_play,EXCADMPLE_PT_sidebar)

def register():
    for cls in CLASSES: bpy.utils.register_class(cls)
    bpy.types.Scene.excadmple_overlay=BoolProperty(name="Recorded Cursor",default=True)
    bpy.types.Scene.excadmple_focus=BoolProperty(name="Focus",default=True)
    if on_frame not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(on_frame)
    if not bpy.app.background and _session["draw_handler"] is None:
        _session["draw_handler"]=bpy.types.SpaceView3D.draw_handler_add(
            draw_overlay,(),"WINDOW","POST_PIXEL")

def unregister():
    if _session["draw_handler"] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_session["draw_handler"],"WINDOW")
        _session["draw_handler"]=None
    if on_frame in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(on_frame)
    if hasattr(bpy.types.Scene,"excadmple_focus"): del bpy.types.Scene.excadmple_focus
    if hasattr(bpy.types.Scene,"excadmple_overlay"): del bpy.types.Scene.excadmple_overlay
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)

if __name__=="__main__": register()
