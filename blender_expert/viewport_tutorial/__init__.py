"""exCADmple — In-Viewport Extrude Walkthrough (Blender 4.2+).

Install this FOLDER as a ZIP add-on. The virtual expert is drawn by POST_VIEW
and POST_PIXEL GPU callbacks, NOT created as Blender objects and NOT replayed
through bpy.ops. No expert actions are inserted into the user's Undo stack.

The N sidebar contains only playback controls. All operation instruction,
face highlighting, real growing geometry, tool and Why callouts live in the
ONE actual Blender 3D Viewport. User can orbit, select, Edit and Undo normally.
"""
bl_info = {
    "name": "exCADmple: In-Viewport Operation Tutorial",
    "author": "exCADmple research prototype",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > N > exCADmple (playback controls only)",
    "description": "A GPU-only expert demonstrates face selection and extrusion alongside your editable model.",
    "category": "3D View",
}
import time
import bpy
import blf
import gpu
from bpy.props import EnumProperty, FloatProperty
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector
from . import core

RUNTIME = {
    "visible":False, "playing":False, "elapsed":0.0,
    "last_tick":0.0, "area_pointer":None, "scene_pointer":None,
    "draw3d":None, "draw2d":None, "internal_seek":False,
}
_SHADER = None
GHOST = (0.18, 0.69, 0.77, 0.30)
WIRE = (0.25, 0.89, 0.94, 0.86)
SELECT = (1.0, 0.64, 0.16, 0.66)
HINT = (1.0, 0.73, 0.29, 1.0)


def _shader():
    global _SHADER
    if _SHADER is None:
        _SHADER = gpu.shader.from_builtin("UNIFORM_COLOR")
    return _SHADER


def _draw_batch(primitive, points, color):
    if not points:
        return
    shader = _shader()
    batch = batch_for_shader(shader, primitive, {"pos":points})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _quad_triangles(quad):
    return [quad[0],quad[1],quad[2],quad[0],quad[2],quad[3]]


def _scene_matches():
    """Draw only over the viewport that started this lesson, not every pane."""
    if not RUNTIME["visible"]:
        return False
    try:
        ctx = bpy.context
        return (ctx.area and ctx.area.type=="VIEW_3D" and
                ctx.area.as_pointer()==RUNTIME["area_pointer"] and
                ctx.window.scene.as_pointer()==RUNTIME["scene_pointer"])
    except Exception:
        return False


def _mesh_draw(vertices, quads, face_color, line_color):
    triangles=core.quads_to_triangles(vertices,quads)
    _draw_batch("TRIS",triangles,face_color)
    edges=core.unique_edges(vertices,quads)
    lines=[p for a,b in edges for p in (a,b)]
    _draw_batch("LINES",lines,line_color)


def _draw_reference_3d():
    if not _scene_matches():
        return
    snap=core.snapshot(RUNTIME["elapsed"])
    moment=snap["moment"]
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")
    gpu.state.depth_mask_set(False)
    gpu.state.line_width_set(2.4)
    try:
        _mesh_draw(snap["base_vertices"],snap["base_faces"],GHOST,WIRE)
        if snap["wall_faces"]:
            _mesh_draw(snap["wall_vertices"],snap["wall_faces"],
                       (0.22,0.74,0.82,.43),(0.22,.92,.96,.94))
        if moment.index>=1:
            face=snap["face"]
            _draw_batch("TRIS",_quad_triangles(face),SELECT)
            _draw_batch("LINES",
                        [p for i in range(4) for p in (face[i],face[(i+1)%4])],
                        (1,.83,.36,1))
        # Visually show the selected face advancing along the Z axis.
        if moment.index>=2:
            end=core.BASE_THICKNESS+snap["height"]
            cx=core.OFFSET_X
            cy=(core.REAR_START_Y+core.REAR_END_Y)*.5
            _draw_batch("LINES",[(cx,cy,core.BASE_THICKNESS),
                                 (cx,cy,end+.34)],(1,.81,.25,1))
            arrow_len=.13
            _draw_batch("LINES",
                        [(cx,cy,end+.34),(cx-arrow_len,cy,end+.17),
                         (cx,cy,end+.34),(cx+arrow_len,cy,end+.17)],
                        HINT)
    finally:
        gpu.state.line_width_set(1)
        gpu.state.depth_mask_set(True)
        gpu.state.depth_test_set("NONE")
        gpu.state.blend_set("NONE")


