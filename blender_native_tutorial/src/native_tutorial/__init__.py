"""exCADmple — Blender-native interactive software tutorial.

The virtual expert's results come from ACTUAL built-in Blender bpy.ops
executed in an isolated background Blender process. All pedagogical cues
and frames are drawn in one genuine Blender 3D viewport with POST_VIEW and
POST_PIXEL. Learner edits use genuine native tools and their own Undo.

The N sidebar is ONLY a playback controller and a lesson-import control.
The source operation history is authored JSON; no recorder is required.
"""
bl_info={
    'name':'exCADmple: Native Blender Interactive Tutorial',
    'author':'exCADmple research prototype',
    'version':(1,1,0),
    'blender':(4,2,0),
    'location':'3D View > Sidebar > exCADmple (playback controls)',
    'description':'Native Blender operation walkthrough in the SAME viewport while you keep modeling',
    'category':'3D View',
}
import bpy
import blf
import gpu
import math
import sys
import time
import subprocess
import hashlib
from pathlib import Path
from bpy.app.handlers import persistent
from bpy.props import EnumProperty, FloatProperty
from gpu_extras.batch import batch_for_shader
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector
from . import engine
from .starter import practice_mesh

REF_OFFSET=(5.2,0.0,0.0)
S={
    'lesson':None,'playing':False,'visible':False,'explore':False,
    'elapsed':0.0,'last_tick':0.0,'area_id':None,'window_id':None,
    'draw3d':None,'draw2d':None,'worker':None,'log_handle':None,
    'log_path':None,'compiled_path':None,'spec':None,'autoplay':False,
    'status':'Press Play to prepare the native operation walkthrough',
    'error':None,'changing_seek':False,
}
SHADER=None
COLOR_FACES=(.17,.74,.81,.25)
COLOR_SELECTED=(1.0,.62,.13,.72)
COLOR_LINES=(.30,.87,.95,.78)
COLOR_EDGES=(1.0,.77,.22,1.0)


def _spec_path():
    return S['spec'] or Path(__file__).resolve().parent/'lesson.json'


def _cache_path(spec):
    source=Path(spec).read_bytes()
    fingerprint=hashlib.sha256(source+str(bpy.app.version).encode()).hexdigest()[:20]
    parent=Path(bpy.utils.user_resource('CONFIG'))/'excadmple'/'native_tutorial'
    parent.mkdir(parents=True,exist_ok=True)
    return parent/('native_'+fingerprint+'.json')


def _begin_compile():
    if S['worker'] is not None:return
    spec=Path(_spec_path()).resolve()
    engine.read_spec(spec)
    compiled=_cache_path(spec)
    S['compiled_path']=compiled
    if compiled.exists():
        try:
            S['lesson']=engine.read_compiled(compiled)
            S['status']='Native Blender operators loaded'
            if S['autoplay']:_play()
            return
        except Exception:
            compiled.unlink(missing_ok=True)
    binary=Path(bpy.app.binary_path)
    if not binary.is_file():
        raise RuntimeError('Cannot locate Blender executable to compile isolated native modeling operations')
    compiler=Path(__file__).resolve().parent/'compiler_cli.py'
    log_path=compiled.with_suffix('.log')
    log=open(log_path,'w',encoding='utf8')
    try:
        command=[str(binary),'--background','--factory-startup','--python',
                 str(compiler),'--','--spec',str(spec),'--output',str(compiled)]
        child=subprocess.Popen(command,stdin=subprocess.DEVNULL,
                               stdout=log,stderr=subprocess.STDOUT,
                               close_fds=True)
    except Exception:
        log.close()
        raise
    S['worker']=child
    S['log_handle']=log
    S['log_path']=log_path
    S['status']='Compiling actual Blender operations in an isolated Blender process…'
    S['error']=None


def _poll_compile():
    proc=S['worker']
    if proc is None:return
    code=proc.poll()
    if code is None:return
    S['worker']=None
    if S['log_handle']:
        S['log_handle'].close()
        S['log_handle']=None
    if code==0 and S['compiled_path'].exists():
        try:
            S['lesson']=engine.read_compiled(S['compiled_path'])
            S['status']='Ready — original Blender operators, sampled in isolation'
            S['error']=None
            if S['autoplay']:_play()
            return
        except Exception as exc:
            S['error']='Native lesson data invalid: '+str(exc)
    else:
        try:
            log=S['log_path'].read_text(encoding='utf8',errors='replace')
            message=' | '.join(log.splitlines()[-5:])[-380:]
        except Exception:message='No compiler log available'
        S['error']=f'Native Blender compiler failed (exit {code}): {message}'
    S['status']='Could not load the native tutorial. Inspect error in playback panel.'
    S['autoplay']=False


