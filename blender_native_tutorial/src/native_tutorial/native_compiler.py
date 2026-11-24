"""Compile authored interactive tutorials with *actual built-in bpy.ops*.

This runs ONLY inside a separate --background --factory-startup Blender
process. The active learner's Blender window, Undo, Edit Mode and native
operators are untouched. No source Feature History or recording is required.

Each operation samples an ORIGINAL Blender operator on a disposable copy of
the reference mesh, rather than reproducing geometry with handwritten math.
For example `mesh.extrude_region_move` is called at every sample distance.
"""
import json
import math
import os
import sys
from pathlib import Path

import bpy
import bmesh
from .engine import read_spec, COMPILED_FORMAT
from .starter import practice_mesh, REAR_Y, THICKNESS

SAMPLES=15


def _enter_edit(obj):
    if obj.mode!='OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode='EDIT')


def _exit_edit(obj):
    if obj.mode!='OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def _select(obj, selector):
    """Choose source CAD geometry for a Blender native Edit Mode operation."""
    _enter_edit(obj)
    bpy.ops.mesh.select_all(action='DESELECT')
    tool=bpy.context.tool_settings
    edge_mode=selector=='highest_edges'
    tool.mesh_select_mode=(False, True, False) if edge_mode else (False,False,True)
    bm=bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.normal_update()
    for v in bm.verts:v.select_set(False)
    for e in bm.edges:e.select_set(False)
    for f in bm.faces:f.select_set(False)
    selected=[]
    if selector=='highest_edges':
        top=max(v.co.z for v in bm.verts)
        # Only edges along the top of the back support, not every edge.
        selected=[e for e in bm.edges if all(abs(v.co.z-top)<.025 for v in e.verts)]
        if not selected:raise ValueError('No upper edges available for native Bevel')
        for e in selected:e.select_set(True)
        points=[tuple(v.co) for edge in selected for v in edge.verts]
    elif selector in ('rear_top_face','front_top_face'):
        candidates=[]
        for f in bm.faces:
            c=f.calc_center_median()
            if f.normal.z<.65:continue
            if selector=='rear_top_face' and c.y>=REAR_Y-.002:
                candidates.append(f)
            if selector=='front_top_face' and c.y<REAR_Y-.03:
                candidates.append(f)
        if not candidates:raise ValueError('Face not found: '+selector)
        # Selecting one face matches how the learner uses Blender; avoid
        # selecting surrounding walls or unrelated faces.
        chosen=max(candidates,key=lambda f:f.calc_area())
        chosen.select_set(True)
        selected=[chosen]
        points=[tuple(v.co) for v in chosen.verts]
    elif selector=='all_faces':
        selected=list(bm.faces)
        for f in selected:f.select_set(True)
        points=[tuple(v.co) for f in selected for v in f.verts]
    elif selector=='all_verts':
        tool.mesh_select_mode=(True,False,False)
        for v in bm.verts:v.select_set(True)
        points=[tuple(v.co) for v in bm.verts]
    else:
        raise ValueError('Unknown selector '+selector)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)
    center=[sum(v[i] for v in points)/len(points) for i in range(3)]
    return center


def _apply_builtin(op,args,fraction):
    """The calls below ARE Blender's real modeling operators, not replicas."""
    if fraction<=0:return
    if op=='mesh.extrude_region_move':
        distance=float(args['distance'])*fraction
        result=bpy.ops.mesh.extrude_region_move(
            MESH_OT_extrude_region={},
            TRANSFORM_OT_translate={'value':(0.0,0.0,distance),
                                    'orient_type':'GLOBAL'})
    elif op=='mesh.bevel':
        offset=float(args['offset'])*fraction
        result=bpy.ops.mesh.bevel(offset=max(.00001,offset),
                                  segments=int(args.get('segments',3)),
                                  affect='EDGES')
    elif op=='mesh.inset':
        result=bpy.ops.mesh.inset(thickness=max(.00001,float(args['thickness'])*fraction),
                                 depth=float(args.get('depth',0.0))*fraction,
                                 use_individual=False)
    elif op=='transform.translate':
        value=tuple(float(n)*fraction for n in args['value'])
        result=bpy.ops.transform.translate(value=value,orient_type='GLOBAL')
    elif op=='transform.rotate':
        result=bpy.ops.transform.rotate(value=float(args['angle'])*fraction,
                                        orient_axis=str(args.get('orient_axis','Z')),
                                        orient_type='GLOBAL')
    elif op=='transform.resize':
        value=tuple(1+(float(n)-1)*fraction for n in args['value'])
        result=bpy.ops.transform.resize(value=value,orient_type='GLOBAL')
    elif op=='mesh.subdivide':
        result=bpy.ops.mesh.subdivide(number_cuts=int(args.get('number_cuts',1)))
    else:
        raise ValueError('Unsupported Blender operator '+op)
    if 'FINISHED' not in result:
        raise RuntimeError('Blender native operator returned '+str(result))