def _rect(x,y,w,h,color):
    points=[(x,y),(x+w,y),(x+w,y+h),(x,y),
            (x+w,y+h),(x,y+h)]
    _draw_batch("TRIS",points,color)


def _text(x,y,message,size=14,color=(.94,.97,.99,1)):
    font=0
    blf.size(font,size)
    blf.color(font,*color)
    blf.position(font,x,y,0)
    blf.draw(font,str(message))


def _segment(a,b,color):
    _draw_batch("LINES",[a,b],color)


def _viewport_anchor(snap):
    ctx=bpy.context
    try:
        return location_3d_to_region_2d(ctx.region,ctx.space_data.region_3d,
                                         Vector(snap["anchor"]))
    except Exception:
        return None


def _draw_reference_2d():
    if not _scene_matches():
        return
    region=bpy.context.region
    if not region or region.type!="WINDOW":
        return
    s=core.snapshot(RUNTIME["elapsed"])
    moment=s["moment"]
    w,h=region.width,region.height
    anchor=_viewport_anchor(s)
    if anchor is None:
        anchor=(w*.60,h*.45)
    else:
        anchor=(float(anchor.x),float(anchor.y))
    # Genuine geometry anchoring, not a fixed sidebar/text transcript.
    box_w=min(360,max(235,w*.47))
    box_h=159 if moment.name=="why" else 137
    x=core.clamp(anchor[0]+36,18,max(18,w-box_w-18))
    y=core.clamp(anchor[1]+60,70,max(70,h-box_h-20))
    gpu.state.blend_set("ALPHA")
    gpu.state.line_width_set(2)
    try:
        _segment(anchor,(x,y+48),(.98,.72,.35,.85))
        _rect(x-3,y-3,box_w+6,box_h+6,(.04,.08,.12,.63))
        _rect(x,y,box_w,box_h,(.07,.105,.14,.94))
        _rect(x,y+box_h-5,box_w,5,(.93,.63,.20,.9))
        _text(x+14,y+box_h-32,"EXPERT DEMONSTRATION  ·  %s / %s" %
              (moment.index+1,len(core.PHASES)),11,(.99,.75,.36,1))
        _text(x+14,y+box_h-57,moment.title,16)
        _text(x+14,y+box_h-83,moment.hint[:56],12,(.83,.90,.95,1))
        if moment.name=="tool":
            _rect(x+14,y+23,50,34,(.94,.63,.21,.99))
            _text(x+26,y+33,"E",21,(.08,.11,.13,1))
            _text(x+78,y+43,"BLENDER · EXTRUDE REGION",12,(.96,.83,.59,1))
            _text(x+78,y+26,"Edit Mode > Face Select > E",11,(.80,.87,.91,1))
        elif moment.name=="face":
            _text(x+14,y+27,"ORANGE FACE = NEXT CLICK",12,(1,.79,.42,1))
        elif moment.name=="extrude":
            _rect(x+14,y+19,(box_w-28)*moment.fraction,7,(1,.75,.35,.95))
            _text(x+14,y+38,"HEIGHT  %.2f / %.2f Blender units" %
                  (s["height"],core.EXTRUDE_DISTANCE),12,(1,.78,.44,1))
        elif moment.name=="parameter":
            _rect(x+14,y+20,137,38,(.15,.22,.28,.98))
            _text(x+28,y+33,"Distance: 2.4",16,(1,.81,.48,1))
            _text(x+163,y+34,"[ Enter ]  CONFIRM",11,(.81,.93,.87,1))
        elif moment.name=="why":
            _text(x+14,y+40,"AUTHORED DEMO REASONING",11,(1,.75,.36,1))
            _text(x+14,y+23,"Not an inferred or recorded human decision",11,(.75,.84,.88,1))
        _text(x+14,y+7,("PLAYING" if RUNTIME["playing"] else "PAUSED")+
              " · GPU reference only",10,(.58,.74,.78,1))
        # Keep the expert and learner visually distinct without rewriting
        # Blender's real tools or obscuring the modeling canvas.
        _rect(17,h-55,260,36,(.08,.17,.21,.80))
        _text(27,h-41,"REFERENCE  ·  VIRTUAL EXPERT",12,(.42,.94,.93,1))
        _text(27,h-53,"Your real model remains editable",10,(.77,.84,.88,1))
    finally:
        gpu.state.line_width_set(1)
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
    if RUNTIME["playing"]:
        now=time.monotonic()
        delta=max(0.0,min(.15,now-RUNTIME["last_tick"]))
        RUNTIME["last_tick"]=now
        # Changes only a Python float. There is no bpy.data scene mutation,
        # history entry, synthetic input or native operator replay.
        try:
            wm=bpy.context.window_manager
            speed=float(wm.excad_viewport_speed)
        except Exception:
            wm=None
            speed=1.0
        RUNTIME["elapsed"]=min(core.TOTAL_SECONDS,
                              RUNTIME["elapsed"]+delta*speed)
        if RUNTIME["elapsed"]>=core.TOTAL_SECONDS:
            RUNTIME["playing"]=False
        if wm is not None and abs(wm.excad_viewport_time-RUNTIME["elapsed"])>.075:
            RUNTIME["internal_seek"]=True
            try:
                wm.excad_viewport_time=RUNTIME["elapsed"]
            finally:
                RUNTIME["internal_seek"]=False
        _redraw()
    return 1.0/30.0