def _play():
    if not S['lesson']:
        S['autoplay']=True
        _begin_compile()
        return
    if S['elapsed']>=engine.total_seconds(S['lesson']):S['elapsed']=0.0
    S['playing']=True
    S['visible']=True
    S['explore']=False
    S['last_tick']=time.monotonic()
    _redraw()


def _time_set(t):
    if not S['lesson']:return
    S['elapsed']=max(0.0,min(float(t),engine.total_seconds(S['lesson'])))
    S['playing']=False
    S['visible']=True
    S['last_tick']=time.monotonic()
    _slider_sync()
    _redraw()


def _slider_sync():
    if not S['lesson']:return
    try:
        wm=bpy.context.window_manager
        amount=S['elapsed']/max(.001,engine.total_seconds(S['lesson']))
        S['changing_seek']=True
        wm.excadmple_scrub=amount
    except Exception:pass
    finally:S['changing_seek']=False


def _on_scrub(self,context):
    if S['changing_seek'] or not S['lesson']:return
    _time_set(context.window_manager.excadmple_scrub*engine.total_seconds(S['lesson']))


def _tick():
    _poll_compile()
    if S['playing'] and S['lesson']:
        now=time.monotonic()
        delta=max(0.0,min(.12,now-S['last_tick']))
        S['last_tick']=now
        try:speed=float(bpy.context.window_manager.excadmple_speed)
        except Exception:speed=1
        S['elapsed']=min(engine.total_seconds(S['lesson']),S['elapsed']+delta*speed)
        if S['elapsed']>=engine.total_seconds(S['lesson']):S['playing']=False
        _slider_sync()
        _redraw()
    return .035


def _redraw():
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type=='VIEW_3D':area.tag_redraw()
    except Exception:pass


def _view_is_target():
    if not S['visible'] or not S['lesson']:return False
    try:
        c=bpy.context
        return bool(c.area and c.area.type=='VIEW_3D' and
                    c.area.as_pointer()==S['area_id'] and
                    c.window.as_pointer()==S['window_id'] and
                    c.region and c.region.type=='WINDOW')
    except Exception:return False


def _frame_data():
    if not S['lesson']:return None
    p=engine.position(S['lesson'],S['elapsed'])
    return p,engine.triangles(p['frame'])


def _shader():
    global SHADER
    if SHADER is None:SHADER=gpu.shader.from_builtin('UNIFORM_COLOR')
    return SHADER


def _batch(kind,positions,color):
    if not positions:return
    vertices=[(p[0]+REF_OFFSET[0],p[1]+REF_OFFSET[1],p[2]+REF_OFFSET[2]) for p in positions]
    shader=_shader()
    batch=batch_for_shader(shader,kind,{'pos':vertices})
    shader.bind()
    shader.uniform_float('color',color)
    batch.draw(shader)


def _draw_3d():
    if not _view_is_target():return
    info=_frame_data()
    if not info:return
    p,(solid,selected,edges)=info
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(False)
    try:
        _batch('TRIS',solid,COLOR_FACES)
        _batch('TRIS',selected,COLOR_SELECTED)
        _batch('LINES',edges,COLOR_LINES)
        s=p['frame']
        colored=[]
        for a,b in s.get('selected_edges',[]):
            vs=s['vertices']
            if a<len(vs) and b<len(vs):colored.extend((vs[a],vs[b]))
        _batch('LINES',colored,COLOR_EDGES)
        if p['stage']=='OPERATE' and p['step']['operator']=='mesh.extrude_region_move':
            tgt=engine.selected_centroid(p['frame'])
            end=(tgt[0],tgt[1],tgt[2]+.25)
            _batch('LINES',[tgt,end],(1,.76,.20,1))
    finally:
        gpu.state.depth_mask_set(True)
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('NONE')


def _rect(x,y,w,h,color):
    shader=_shader()
    verts=[(x,y),(x+w,y),(x+w,y+h),(x,y),
           (x+w,y+h),(x,y+h)]
    batch=batch_for_shader(shader,'TRIS',{'pos':verts})
    shader.bind()
    shader.uniform_float('color',color)
    batch.draw(shader)


