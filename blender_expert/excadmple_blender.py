"""exCADmple — shared-viewport virtual CAD apprentice for Blender 4.2+.

Install as a single-file Add-on. Open or build a .blend lesson, select
3D View > Sidebar > exCADmple. Press PLAY and keep modeling with your real
mouse: the expert has a separate, synthetic cursor and nonselectable objects.
No Blender operator is injected into the learner's active command context.
"""
bl_info = {
    "name": "exCADmple: Virtual Expert in One Viewport",
    "author": "exCADmple",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > exCADmple",
    "description": "Watch a virtual CAD expert while editing your own model.",
    "category": "3D View",
}
import bpy
import json
import math
import time
import blf
import gpu
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from bpy.app.handlers import persistent

COLLECTION = "exCADmple | Reference (read only)"
LESSON_KEY = "excadmple.lesson.v1"
EXPERT_PREFIX = "MASTER | "
DEFAULT_SPEED = 1.0

# Commands are explicit, human-readable operations, not interpolated CAD
# geometry animations. Geometry changes discretely on 'Confirm'.
# Dimensions are in Blender units and measured before arbitrary transforms.
SAMPLE = [
    dict(title="Add base", tool="F3 → Add Cube", obj="Base", action="add",
         dims=[2,2,2], pos=[0,0,0], say="Start with a base that supports the phone."),
    dict(title="Size the base", tool="S X / S Y / S Z", obj="Base", action="transform",
         dims=[5.6,3.4,.36], pos=[0,0,.18], param="X 5.6   Y 3.4   Z 0.36",
         say="A wide footprint supports the phone without making the entire design heavy."),
    dict(title="Add the back support", tool="F3 → Add Cube", obj="Back", action="add",
         dims=[2,2,2], pos=[0,0,0], say="Next, construct a support for the phone."),
    dict(title="Position the back support", tool="S / G", obj="Back", action="transform",
         dims=[5.0,.30,4.8], pos=[0,1.38,2.4],
         param="Scale X 5.0, Y 0.3, Z 4.8 · Move to rear",
         say="The support height and placement depend on the phone's size and viewing position."),
    dict(title="Add the front lip", tool="F3 → Add Cube", obj="Lip", action="add",
         dims=[2,2,2], pos=[0,0,0], say="A lip will prevent the phone from sliding."),
    dict(title="Size the front lip", tool="S / G", obj="Lip", action="transform",
         dims=[5.0,.44,.84], pos=[0,-1.24,.42],
         param="Scale lip and move to front",
         say="Keep the lip low enough not to obstruct the screen."),
    dict(title="Add left brace", tool="F3 → Add Cube", obj="Left brace", action="add",
         dims=[2,2,2], pos=[0,0,0], say="Braces strengthen the back support."),
    dict(title="Place left brace", tool="S / G", obj="Left brace", action="transform",
         dims=[.4,2.6,2.5], pos=[-2.3,.4,1.25],
         param="Scale and move to x = -2.3",
         say="A brace near the edge preserves space in the center."),
    dict(title="Add right brace", tool="F3 → Add Cube", obj="Right brace", action="add",
         dims=[2,2,2], pos=[0,0,0], say="Repeat the structural idea on the other side."),
    dict(title="Place right brace", tool="S / G", obj="Right brace", action="transform",
         dims=[.4,2.6,2.5], pos=[2.3,.4,1.25],
         param="Scale and move to x = 2.3",
         say="The mirrored placement creates balanced support."),
    dict(title="Soften exposed edges", tool="Ctrl+B → Bevel", obj="Base", action="bevel",
         param="Bevel width 0.15", say="Softened edges improve handling and reduce sharp contacts."),
    dict(title="Inspect the result", tool="Orbit / inspect", obj="Base", action="inspect",
         say="Inspect the phone contact surfaces and adjust the design for your device."),
]