def _capture(obj, target):
    _exit_edit(obj)
    me=obj.data
    me.calc_loop_triangles()
    frame={
        'vertices':[[round(float(c),5) for c in v.co] for v in me.vertices],
        'faces':[list(poly.vertices) for poly in me.polygons],
        'triangles':[list(t.vertices) for t in me.loop_triangles],
        'triangle_faces':[int(t.polygon_index) for t in me.loop_triangles],
        'selected_faces':[p.index for p in me.polygons if p.select],
        'selected_edges':[list(e.vertices) for e in me.edges if e.select],
        'target':[round(float(c),4) for c in target],
    }
    if len(frame['vertices'])>60000 or len(frame['faces'])>60000:
        raise ValueError('Native operation produced too many GPU vertices')
    return frame


def _make_base():
    vertices,faces=practice_mesh()
    mesh=bpy.data.meshes.new('exCADmple native author source')
    mesh.from_pydata(vertices,[],faces)
    mesh.update()
    obj=bpy.data.objects.new('Native operator source',mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    return obj


def _native_step(obj, step, frames_count=SAMPLES):
    """Compile all frames by applying the specified builtin to the same
    pre-operation mesh, then apply it once at full strength to advance the
    author's source state. Each sample is a real bpy.ops execution.
    """
    _exit_edit(obj)
    previous=obj.data.copy()
    result=[]
    for sample in range(frames_count):
        _exit_edit(obj)
        old=obj.data
        obj.data=previous.copy()
        if old.users==0:bpy.data.meshes.remove(old)
        target=_select(obj,step['select'])
        _apply_builtin(step['operator'],step['args'],sample/(frames_count-1))
        result.append(_capture(obj,target))
    _exit_edit(obj)
    old=obj.data
    obj.data=previous.copy()
    if old.users==0:bpy.data.meshes.remove(old)
    _select(obj,step['select'])
    _apply_builtin(step['operator'],step['args'],1.0)
    _exit_edit(obj)
    if previous.users==0:bpy.data.meshes.remove(previous)
    out={key:value for key,value in step.items() if key!='frames'}
    out['frames']=result
    out['provenance']='native-bpy.ops'
    return out


def compile_lesson(spec_path,output_path):
    spec=read_spec(spec_path)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj=_make_base()
    compiled=[]
    for i,step in enumerate(spec['steps']):
        print(f'[exCADmple] Executing native {i+1}/{len(spec["steps"])}: {step["operator"]}',flush=True)
        compiled.append(_native_step(obj,step))
    result={
        'format':COMPILED_FORMAT,
        'title':spec.get('title','Native Blender Modeling Tutorial'),
        'unit':spec.get('unit','Blender units'),
        'blender_version':bpy.app.version_string,
        'source':str(Path(spec_path).resolve()),
        'description':spec.get('description',''),
        'method':'Actual Blender builtin bpy.ops executed in an isolated background process',
        'steps':compiled,
    }
    destination=Path(output_path).resolve()
    destination.parent.mkdir(parents=True,exist_ok=True)
    part=destination.with_name(destination.name+'.pending')
    part.write_text(json.dumps(result,separators=(',',':')),encoding='utf8')
    os.replace(part,destination)
    print(f'[exCADmple] Wrote {destination}: {len(compiled)} native operations',flush=True)
    return result