def _line(points,color):
    shader=_shader()
    batch=batch_for_shader(shader,'LINES',{'pos':points})
    shader.bind();shader.uniform_float('color',color);batch.draw(shader)


def _font(x,y,value,size=12,color=(.93,.97,.99,1)):
    blf.size(0,size)
    blf.color(0,*color)
    blf.position(0,x,y,0)
    blf.draw(0,str(value))


def _wrap(value,width=47,lines=3):
    words=str(value).split()
    output=['']
    for word in words:
        candidate=(output[-1]+' '+word).strip()
        if len(candidate)>width and output[-1]:output.append(word)
        else:output[-1]=candidate
    return output[:lines]


def _draw_2d():
    if not _view_is_target():return
    p=engine.position(S['lesson'],S['elapsed'])
    step=p['step'];frame=p['frame'];stage=p['stage']
    ctx=bpy.context;region=ctx.region
    if not region:return
    center=engine.selected_centroid(frame)
    point=Vector((center[0]+REF_OFFSET[0],center[1]+REF_OFFSET[1],center[2]+REF_OFFSET[2]))
    try:anchor=location_3d_to_region_2d(region,ctx.space_data.region_3d,point)
    except Exception:anchor=None
    x0,y0=(anchor.x,anchor.y) if anchor else (region.width*.60,region.height*.40)
    boxw=min(408,max(235,region.width*.48))
    boxh=167 if stage=='WHY' else 145
    left=max(12,min(region.width-boxw-12,x0+33))
    bottom=max(65,min(region.height-boxh-22,y0+40))
    gpu.state.blend_set('ALPHA')
    try:
        # Strong spatial anchor on the actual selected geometry, not a side tutorial.
        _line([(x0,y0),(left,bottom+boxh-55)],(.96,.73,.30,.87))
        _rect(left-3,bottom-3,boxw+6,boxh+6,(.015,.035,.055,.58))
        _rect(left,bottom,boxw,boxh,(.06,.10,.14,.94))
        _rect(left,bottom+boxh-5,boxw,5,(.95,.65,.23,1))
        _font(left+13,bottom+boxh-26,f'EXCADMPLE · {p["index"]+1}/{len(S["lesson"]["steps"])} · {stage}',10,(1,.75,.31,1))
        _font(left+13,bottom+boxh-49,step.get('title','Blender Operation')[:52],15)
        if stage=='TOOL':
            _rect(left+13,bottom+27,66,37,(.94,.63,.19,1))
            _font(left+23,bottom+38,step.get('shortcut','')[:8],17,(.06,.10,.13,1))
            _font(left+92,bottom+50,step.get('tool','Blender operator')[:35],13,(1,.88,.61,1))
            _font(left+92,bottom+32,step.get('operator','')[:36],11)
            _font(left+13,bottom+12,'BLENDER BUILT-IN TOOL · THIS IS NOT A NEW CAD OPERATOR',9,(.62,.78,.81,1))
        elif stage=='SELECT':
            _font(left+13,bottom+69,'Select the highlighted original mesh geometry',12,(1,.79,.42,1))
            _font(left+13,bottom+45,step.get('select','').replace('_',' ').upper(),11)
            _font(left+13,bottom+23,'Use Blender Face/Edge Select, then activate the tool',11)
        elif stage=='OPERATE':
            _font(left+13,bottom+63,'Source geometry computed by Blender native bpy.ops',11,(.74,.92,.93,1))
            amount=', '.join(f'{k} = {v}' for k,v in step.get('args',{}).items())
            _font(left+13,bottom+43,amount[:61],11,(1,.8,.46,1))
            frac=p['fraction'];progress=min(1,max(0,(frac-.32)/(.79-.32)))
            _rect(left+13,bottom+22,(boxw-26)*progress,6,(.93,.71,.28,1))
        elif stage=='PARAMETER':
            amount=', '.join(f'{k} = {v}' for k,v in step.get('args',{}).items())
            _rect(left+13,bottom+25,boxw-26,35,(.13,.19,.25,1))
            _font(left+22,bottom+38,amount[:57],14,(1,.82,.46,1))
            _font(left+13,bottom+12,'Blender native input → Enter to confirm',10)
        else:
            _font(left+13,bottom+83,'DESIGN REASONING · '+step.get('why_source','')[:30],11,(1,.74,.35,1))
            for i,line in enumerate(_wrap(step.get('why','No authored reasoning for this operation'),49,3)):
                _font(left+13,bottom+63-i*17,line,11)
            _font(left+13,bottom+10,'Reason comes from tutorial author, not inferred from the model',9,(.66,.78,.83,1))
        # The learner sees the intended click target. This guidance cursor
        # is drawn in the viewport and never injects a mouse event or
        # pretends to be a recording of the original designer's clicks.
        phase_fraction=p['fraction']
        sx,sy=(left+47,bottom+44)
        if stage=='TOOL':
            px,py=(sx,sy)
        elif stage=='SELECT':
            t=max(0,min(1,(phase_fraction-.16)/.16))
            px=sx+(x0-sx)*t
            py=sy+(y0-sy)*t
        else:
            px,py=(x0,y0)
        _line([(px,py),(px+11,py-15),(px+13,py-8),
               (px+21,py-8),(px,py)],(.97,.86,.52,1))
        _font(px+16,py-25,'GUIDE',9,(.98,.82,.38,1))
        if stage in ('SELECT','OPERATE'):
            _line([(x0-10,y0),(x0+10,y0),(x0,y0-10),(x0,y0+10)],
                  (.99,.74,.27,.86))
        _rect(12,region.height-51,222,35,(.06,.15,.19,.81))
        _font(22,region.height-34,'VIRTUAL EXPERT · REFERENCE',11,(.4,.94,.95,1))
        _font(22,region.height-47,'Your real Blender model stays editable',9)
    finally:
        gpu.state.blend_set('NONE')


