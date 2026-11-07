bl_info = {
    "name": "exCADmple — Design Reasoning Player (Prototype)",
    "author": "exCADmple research prototype",
    "version": (0, 5, 0), "blender": (4, 1, 0),
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
from bpy.props import BoolProperty, StringProperty, FloatProperty, EnumProperty
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d
from .core import load_example, step_at_frame, caption_at_frame, pointer_at_frame, pointer_world_at_frame, operation_phase, progress_in_step
from .procedural import build_extrusion
from .him_ops import build_operation, OPERATION_TYPES
from .viewport_panel import draw as draw_him_panel
from .overlay_geometry import panel_layout, hit_test

REF_NAME = "exCADmple | Recorded example (read-only)"
_session = {
    "draw_handler": None, "step_id": None,
    "panel_active": False, "panel_area": None,
    "panel_generation": 0, "panel_speed": 1.0,
}

def example_for_scene(scene):
    raw = scene.get("excadmple_example", "")
    if not raw: return None
    try: return json.loads(raw)
    except Exception: return None

def get_reference(scene):
    """Find only the reference attached to this Scene, never a global name.

    A .blend may contain several Scenes; the earlier global lookup could
    accidentally delete another Scene's reference when reloading a demo.
    """
    for col in scene.collection.children:
        if col.get("excadmple_reference_collection"):
            return col
    # Legacy saved smoke scenes lack the collection marker. Recognize them
    # by both name and our object metadata, not name alone.
    for col in scene.collection.children:
        if col.name.startswith(REF_NAME) and any(
            obj.get("excadmple_reference") for obj in col.objects
        ):
            return col
    return None

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
    col["excadmple_reference_collection"]=True
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
    scene["excadmple_showcase_mode"]=False
    scene.frame_set(scene.frame_start)
    num_audio=add_narration(scene,data,root)
    _session["step_id"]=None
    _session["panel_speed"]=1.0
    # The reference is inspectable but not directly editable or selectable.
    for obj in col.objects:
        obj.hide_select = True
    update_focus(scene)
    return {"objects":3,"audio_tracks":num_audio}

def build_showcase(scene, data):
    """Load 20 independent reference demonstrations without touching user meshes."""
    from .core import validate_example
    validate_example(data)
    if data.get("geometry_preset") != "him_feature_showcase_v1":
        raise ValueError("Not an operation showcase")
    unlink_reference(scene)
    col=bpy.data.collections.new(REF_NAME)
    col["excadmple_reference_collection"]=True
    scene.collection.children.link(col)
    total=0
    for step in data["steps"]:
        built=build_operation(col,step)
        if not built:
            raise RuntimeError("No reference geometry created for "+step["id"])
        total+=len(built)
    scene.render.fps=int(data.get("fps",24))
    scene.frame_start=data["steps"][0]["start"]
    scene.frame_end=data["steps"][-1]["end"]
    scene["excadmple_example"]=json.dumps(data,separators=(",",":"))
    scene["excadmple_is_mock"]=True
    scene["excadmple_showcase_mode"]=True
    _session["step_id"]=None
    scene.frame_set(scene.frame_start)
    for obj in col.objects:
        obj.hide_select = True
    update_focus(scene)
    return {"steps":len(data["steps"]),"objects":total}


def update_focus(scene):
    data=example_for_scene(scene)
    col=get_reference(scene)
    if not data or not col: return
    step=step_at_frame(data,scene.frame_current)
    if _session.get("step_id")==step["id"] and scene.get("excadmple_focus_last")==scene.excadmple_focus:
        return
    _session["step_id"]=step["id"]
    scene["excadmple_focus_last"]=scene.excadmple_focus
    is_showcase=bool(scene.get("excadmple_showcase_mode",False))
    for obj in col.objects:
        target=obj.get("excadmple_step")==step["id"]
        if is_showcase:
            # Only the demonstrated feature is drawn; avoids 20 operations'
            # worth of spatial clutter. User objects outside this collection
            # are never hidden or modified.
            obj.hide_set(not target)
            if target:
                obj.display_type = "TEXTURED" if not obj.get("excadmple_auxiliary") else "WIRE"
                obj.show_in_front=bool(scene.excadmple_focus)
            continue
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

def _draw_ghost_circle(shader, location, radius, color, outline=False):
    """Visual feedback only. No synthetic mouse events are sent to Blender."""
    count=32
    ring=[
        (location[0]+math.cos(2*math.pi*i/count)*radius,
         location[1]+math.sin(2*math.pi*i/count)*radius)
        for i in range(count)
    ]
    if outline:
        batch=batch_for_shader(shader,"LINE_LOOP",{"pos":ring})
    else:
        vertices=[location]+ring
        triangles=[(0,i+1,(i+1)%count+1) for i in range(count)]
        batch=batch_for_shader(shader,"TRIS",{"pos":vertices},indices=triangles)
    shader.bind()
    shader.uniform_float("color",color)
    batch.draw(shader)


def _project_ghost_position(ctx, xyz):
    """Project a model-space reference event through the current 3D view."""
    rv3d=getattr(ctx.space_data,"region_3d",None)
    if rv3d is None:
        return None
    screen=location_3d_to_region_2d(ctx.region,rv3d,Vector(xyz))
    return None if screen is None else (float(screen.x),float(screen.y))


def _ghost_position(ctx, step, frame):
    xyz=pointer_world_at_frame(step,frame)
    if xyz is not None:
        return _project_ghost_position(ctx,xyz)
    # Backward compatibility for developer examples with screen-space cues.
    x,y=pointer_at_frame(step,frame)
    return (x*ctx.region.width,y*ctx.region.height)


def draw_cursor_overlay():
    """A noninteractive ghost *dot* illustrating the preset author's actions.

    The real mouse belongs entirely to the learner; this GPU drawing is not a
    cursor override, a mouse event, or a clickable control. World-space cues
    follow the reference model when the single viewport's camera changes.
    """
    ctx=bpy.context
    if ctx.area is None or ctx.area.type!="VIEW_3D" or ctx.region is None:
        return
    scene=ctx.scene
    data=example_for_scene(scene)
    if not data or not scene.excadmple_overlay:
        return
    step=step_at_frame(data,scene.frame_current)
    loc=_ghost_position(ctx,step,scene.frame_current)
    if loc is None:
        return
    w,h=ctx.region.width,ctx.region.height
    trail=[]
    for frame in range(max(step["start"],scene.frame_current-22),
                       scene.frame_current+1,2):
        point=_ghost_position(ctx,step,frame)
        if point is not None:
            trail.append(point)
    gpu.state.blend_set("ALPHA")
    shader=gpu.shader.from_builtin("UNIFORM_COLOR")
    try:
        if len(trail)>1:
            batch=batch_for_shader(shader,"LINE_STRIP",{"pos":trail})
            shader.bind()
            shader.uniform_float("color",(.98,.64,.26,.60))
            gpu.state.line_width_set(2.5)
            batch.draw(shader)

        # The ghost is a soft halo + small dot, visibly distinct from the
        # learner's true OS cursor. No input handler is registered for it.
        _draw_ghost_circle(shader,loc,11,(.96,.63,.24,.16))
        _draw_ghost_circle(shader,loc,5.8,(.98,.66,.28,.94))
        _draw_ghost_circle(shader,loc,2.3,(1.,1.,1.,.93))

        # Click is represented by a short, fading ripple at the point
        # of the previous designer's illustrated click event.
        relative=scene.frame_current-step["start"]
        for sample in step.get("pointer_world",[]):
            if sample.get("event")!="click":
                continue
            elapsed=relative-sample["at"]
            if not 0<=elapsed<=9:
                continue
            click_pos=_project_ghost_position(ctx,sample["xyz"])
            if click_pos is not None:
                amount=elapsed/9.
                _draw_ghost_circle(shader,click_pos,10+18*amount,
                                   (.98,.72,.34,.85*(1.-amount)),
                                   outline=True)
        font=0
        blf.size(font,12)
        blf.color(font,.96,.88,.71,1.)
        blf.position(font,loc[0]+13,loc[1]+10,0)
        blf.draw(font,"EXAMPLE")
        blf.size(font,12)
        blf.color(font,.94,.94,.95,1.)
        blf.position(font,loc[0]+13,loc[1]-11,0)
        blf.draw(font,operation_phase(step,scene.frame_current))
        if step.get("animation",{}).get("type")=="extrude":
            spec=step["animation"]
            phase=progress_in_step(step,scene.frame_current)
            growth=max(0,min(1,(phase-.31)/.69))
            blf.position(font,loc[0]+13,loc[1]-28,0)
            blf.draw(font,"%.2f / %.2f BU"%(growth*spec["distance"],
                                            spec["distance"]))
        # Keep captions but do not draw a fake software pointer.
        blf.color(font,1,1,1,1)
        blf.position(font,22,30,0)
        blf.draw(font,caption_at_frame(step,scene.frame_current)
                 [:max(28,int(w/9))])
    finally:
        gpu.state.line_width_set(1.)
        gpu.state.blend_set("NONE")

def draw_overlay():
    """Render mouse reenactment and HiM panel over ONE editable 3D region."""
    ctx = bpy.context
    if not ctx.area or ctx.area.type != "VIEW_3D" or not ctx.region:
        return
    example = example_for_scene(ctx.scene)
    if not example:
        return
    if ctx.scene.excadmple_overlay:
        draw_cursor_overlay()
    if (_session.get("panel_active")
            and _session.get("panel_area") == ctx.area.as_pointer()):
        draw_him_panel(ctx, example, _session.get("panel_speed", 1.0))


class EXCADMPLE_OT_load_demo(bpy.types.Operator):
    bl_idname="excadmple.load_demo"
    bl_label="Load Example"
    bl_description="Build a separate read-only animated example; preserve all other objects"
    def execute(self,context):
        path=Path(__file__).parent/"demo.json"
        data=load_example(path)
        stats=build_demo(context.scene,data,path.parent)
        # An explicit operator runs in the same VIEW_3D area. No second
        # window/viewport is created. In headless CI, skip modal UI.
        if not bpy.app.background and not _session.get("panel_active"):
            try:
                bpy.ops.excadmple.viewport_panel("INVOKE_DEFAULT")
            except RuntimeError:
                # The user can also activate via the N-sidebar button.
                pass
        self.report({"INFO"},"Loaded %d animated objects and %d audio tracks"%(stats["objects"],stats["audio_tracks"]))
        return {"FINISHED"}

class EXCADMPLE_OT_load_him(bpy.types.Operator):
    bl_idname="excadmple.load_him_showcase"
    bl_label="Load HiM Animation Catalog"
    bl_description="Open the 20-feature synthetic operation animation showcase"

    def execute(self,context):
        path=Path(__file__).parent/"him_showcase.json"
        try:
            data=load_example(path)
            result=build_showcase(context.scene,data)
        except Exception as error:
            self.report({"ERROR"},str(error))
            return {"CANCELLED"}
        self.report({"INFO"},"Built %d animation steps (%d reference objects)"%
                    (result["steps"],result["objects"]))
        return {"FINISHED"}


class EXCADMPLE_OT_import(bpy.types.Operator,ImportHelper):
    bl_idname="excadmple.import_example"
    bl_label="Import Example JSON"
    filename_ext=".json"
    filter_glob: StringProperty(default="*.json",options={"HIDDEN"})
    def execute(self,context):
        try:
            data=load_example(self.filepath)
            if data["geometry_preset"]=="him_feature_showcase_v1":
                build_showcase(context.scene,data)
            else:
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


def _active_step_index(data, frame):
    current = step_at_frame(data, frame)
    return next((i for i, item in enumerate(data["steps"])
                 if item["id"] == current["id"]), 0)


def _progress_get(scene):
    data = example_for_scene(scene)
    if not data:
        return 0.0
    item = step_at_frame(data, scene.frame_current)
    return max(0.0, min(1.0, (scene.frame_current - item["start"]) /
                        max(1, item["end"] - item["start"])))


def _progress_set(scene, progress):
    data = example_for_scene(scene)
    if not data:
        return
    item = step_at_frame(data, scene.frame_current)
    scene.frame_set(item["start"] + round(
        max(0.0, min(1.0, progress)) * (item["end"] - item["start"])
    ))


class EXCADMPLE_OT_navigate(bpy.types.Operator):
    bl_idname = "excadmple.navigate"
    bl_label = "Navigate design example"
    bl_description = "Browse the reference steps without editing your model"

    action: EnumProperty(items=[
        ("PREVIOUS", "Previous step", ""),
        ("NEXT", "Next step", ""),
        ("REPLAY", "Replay step", ""),
        ("BEGINNING", "Start of example", "")
    ], default="NEXT")

    def execute(self, context):
        data = example_for_scene(context.scene)
        if not data:
            return {"CANCELLED"}
        i = _active_step_index(data, context.scene.frame_current)
        if self.action == "BEGINNING":
            i = 0
        elif self.action == "PREVIOUS":
            i = max(0, i - 1)
        elif self.action == "NEXT":
            i = min(len(data["steps"]) - 1, i + 1)
        context.scene.frame_set(data["steps"][i]["start"])
        return {"FINISHED"}


def _wrapped_labels(layout, message, width=39):
    for line in textwrap.wrap(message or "No information attached to this step.",
                              width=width):
        layout.label(text=line)



class EXCADMPLE_OT_viewport_panel(bpy.types.Operator):
    """Capture input only over the floating HiM panel.

    Every event outside the right-side overlay is PASS_THROUGH, allowing
    normal selection, mesh editing, navigation and Blender shortcuts in
    the same 3D Viewport.
    """
    bl_idname = "excadmple.viewport_panel"
    bl_label = "Show exCADmple HiM Player"
    bl_description = "Show the interactive player inside this 3D viewport"

    def invoke(self, context, event):
        if not context.area or context.area.type != "VIEW_3D":
            self.report({"ERROR"}, "Open this control from a 3D Viewport")
            return {"CANCELLED"}
        if not example_for_scene(context.scene):
            self.report({"ERROR"}, "Open the preset model first")
            return {"CANCELLED"}
        if _session.get("panel_active"):
            return {"CANCELLED"}
        region = next((r for r in context.area.regions if r.type == "WINDOW"), None)
        if not region:
            return {"CANCELLED"}
        self._area = context.area
        self._region = region
        self._dragging = False
        _session["panel_generation"] += 1
        self._generation = _session["panel_generation"]
        _session["panel_active"] = True
        _session["panel_area"] = context.area.as_pointer()
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {"RUNNING_MODAL"}

    def _layout_and_local(self, context, event):
        # Use window coordinates rather than mouse_region_x, which refers to
        # the Sidebar when the operator was started from the N-panel.
        region = self._region
        x = event.mouse_x - region.x
        y = event.mouse_y - region.y
        data = example_for_scene(context.scene)
        if not data:
            return None, x, y
        index = _active_step_index(data, context.scene.frame_current)
        return panel_layout(region.width, region.height, index, len(data["steps"])), x, y

    def _seek_to_x(self, context, layout, x):
        bar = layout["buttons"]["progress"]
        position = min(1.0, max(0.0, (x - bar.x) / max(1.0, bar.w)))
        _progress_set(context.scene, position)

    def _close(self):
        if _session.get("panel_generation") == self._generation:
            _session["panel_active"] = False
            _session["panel_area"] = None
            _session["panel_generation"] += 1
        try:
            self._area.tag_redraw()
        except ReferenceError:
            pass

    def modal(self, context, event):
        if (not _session.get("panel_active") or
                _session.get("panel_generation") != self._generation):
            return {"CANCELLED"}
        if not self._area or not self._region:
            self._close()
            return {"CANCELLED"}
        if context.window is None:
            self._close()
            return {"CANCELLED"}
        if not example_for_scene(context.scene):
            self._close()
            return {"CANCELLED"}

        layout, x, y = self._layout_and_local(context, event)
        if layout is None:
            return {"PASS_THROUGH"}
        if self._dragging:
            if event.type == "MOUSEMOVE":
                self._seek_to_x(context, layout, x)
                self._area.tag_redraw()
                return {"RUNNING_MODAL"}
            if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                self._seek_to_x(context, layout, x)
                self._dragging = False
                self._area.tag_redraw()
                return {"RUNNING_MODAL"}

        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"PASS_THROUGH"}

        action = hit_test(layout, x, y)
        if action is None:
            return {"PASS_THROUGH"}
        if action == "close":
            self._close()
            return {"CANCELLED"}

        data = example_for_scene(context.scene)
        scene = context.scene
        current_idx = _active_step_index(data, scene.frame_current)
        if action.startswith("step:"):
            index = int(action.split(":", 1)[1])
            scene.frame_set(data["steps"][index]["start"])
        elif action == "previous":
            scene.frame_set(data["steps"][max(0, current_idx - 1)]["start"])
        elif action == "next":
            scene.frame_set(data["steps"][min(len(data["steps"]) - 1,
                                              current_idx + 1)]["start"])
        elif action == "play_pause":
            bpy.ops.screen.animation_play()
        elif action == "progress":
            self._dragging = True
            self._seek_to_x(context, layout, x)
        elif action in ("speed_minus", "speed_plus"):
            speeds = (0.5, 1.0, 1.5, 2.0)
            old = _session["panel_speed"]
            i = min(range(len(speeds)), key=lambda j: abs(speeds[j] - old))
            i = max(0, i - 1) if action == "speed_minus" else min(len(speeds) - 1, i + 1)
            _session["panel_speed"] = speeds[i]
            # Native Blender's scene frame currently drives both the
            # reference and any user-authored animation. Speed affects
            # that global clock, not the user's static geometry.
            scene.render.fps = max(1, int(round(
                data.get("fps", 24) * speeds[i])))
        # 'panel' consumes clicks to prevent selecting a mesh underneath it.
        self._area.tag_redraw()
        return {"RUNNING_MODAL"}