def _set_time(value):
    RUNTIME["elapsed"]=max(0.0,min(core.TOTAL_SECONDS,float(value)))
    RUNTIME["last_tick"]=time.monotonic()
    RUNTIME["visible"]=True
    try:
        wm=bpy.context.window_manager
        RUNTIME["internal_seek"]=True
        wm.excad_viewport_time=RUNTIME["elapsed"]
    except Exception:
        pass
    finally:
        RUNTIME["internal_seek"]=False
    _redraw()


def _begin_in_area(context):
    if not context.area or context.area.type!="VIEW_3D":
        raise RuntimeError("Use playback from the 3D View sidebar")
    RUNTIME["area_pointer"]=context.area.as_pointer()
    RUNTIME["scene_pointer"]=context.window.scene.as_pointer()
    RUNTIME["visible"]=True


def _on_seek(self,context):
    if RUNTIME["internal_seek"]:
        return
    RUNTIME["playing"]=False
    _set_time(context.window_manager.excad_viewport_time)


class EXCADV_OT_playback(bpy.types.Operator):
    bl_idname="view3d.excad_viewport_playback"
    bl_label="exCADmple playback"
    bl_options={"INTERNAL"}
    action:EnumProperty(name="Action",items=[
        ("PLAY","Play",""),("PAUSE","Pause",""),("PREV","Previous",""),
        ("NEXT","Next",""),("RESTART","Restart",""),("HIDE","Hide","")])
    def execute(self,context):
        try:
            if self.action!="HIDE":
                _begin_in_area(context)
            if self.action=="PLAY":
                if RUNTIME["elapsed"]>=core.TOTAL_SECONDS:
                    _set_time(0.0)
                RUNTIME["playing"]=True
                RUNTIME["last_tick"]=time.monotonic()
            elif self.action=="PAUSE":
                RUNTIME["playing"]=False
            elif self.action=="HIDE":
                RUNTIME["playing"]=False
                RUNTIME["visible"]=False
            elif self.action=="RESTART":
                RUNTIME["playing"]=False
                _set_time(0.0)
            elif self.action in ("PREV","NEXT"):
                RUNTIME["playing"]=False
                m=core.moment_at(RUNTIME["elapsed"])
                if self.action=="NEXT":
                    dest=min(len(core.PHASES)-1,m.index+1)
                else:
                    dest=m.index-1 if RUNTIME["elapsed"]-m.start<.28 else m.index
                _set_time(core.moment_start(max(0,dest)))
            _redraw()
            return {"FINISHED"}
        except Exception as error:
            self.report({"ERROR"},str(error))
            return {"CANCELLED"}