def _start_in_context(context):
    if context.area is None or context.area.type!='VIEW_3D':
        raise RuntimeError('Run from a Blender 3D View')
    S['area_id']=context.area.as_pointer()
    S['window_id']=context.window.as_pointer()
    S['visible']=True


class EXCAD_OT_transport(bpy.types.Operator):
    bl_idname='view3d.excad_native_transport'
    bl_label='exCADmple Playback'
    bl_options={'INTERNAL'}
    action:EnumProperty(items=[(v,v.title(),'') for v in (
        'PLAY','PAUSE','PREVIOUS','NEXT','REPEAT','RESTART','EXPLORE','HIDE')])
    def execute(self,context):
        try:
            if self.action!='HIDE':_start_in_context(context)
            if self.action=='PLAY':_play()
            elif self.action=='PAUSE':S['playing']=False
            elif self.action=='PREVIOUS' and S['lesson']:
                p=engine.position(S['lesson'],S['elapsed'])
                i=max(0,p['index']-(1 if p['local_seconds']<.5 else 0))
                _time_set(engine.step_start(S['lesson'],i))
            elif self.action=='NEXT' and S['lesson']:
                i=engine.position(S['lesson'],S['elapsed'])['index']
                _time_set(engine.step_start(S['lesson'],min(i+1,len(S['lesson']['steps'])-1)))
            elif self.action=='REPEAT' and S['lesson']:
                i=engine.position(S['lesson'],S['elapsed'])['index']
                _time_set(engine.step_start(S['lesson'],i));_play()
            elif self.action=='RESTART':_time_set(0)
            elif self.action=='EXPLORE' and S['lesson']:
                S['playing']=False
                S['explore']=not S['explore']
                if S['explore']:S['elapsed']=engine.total_seconds(S['lesson'])
                _slider_sync()
            elif self.action=='HIDE':
                S['playing']=False;S['visible']=False
            _redraw()
            return {'FINISHED'}
        except Exception as error:
            S['status']='Error preparing Blender native tutorial'
            S['error']=str(error)
            self.report({'ERROR'},str(error))
            return {'CANCELLED'}


class EXCAD_OT_practice(bpy.types.Operator):
    bl_idname='view3d.excad_native_practice'
    bl_label='exCADmple: Create Editable Practice Base'
    bl_description='Explicitly create your OWN mesh (normal Blender Undo action)'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and context.scene is not None
    def execute(self,context):
        verts,faces=practice_mesh()
        mesh=bpy.data.meshes.new('Phone stand lesson · learner mesh')
        mesh.from_pydata(verts,[],faces);mesh.update()
        obj=bpy.data.objects.new('MY PHONE STAND | Editable',mesh)
        context.collection.objects.link(obj)
        for selected in context.selected_objects:selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active=obj
        self.report({'INFO'},'Real Blender Edit Mode: Tab, Face Select (3), select rear strip, E, 2.4')
        return {'FINISHED'}


