"""Pure data/schema + timeline core. No Blender APIs and no CAD algorithms.

Geometry frames are built by native Blender operators in a SEPARATE background
Blender process. Playback only reads these snapshots, without editing the
learner's Scene, Timeline, active native tool or Undo stack.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

FORMAT = 'excadmple.native-ops.v1'
COMPILED_FORMAT = 'excadmple.native-compiled.v1'
ALLOWED = {
    'mesh.extrude_region_move': {'distance'},
    'mesh.bevel': {'offset', 'segments'},
    'mesh.inset': {'thickness', 'depth'},
    'transform.translate': {'value'},
    'transform.rotate': {'angle', 'orient_axis'},
    'transform.resize': {'value'},
    'mesh.subdivide': {'number_cuts'},
}
SELECTORS = {'rear_top_face', 'front_top_face', 'highest_edges', 'all_faces', 'all_verts'}
STAGES = (('TOOL',0.00,0.16),('SELECT',0.16,0.32),('OPERATE',0.32,0.79),
          ('PARAMETER',0.79,0.90),('WHY',0.90,1.00))
MAX_STEPS=80
MAX_FRAMES=28


def _finite(x):
    return isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x)


def validate_spec(data):
    if not isinstance(data,dict) or data.get('format')!=FORMAT:
        raise ValueError('Expected excadmple.native-ops.v1 lesson')
    steps=data.get('steps')
    if not isinstance(steps,list) or not 1<=len(steps)<=MAX_STEPS:
        raise ValueError('Lesson requires 1–80 authored native operations')
    identifiers=set()
    for i,step in enumerate(steps):
        if not isinstance(step,dict): raise ValueError('Step must be an object')
        ident=step.get('id')
        if not isinstance(ident,str) or not ident or ident in identifiers:
            raise ValueError('Nonempty unique step IDs required')
        identifiers.add(ident)
        operator=step.get('operator')
        if operator not in ALLOWED: raise ValueError(f'Native operator not permitted: {operator}')
        if step.get('select') not in SELECTORS:
            raise ValueError(f'Invalid geometric selection in step {ident}')
        if step.get('mode')!='EDIT_MESH':
            raise ValueError('MVP supports genuine native mesh-edit operators only')
        args=step.get('args')
        if not isinstance(args,dict) or set(args)-ALLOWED[operator]:
            raise ValueError('Unsupported native Blender operator arguments')
        for key,v in args.items():
            if isinstance(v,(list,tuple)):
                if len(v)!=3 or any(not _finite(n) or abs(n)>10000 for n in v):
                    raise ValueError(f'Invalid vector for {key}')
            elif isinstance(v,str):
                if key!='orient_axis' or v not in ('X','Y','Z'):
                    raise ValueError(f'Invalid string parameter {key}')
            elif not _finite(v) or abs(v)>10000:
                raise ValueError(f'Nonfinite or unsupported parameter {key}')
        duration=step.get('duration',10)
        if not _finite(duration) or not 2<=duration<=120:
            raise ValueError('Step duration must be 2–120 seconds')
        for key in ('title','tool','shortcut','why'):
            if not isinstance(step.get(key,''),str) or len(step.get(key,''))>500:
                raise ValueError(f'Invalid {key} text')
        if step.get('why') and step.get('why_source') not in ('authored-example','author-recorded','author-written'):
            raise ValueError('Reasoning requires explicit provenance')
    return data


def validate_compiled(data):
    if not isinstance(data,dict) or data.get('format')!=COMPILED_FORMAT:
        raise ValueError('Not a native Blender compiled walkthrough')
    steps=data.get('steps',[])
    if not isinstance(steps,list) or not 1<=len(steps)<=MAX_STEPS:
        raise ValueError('Missing compiled operations')
    for step in steps:
        frames=step.get('frames',[])
        if not isinstance(frames,list) or not 3<=len(frames)<=MAX_FRAMES:
            raise ValueError('Missing native operator sampled geometry')
        for frame in frames:
            if not isinstance(frame,dict):raise ValueError('Invalid frame')
            vs,fs=frame.get('vertices'),frame.get('faces')
            if (not isinstance(vs,list) or not isinstance(fs,list) or len(vs)>60000
                    or len(fs)>60000 or not vs):
                raise ValueError('Invalid native mesh frame')
            if any(not isinstance(v,list) or len(v)!=3 or any(not _finite(n) for n in v) for v in vs):
                raise ValueError('Invalid native mesh positions')
            if any(not isinstance(face,list) or len(face)<3 or len(face)>2000 or
                   any(not isinstance(i,int) or i<0 or i>=len(vs) for i in face) for face in fs):
                raise ValueError('Invalid native mesh topology')
    return data


def total_seconds(lesson):
    return sum(float(s.get('duration',10)) for s in lesson['steps'])


def position(lesson, seconds):
    """Find a step and visual stage from a timeline time, including reverse seek."""
    steps=lesson['steps']
    total=total_seconds(lesson)
    seconds=max(0.0,min(float(seconds),total))
    at=0.0
    for i,step in enumerate(steps):
        d=float(step.get('duration',10))
        if seconds<at+d or i==len(steps)-1:
            f=max(0.0,min(1.0,(seconds-at)/d))
            stage=next((name for name,lo,hi in STAGES if lo<=f<hi),'WHY')
            op_fraction=max(0,min(1,(f-.32)/(.79-.32)))
            frames=step['frames']
            sample=round(op_fraction*(len(frames)-1)) if f>=.32 else 0
            if f>=.79:sample=len(frames)-1
            return {'index':i,'step':step,'fraction':f,'stage':stage,'sample':sample,
                    'frame':frames[sample], 'local_seconds':seconds-at,
                    'step_start':at,'elapsed':seconds, 'total':total}
        at+=d
    raise AssertionError('no steps')


def step_start(lesson,index):
    return sum(float(s.get('duration',10)) for s in lesson['steps'][:index])


def selected_centroid(frame):
    vertices=frame['vertices']
    selected=frame.get('selected_faces',[])
    coords=[vertices[i] for face_id in selected
            if isinstance(face_id,int) and 0<=face_id<len(frame['faces'])
            for i in frame['faces'][face_id]]
    if not coords and frame.get('target'):
        return list(frame['target'])
    if not coords:coords=vertices
    return [sum(v[i] for v in coords)/len(coords) for i in range(3)]


def triangles(frame):
    """Triangulate a native mesh snapshot for GPU, preserving selected faces."""
    vertices=frame['vertices']; regular=[]; highlighted=[]; edges=set()
    selected=set(frame.get('selected_faces',[]))
    # Native Blender's loop triangulation handles bevel ngons correctly;
    # fan triangulation is only a compatibility fallback.
    native_tris=frame.get('triangles')
    if native_tris is not None and len(frame.get('triangle_faces',[]))==len(native_tris):
        for tri,face_id in zip(native_tris,frame['triangle_faces']):
            dest=highlighted if face_id in selected else regular
            dest.extend(vertices[i] for i in tri)
    else:
        for face_id,face in enumerate(frame['faces']):
            dest=highlighted if face_id in selected else regular
            for j in range(1,len(face)-1):
                dest.extend([vertices[face[0]], vertices[face[j]], vertices[face[j+1]]])
    for face in frame['faces']:
        for a,b in zip(face,face[1:]+face[:1]):
            if a!=b:edges.add(tuple(sorted((a,b))))
    return regular,highlighted,[point for a,b in sorted(edges) for point in (vertices[a],vertices[b])]


def read_spec(path):
    path=Path(path)
    if path.stat().st_size>2_000_000:raise ValueError('Spec too large')
    return validate_spec(json.loads(path.read_text(encoding='utf8')))


def read_compiled(path):
    path=Path(path)
    if path.stat().st_size>50_000_000:raise ValueError('Compiled native lesson too large')
    return validate_compiled(json.loads(path.read_text(encoding='utf8')))