class EXCADV_OT_create_practice(bpy.types.Operator):
    bl_idname="view3d.excad_create_practice_base"
    bl_label="exCADmple: Create Practice Base"
    bl_description="Explicitly create YOUR editable subdivided base at origin (one Undo operation)"
    bl_options={"REGISTER","UNDO"}
    @classmethod
    def poll(cls,context):
        return context.mode=="OBJECT" and context.scene is not None
    def execute(self,context):
        vertices,faces=core.practice_base_mesh()
        mesh=bpy.data.meshes.new("Practice base · editable topology")
        mesh.from_pydata(vertices,[],faces)
        mesh.update()
        obj=bpy.data.objects.new("PRACTICE | Rear strip can be extruded",mesh)
        context.collection.objects.link(obj)
        # Explicit user action: this one object belongs to learner history.
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active=obj
        self.report({"INFO"},"Created learner base; Tab, 3 (Face Select), select rear top face, E, 2.4, Enter")
        return {"FINISHED"}


class EXCADV_OT_frame_both(bpy.types.Operator):
    bl_idname="view3d.excad_frame_both"
    bl_label="exCADmple: Frame Both Models"
    bl_description="Reframe the camera ONLY when you explicitly request it"
    bl_options={"INTERNAL"}
    @classmethod
    def poll(cls,context):
        return context.area and context.area.type=="VIEW_3D"
    def execute(self,context):
        space=context.area.spaces.active
        region_3d=space.region_3d
        region_3d.view_location=(core.OFFSET_X/2,0,1.1)
        region_3d.view_distance=13.8
        context.area.tag_redraw()
        return {"FINISHED"}


class EXCADV_PT_playback(bpy.types.Panel):
    bl_label="exCADmple · Playback"
    bl_idname="EXCADV_PT_playback"
    bl_space_type="VIEW_3D"
    bl_region_type="UI"
    bl_category="exCADmple"
    def draw(self,context):
        l=self.layout
        row=l.row(align=True)
        for action,icon in (("PLAY","PLAY"),("PAUSE","PAUSE"),("RESTART","FILE_REFRESH")):
            row.operator("view3d.excad_viewport_playback",text="",icon=icon).action=action
        row=l.row(align=True)
        for action,label in (("PREV","Previous"),("NEXT","Next")):
            row.operator("view3d.excad_viewport_playback",text=label).action=action
        l.prop(context.window_manager,"excad_viewport_time",text="Seek",slider=True)
        l.prop(context.window_manager,"excad_viewport_speed",text="Speed")
        l.operator("view3d.excad_viewport_playback",text="Hide expert",icon="HIDE_OFF").action="HIDE"


CLASSES=(EXCADV_OT_playback,EXCADV_OT_create_practice,
         EXCADV_OT_frame_both,EXCADV_PT_playback)


@persistent
def _after_load(_dummy):
    # File switches must never let an old expert overlay leak to a new design.
    RUNTIME["playing"]=False
    RUNTIME["visible"]=False
    RUNTIME["elapsed"]=0.0
    RUNTIME["area_pointer"]=None
    RUNTIME["scene_pointer"]=None


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.excad_viewport_time=FloatProperty(
        name="Seek",default=0.0,min=0.0,max=core.TOTAL_SECONDS,
        precision=1,subtype="TIME",update=_on_seek)
    bpy.types.WindowManager.excad_viewport_speed=FloatProperty(
        name="Speed",default=1.0,min=.25,max=2.0)
    if not bpy.app.background:
        if RUNTIME["draw3d"] is None:
            RUNTIME["draw3d"]=bpy.types.SpaceView3D.draw_handler_add(
                _draw_reference_3d,(),"WINDOW","POST_VIEW")
        if RUNTIME["draw2d"] is None:
            RUNTIME["draw2d"]=bpy.types.SpaceView3D.draw_handler_add(
                _draw_reference_2d,(),"WINDOW","POST_PIXEL")
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick,first_interval=.05,persistent=True)
    if _after_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_after_load)


def unregister():
    RUNTIME["playing"]=False
    RUNTIME["visible"]=False
    for key in ("draw3d","draw2d"):
        if RUNTIME[key] is not None:
            bpy.types.SpaceView3D.draw_handler_remove(RUNTIME[key],"WINDOW")
            RUNTIME[key]=None
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    if _after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_after_load)
    if hasattr(bpy.types.WindowManager,"excad_viewport_time"):
        del bpy.types.WindowManager.excad_viewport_time
    if hasattr(bpy.types.WindowManager,"excad_viewport_speed"):
        del bpy.types.WindowManager.excad_viewport_speed
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__=="__main__":
    register()