class EXCAD_OT_frame(bpy.types.Operator):
    bl_idname='view3d.excad_native_frame'
    bl_label='exCADmple: Frame Learner and Expert'
    bl_description='Frame both parts only if you explicitly choose this action'
    bl_options={'INTERNAL'}
    def execute(self,context):
        if context.area is None or context.area.type!='VIEW_3D':return {'CANCELLED'}
        view=context.area.spaces.active.region_3d
        view.view_location=(REF_OFFSET[0]/2,0,1.25)
        view.view_distance=14.8
        context.area.tag_redraw()
        return {'FINISHED'}


class EXCAD_OT_import(bpy.types.Operator):
    bl_idname='view3d.excad_native_import'
    bl_label='Import Native Blender Tutorial'
    bl_description='Import a safe authored JSON sequence of existing Blender operators'
    filepath:bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob:bpy.props.StringProperty(default='*.json',options={'HIDDEN'})
    def invoke(self,context,event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    def execute(self,context):
        try:
            engine.read_spec(self.filepath)
            if S['worker'] is not None:
                raise RuntimeError('Finish or cancel current native lesson compilation first')
            S['playing']=False;S['lesson']=None;S['elapsed']=0
            S['spec']=Path(self.filepath).resolve()
            S['autoplay']=False
            S['status']='Authored native operation lesson selected — Play to compile'
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'},str(e));return {'CANCELLED'}


class EXCAD_PT_player(bpy.types.Panel):
    bl_label='exCADmple · Playback'
    bl_idname='EXCAD_PT_native_player'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='exCADmple'
    def draw(self,context):
        l=self.layout
        row=l.row(align=True)
        for action,icon in [('PREVIOUS','BACK'),('PLAY','PLAY'),('PAUSE','PAUSE'),('NEXT','FORWARD')]:
            row.operator(EXCAD_OT_transport.bl_idname,text='',icon=icon).action=action
        row=l.row(align=True)
        for action,name in [('REPEAT','Repeat'),('RESTART','Reset'),('EXPLORE','Explore')]:
            row.operator(EXCAD_OT_transport.bl_idname,text=name).action=action
        l.prop(context.window_manager,'excadmple_scrub',text='Timeline',slider=True)
        l.prop(context.window_manager,'excadmple_speed',text='Speed')
        row=l.row(align=True)
        row.operator(EXCAD_OT_import.bl_idname,text='Import',icon='FILE_FOLDER')
        row.operator(EXCAD_OT_transport.bl_idname,text='Hide',icon='HIDE_OFF').action='HIDE'
        if S['worker'] is not None:
            l.label(text='Compiling native Blender operations…',icon='TIME')
        elif S['error']:
            l.label(text='Compilation failed — see error below',icon='ERROR')
            for line in _wrap(S['error'],35,5):l.label(text=line[:35])


CLASSES=(EXCAD_OT_transport,EXCAD_OT_practice,EXCAD_OT_frame,EXCAD_OT_import,EXCAD_PT_player)


@persistent
def _file_loaded(_dummy):
    S['playing']=False;S['visible']=False;S['area_id']=None;S['window_id']=None
    S['elapsed']=0.0


def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.WindowManager.excadmple_scrub=FloatProperty(
        name='Timeline',min=0,max=1,default=0,update=_on_scrub)
    bpy.types.WindowManager.excadmple_speed=FloatProperty(
        name='Speed',min=.25,max=3,default=1)
    if not bpy.app.background:
        S['draw3d']=bpy.types.SpaceView3D.draw_handler_add(_draw_3d,(),'WINDOW','POST_VIEW')
        S['draw2d']=bpy.types.SpaceView3D.draw_handler_add(_draw_2d,(),'WINDOW','POST_PIXEL')
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick,first_interval=.05,persistent=True)
    if _file_loaded not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_file_loaded)


def unregister():
    S['playing']=False;S['visible']=False
    worker=S.get('worker')
    if worker and worker.poll() is None:
        worker.terminate()
    S['worker']=None
    if S['log_handle']:
        S['log_handle'].close();S['log_handle']=None
    for name in ('draw3d','draw2d'):
        if S[name] is not None:
            bpy.types.SpaceView3D.draw_handler_remove(S[name],'WINDOW');S[name]=None
    if bpy.app.timers.is_registered(_tick):bpy.app.timers.unregister(_tick)
    if _file_loaded in bpy.app.handlers.load_post:bpy.app.handlers.load_post.remove(_file_loaded)
    for prop in ('excadmple_scrub','excadmple_speed'):
        if hasattr(bpy.types.WindowManager,prop):delattr(bpy.types.WindowManager,prop)
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