class EXCADMPLE_PT_sidebar(bpy.types.Panel):
    """Minimal launch control; actual HiM-style UI lives in the 3D viewport."""
    bl_label = "exCADmple"
    bl_idname = "EXCADMPLE_PT_sidebar"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "exCADmple"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        data = example_for_scene(scene)
        layout.label(text="PRESET DESIGN EXAMPLE", icon="OUTLINER_OB_MESH")
        if not data:
            layout.operator("excadmple.load_demo",
                            text="Open Phone Stand Example", icon="FILE_3D")
            return
        layout.label(text=data.get("title", "Design example")[:38])
        if _session.get("panel_active"):
            layout.label(text="Player visible in the viewport", icon="CHECKMARK")
            layout.label(text="Use its X to close it.")
        else:
            layout.operator("excadmple.viewport_panel",
                            text="Show HiM-style Player", icon="PLAY")
        layout.prop(scene, "excadmple_overlay", text="Ghost cursor / captions")
        layout.prop(scene, "excadmple_focus", text="Focus on example step")
        layout.separator()
        layout.label(text="Example and your design share ONE viewport.")
        layout.label(text="Reference objects cannot be selected.")

CLASSES = (
    EXCADMPLE_OT_load_demo,
    EXCADMPLE_OT_go_step,
    EXCADMPLE_OT_play, EXCADMPLE_OT_navigate,
    EXCADMPLE_OT_viewport_panel, EXCADMPLE_PT_sidebar
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.excadmple_overlay = BoolProperty(
        name="Recorded Cursor", default=True)
    bpy.types.Scene.excadmple_focus = BoolProperty(
        name="Focus Reference", default=True)
    bpy.types.Scene.excadmple_step_progress = FloatProperty(
        name="Current Step Progress", min=0.0, max=1.0,
        subtype="FACTOR", precision=2, get=_progress_get, set=_progress_set)
    bpy.types.Scene.excadmple_show_all_steps = BoolProperty(
        name="Show all reference steps", default=False)
    bpy.types.Scene.excadmple_show_transcript = BoolProperty(
        name="Show synchronized transcript", default=True)
    if on_frame not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(on_frame)
    if not bpy.app.background and _session["draw_handler"] is None:
        _session["draw_handler"] = bpy.types.SpaceView3D.draw_handler_add(
            draw_overlay, (), "WINDOW", "POST_PIXEL")


def unregister():
    _session["panel_active"] = False
    _session["panel_area"] = None
    _session["panel_generation"] += 1
    if _session["draw_handler"] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(
            _session["draw_handler"], "WINDOW")
        _session["draw_handler"] = None
    if on_frame in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(on_frame)
    for prop in ("excadmple_overlay", "excadmple_focus",
                 "excadmple_step_progress", "excadmple_show_all_steps",
                 "excadmple_show_transcript"):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

if __name__=="__main__": register()