RUNTIME = {
    "playing": False, "step": 0, "phase": 0, "started": 0.0,
    "handler": None, "lesson": [], "models": {}, "source": "",
    "status": "Load or create a lesson", "last_reason": "",
}
PHASE_SECONDS = (1.05, .95, 1.2, .6)
SHADER = None
PHASE_NAMES = ("Locate tool", "Select reference", "Enter parameters", "Confirm")


def _collection(scene):
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
    if not any(c == coll for c in scene.collection.children):
        scene.collection.children.link(coll)
    return coll


def _cube_mesh(name):
    verts = [(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),
             (1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)]
    faces = [(0,4,6,2),(1,3,7,5),(0,1,5,4),
             (2,6,7,3),(0,2,3,1),(4,5,7,6)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def _reference_obj(name, coll):
    obj = bpy.data.objects.new(EXPERT_PREFIX + name, _cube_mesh(EXPERT_PREFIX + name))
    coll.objects.link(obj)
    obj.hide_select = True
    obj.color = (.21,.69,.74,1)
    obj.hide_set(True)
    return obj


def _clean_reference(scene):
    existing = bpy.data.collections.get(COLLECTION)
    if existing:
        for obj in list(existing.objects):
            bpy.data.objects.remove(obj, do_unlink=True)


def _position(obj, step):
    dims = step.get("dims", [2,2,2])
    pos = step.get("pos", [0,0,0])
    if obj.get("excadmple_raw_mesh"):
        # Selected .blend object meshes carry their own topology, dimensions,
        # rotation and scale baked into the copied vertices.
        obj.scale = (1, 1, 1)
    else:
        obj.scale = [max(.001, float(x)/2.0) for x in dims]
    # Master is offset to the right of the learner, in the SAME viewport.
    obj.location = [float(pos[0]) + 7.5, float(pos[1]), float(pos[2])]
    obj.hide_set(False)
    obj.hide_select = True


def _rebuild(step_index, phase):
    lesson = RUNTIME["lesson"]
    for obj in RUNTIME["models"].values():
        if obj and obj.name in bpy.data.objects:
            obj.hide_set(True)
            # Seeking/restarting must not leave future expert modifiers applied.
            old_bevel = obj.modifiers.get("expert_bevel")
            if old_bevel is not None:
                obj.modifiers.remove(old_bevel)
    if not lesson:
        return
    for i, step in enumerate(lesson):
        if i > step_index or (i == step_index and phase < 3):
            continue
        obj = RUNTIME["models"].get(step.get("obj"))
        if not obj or obj.name not in bpy.data.objects:
            continue
        if step.get("dims") is not None:
            _position(obj, step)
        else:
            obj.hide_set(False)
        if step.get("action") == "bevel" and not obj.modifiers.get("expert_bevel"):
            mod = obj.modifiers.new("expert_bevel", "BEVEL")
            mod.width = .15
            mod.segments = 3
        if step.get("action") == "inspect":
            obj.hide_set(False)
    # Some later steps do not modify their target geometry; preserve its last state.
    if step_index < len(lesson):
        for i, step in enumerate(lesson[:step_index]):
            obj = RUNTIME["models"].get(step.get("obj"))
            if obj and i < step_index and obj.hide_get():
                obj.hide_set(False)


def _load(scene):
    raw = scene.get(LESSON_KEY)
    if not raw:
        raise ValueError("No embedded tutorial. Use 'Build .blend example' first.")
    lesson = json.loads(raw)
    if not isinstance(lesson, list) or not lesson:
        raise ValueError("Invalid embedded lesson.")
    RUNTIME["lesson"] = lesson
    RUNTIME["models"] = {
        obj.name[len(EXPERT_PREFIX):]: obj
        for obj in bpy.data.collections[COLLECTION].objects
        if obj.name.startswith(EXPERT_PREFIX)
    }
    RUNTIME["step"] = 0
    RUNTIME["phase"] = 0
    RUNTIME["playing"] = False
    RUNTIME["source"] = scene.name
    _rebuild(0,0)


def build_example(scene):
    _clean_reference(scene)
    coll = _collection(scene)
    for name in sorted({s["obj"] for s in SAMPLE}):
        _reference_obj(name, coll)
    scene[LESSON_KEY] = json.dumps(SAMPLE)
    _load(scene)
    RUNTIME["status"] = "Sample loaded · 12 authentic command demonstrations"
    return len(SAMPLE)


def _read_expert_object_geometry(obj):
    # A lesson from a general .blend uses geometry already in the file.
    # This is explicitly a reconstruction, not the author's recorded actions.
    pos = [float(v) for v in obj.location]
    dims = [float(v) for v in obj.dimensions]
    return pos, dims


def build_from_selected(scene, selected):
    selected = [o for o in selected if o.type == "MESH" and not o.name.startswith(EXPERT_PREFIX)]
    if not selected:
        raise ValueError("Select one or more existing mesh objects first.")
    snapshot = []
    for o in selected:
        pos, dims = _read_expert_object_geometry(o)
        mesh = o.data.copy()
        # Bake the original object's rotation/scale into its read-only copy;
        # keep its world translation separate for the teacher placement.
        mesh.transform(o.matrix_world.to_3x3().to_4x4())
        snapshot.append((o.name, pos, dims, mesh))
    _clean_reference(scene)
    coll = _collection(scene)
    steps = []
    for i,(name,pos,dims,mesh) in enumerate(snapshot):
        key = "Reference " + str(i+1) + " · " + name
        ob = bpy.data.objects.new(EXPERT_PREFIX + key, mesh)
        coll.objects.link(ob)
        ob.hide_set(True)
        ob.hide_select = True
        ob["excadmple_raw_mesh"] = True
        ob.color = (.21,.69,.74,1)
        steps.append(dict(title="Place " + name, tool="Object / Add Mesh",
                          obj=key, action="add", dims=dims, pos=[0,0,0],
                          say="A plausible reconstruction from the saved geometry; original commands were not recorded."))
        steps.append(dict(title="Position " + name, tool="G / S / R",
                          obj=key, action="transform", dims=dims,
                          pos=[pos[0],pos[1],pos[2]],
                          param="Dimensions " + ", ".join("%.2f"%v for v in dims),
                          say="Adjust the placement and proportions to match your own requirements."))
    scene[LESSON_KEY] = json.dumps(steps)
    _load(scene)
    RUNTIME["status"] = "Reconstructed example from selected meshes (not recorded UI history)"
    return len(steps)


def _area_region():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "WINDOW":
                        return area,region
    return None,None


def _box(x,y,w,h,color):
    global SHADER
    if SHADER is None:
        SHADER = gpu.shader.from_builtin("UNIFORM_COLOR")
    vertices = [(x,y),(x+w,y),(x+w,y+h),(x,y),
                (x+w,y+h),(x,y+h)]
    batch = batch_for_shader(SHADER,"TRIS",{"pos":vertices})
    SHADER.bind()
    SHADER.uniform_float("color",color)
    batch.draw(SHADER)


def _word(x,y,text,size=13,color=(1,1,1,1)):
    font = 0
    blf.size(font,size)
    blf.color(font,*color)
    blf.position(font,x,y,0)
    blf.draw(font,str(text))


def _cursor(x,y):
    _box(x,y-21,3,22,(1,.7,.24,1))
    _box(x+1,y-4,12,3,(1,.7,.24,1))
    _word(x+14,y-14,"EXPERT",10,(1,.73,.28,1))


def _draw():
    if not RUNTIME["lesson"]:
        return
    area,region=_area_region()
    if not area or not region or bpy.context.region != region:
        return
    step = RUNTIME["lesson"][RUNTIME["step"]]
    w,h = region.width,region.height
    phase = RUNTIME["phase"]
    t = max(0,min(1,(time.monotonic()-RUNTIME["started"])/PHASE_SECONDS[phase]))
    gpu.state.blend_set("ALPHA")
    # Faux tool interaction occurs in the SAME visible native viewport.
    # It does not change Blender's own active operator or hijack the mouse.
    _box(22,h-110,min(400,w-44),87,(.07,.085,.105,.91))
    _word(34,h-48,"EXPERT · Step %d/%d"%(RUNTIME["step"]+1,len(RUNTIME["lesson"])),15)
    _word(34,h-70,step.get("title",""),13,(.77,.9,.93,1))
    _word(34,h-92,step.get("tool",""),13,(1,.76,.40,1))
    bx=max(22,w-315)
    _box(bx,h-180,293,137,(.11,.12,.15,.94))
    _word(bx+12,h-59,"CAD operation",14)
    _word(bx+12,h-88,PHASE_NAMES[phase],12,(1,.76,.40,1))
    val=step.get("param",step.get("tool",""))
    _word(bx+12,h-113,str(val)[:42],11,(.9,.9,.9,1))
    _word(bx+12,h-145,"Confirm" if phase==3 else "Preview / next",11,(.6,.85,.75,1))
    # Contextual reasoning appears only at a few meaningful decisions.
    if step.get("say") and phase==2:
        _box(22,22,min(w-44,600),65,(.11,.14,.17,.94))
        _word(34,65,"WHY",11,(1,.75,.36,1))
        words=step["say"]
        _word(34,39,words[:93],12)
    # Expert pointer moves on a deterministic animation; the user's real
    # macOS/Blender cursor remains entirely independent.
    target=RUNTIME["models"].get(step.get("obj"))
    model_xy=(w*.62,h*.49)
    if target:
        try:
            from bpy_extras.view3d_utils import location_3d_to_region_2d
            pt=location_3d_to_region_2d(region,area.spaces.active.region_3d,
                                        target.matrix_world.translation)
            if pt: model_xy=(pt.x,pt.y)
        except Exception:
            pass
    targets=((60,h-80),model_xy,(bx+150,h-115),(bx+247,h-145))
    destination=targets[phase]
    origin=targets[max(0,phase-1)] if phase else (w*.5,h*.5)
    x=origin[0]+(destination[0]-origin[0])*min(1,t*2)
    y=origin[1]+(destination[1]-origin[1])*min(1,t*2)
    _cursor(x,y)
    gpu.state.blend_set("NONE")


def _redraw():
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type=="VIEW_3D":
                    area.tag_redraw()
    except Exception:
        pass


def _tick():
    if RUNTIME["playing"] and RUNTIME["lesson"]:
        seconds=PHASE_SECONDS[RUNTIME["phase"]]
        if time.monotonic()-RUNTIME["started"]>=seconds/max(.2,RUNTIME.get("speed",1)):
            if RUNTIME["phase"]==3:
                _rebuild(RUNTIME["step"],3)
                if RUNTIME["step"]+1>=len(RUNTIME["lesson"]):
                    RUNTIME["playing"]=False
                    RUNTIME["status"]="Finished. Keep modeling in your own workspace."
                else:
                    RUNTIME["step"]+=1
                    RUNTIME["phase"]=0
            else:
                RUNTIME["phase"]+=1
            RUNTIME["started"]=time.monotonic()
    _redraw()
    return .06


class EXCAD_OT_generate(bpy.types.Operator):
    bl_idname="excadmple.generate"
    bl_label="Build .blend phone stand example"
    bl_description="Create a 12-step embedded reference tutorial without clearing your design"
    def execute(self,context):
        build_example(context.scene)
        return {"FINISHED"}


class EXCAD_OT_from_selected(bpy.types.Operator):
    bl_idname="excadmple.from_selected"
    bl_label="Reconstruct from selected objects"
    bl_description="Create a plausible tutorial from objects already in this .blend"
    def execute(self,context):
        try: build_from_selected(context.scene,list(context.selected_objects))
        except Exception as exc:
            self.report({"ERROR"},str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class EXCAD_OT_player(bpy.types.Operator):
    bl_idname="excadmple.player"
    bl_label="Expert playback"
    action: bpy.props.EnumProperty(items=[
        ("PLAY","Play",""),("PAUSE","Pause",""),("NEXT","Next",""),
        ("PREV","Previous",""),("RESTART","Restart",""),("LOAD","Load embedded","")])
    def execute(self,context):
        act=self.action
        try:
            if act=="LOAD":
                _load(context.scene)
            elif not RUNTIME["lesson"]:
                _load(context.scene)
            if act=="PLAY":
                RUNTIME["playing"]=True
                RUNTIME["started"]=time.monotonic()
            elif act=="PAUSE":
                RUNTIME["playing"]=False
            elif act in ("NEXT","PREV","RESTART"):
                RUNTIME["playing"]=False
                RUNTIME["step"] = (0 if act=="RESTART" else
                     max(0,min(len(RUNTIME["lesson"])-1,RUNTIME["step"]+(1 if act=="NEXT" else -1))))
                RUNTIME["phase"]=0
                RUNTIME["started"]=time.monotonic()
                _rebuild(RUNTIME["step"],0)
        except Exception as exc:
            self.report({"ERROR"},str(exc))
            return {"CANCELLED"}
        _redraw()
        return {"FINISHED"}


class EXCAD_PT_panel(bpy.types.Panel):
    bl_label="exCADmple · Virtual Expert"
    bl_idname="EXCAD_PT_panel"
    bl_space_type="VIEW_3D"
    bl_region_type="UI"
    bl_category="exCADmple"
    def draw(self,context):
        layout=self.layout
        layout.label(text="ONE viewport · Two independent models")
        row=layout.row(align=True)
        for action,label,icon in [("PLAY","Play","PLAY"),("PAUSE","Pause","PAUSE"),
                                  ("RESTART","Restart","FILE_REFRESH")]:
            op=row.operator("excadmple.player",text=label,icon=icon)
            op.action=action
        row=layout.row(align=True)
        for action,label in [("PREV","Previous"),("NEXT","Next")]:
            row.operator("excadmple.player",text=label).action=action
        layout.operator("excadmple.player",text="Load embedded .blend lesson").action="LOAD"
        layout.separator()
        layout.operator("excadmple.generate",icon="MESH_CUBE")
        layout.operator("excadmple.from_selected",icon="OUTLINER_OB_MESH")
        layout.separator()
        layout.label(text="Step %d / %d"%(RUNTIME["step"]+1,len(RUNTIME["lesson"])))
        layout.label(text=RUNTIME["status"][:60])
        layout.label(text="Expert model is non-selectable.")
        layout.label(text="Your mouse and tools remain yours.")


CLASSES=(EXCAD_OT_generate,EXCAD_OT_from_selected,EXCAD_OT_player,EXCAD_PT_panel)


@persistent
def _load_after_file_open(_dummy):
    RUNTIME["playing"] = False
    RUNTIME["lesson"] = []
    RUNTIME["models"] = {}
    try:
        if bpy.context.scene and bpy.context.scene.get(LESSON_KEY):
            _load(bpy.context.scene)
    except Exception:
        pass


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    if RUNTIME["handler"] is None:
        RUNTIME["handler"]=bpy.types.SpaceView3D.draw_handler_add(
            _draw,(),"WINDOW","POST_PIXEL")
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick,first_interval=.15,persistent=True)
    if _load_after_file_open not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_load_after_file_open)
    try:
        if bpy.context.scene and bpy.context.scene.get(LESSON_KEY):
            _load(bpy.context.scene)
    except Exception:
        pass


def unregister():
    RUNTIME["playing"]=False
    if RUNTIME["handler"] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(RUNTIME["handler"],"WINDOW")
        RUNTIME["handler"]=None
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    if _load_after_file_open in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_after_file_open)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__=="__main__":
    register()
