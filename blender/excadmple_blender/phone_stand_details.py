"""Additional *coherent* Phone Stand construction, not a feature gallery.

These steps extend the SAME support, lip, and base objects made by build_demo.
All animated geometry is deliberately pre-authored. The authored reasoning
and ghost pointer are supplied by the corresponding example JSON steps.

Steps 4-9:
  fillet base edges, open cable slot, brace with paired gussets,
  pattern four grip pads, open back-panel lightening window,
  fit-check against a deliberately temporary phone proxy.

The reference objects are never linked to the learner's editable geometry.
"""
import bpy

from .procedural import _material


def _mesh(collection, name, vertices, faces, step_id, color=(.29, .55, .77),
          auxiliary=False):
    mesh=bpy.data.meshes.new(name+" mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj=bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(_material("exCADmple | "+name, color))
    obj.color=(*color,1.)
    obj["excadmple_reference"]=True
    obj["excadmple_step"]=step_id
    if auxiliary:
        obj["excadmple_auxiliary"]=True
    return obj


def _cube(collection,name,step_id,location,scale,color=(.36,.68,.79),
          auxiliary=False):
    vertices=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
              (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),
           (2,3,7,6),(3,0,4,7)]
    obj=_mesh(collection,name,vertices,faces,step_id,color,auxiliary)
    obj.location=location
    obj.scale=scale
    return obj


def _key(obj,path,pairs):
    for frame,value in pairs:
        setattr(obj,path,value)
        obj.keyframe_insert(data_path=path,frame=frame)


def _bevel(obj,step,name,amount,segments):
    modifier=obj.modifiers.new(name,"BEVEL")
    modifier.limit_method="ANGLE"
    modifier.segments=segments
    mid=step["start"]+int(.28*(step["end"]-step["start"]))
    for frame,value in ((step["start"],.0001),(mid,.0001),
                        (step["end"],amount)):
        modifier.width=value
        modifier.keyframe_insert(data_path="width",frame=frame)
    return modifier


def _slot(collection,target,step,name,origin,target_position,halfsize):
    cutter=_cube(collection,name,step["id"],origin,halfsize,
                 (.97,.65,.23),auxiliary=True)
    cutter.display_type="WIRE"
    cutter.hide_render=True
    modifier=target.modifiers.new(name+" / cut","BOOLEAN")
    modifier.operation="DIFFERENCE"
    modifier.solver="EXACT"
    modifier.object=cutter
    start,end=step["start"],step["end"]
    drag=start+int((end-start)*.35)
    _key(cutter,"location",((start,origin),(drag,origin),
                            (end,target_position)))
    return cutter,modifier


def _triangular_rib(collection,step,x,suffix):
    """Extruded triangular brace in the Y-Z section, beside the back support."""
    y0,y1=.30,.94
    z0,z1=.26,1.52
    half=.065
    verts=[
        (x-half,y0,z0),(x-half,y1,z0),(x-half,y1,z0+.004),
        (x+half,y0,z0),(x+half,y1,z0),(x+half,y1,z0+.004)
    ]
    faces=[(0,2,1),(3,4,5),(0,1,4,3),
           (1,2,5,4),(2,0,3,5)]
    target=[tuple(v) for v in verts]
    target[2]=(x-half,y1,z1)
    target[5]=(x+half,y1,z1)
    obj=_mesh(collection,"exCADmple | 06 Support rib "+suffix,
              verts,faces,step["id"],(.30,.61,.83))
    obj.shape_key_add(name="Basis",from_mix=False)
    shape=obj.shape_key_add(name="Gusset height",from_mix=False)
    for vertex,desired in zip(shape.data,target):
        vertex.co=desired
    mid=step["start"]+int(.25*(step["end"]-step["start"]))
    for frame,value in ((step["start"],0.),(mid,0.),(step["end"],1.)):
        shape.value=value
        shape.keyframe_insert(data_path="value",frame=frame)
    return obj


def _pads(collection,step):
    out=[]
    start,end=step["start"],step["end"]
    # A 2x2 pattern gives a stable footprint without changing the base width.
    for i,x in enumerate((-4.05,-1.55)):
        for j,y in enumerate((-.80,.80)):
            pad=_cube(
                collection,"exCADmple | 07 Grip pad %d-%d"%(i+1,j+1),
                step["id"],(x,y,-.057),(.20,.23,.056),
                (.20,.23,.26))
            pad.modifiers.new("Soft pad edge","BEVEL").width=.04
            delay=(i*2+j)*6
            _key(pad,"scale",(
                (start,(.001,.001,.001)),
                (start+delay,(.001,.001,.001)),
                (min(end,start+int(.75*(end-start))+delay),(.20,.23,.056))))
            out.append(pad)
    return out


def _fit_proxy(collection,step):
    """Temporary wireframe phone is a design-check aid, not part of the stand."""
    phone=_cube(collection,"exCADmple | 09 Device fit proxy",step["id"],
                (-2.8,-1.60,2.66), (1.20,.09,1.55),
                (.86,.83,.55),auxiliary=True)
    phone.display_type="WIRE"
    phone.hide_render=True
    start,end=step["start"],step["end"]
    _key(phone,"location",(
        (start,(-2.8,-1.60,2.66)),
        (start+int(.20*(end-start)),(-2.8,-1.60,2.66)),
        (end,(-2.8,.45,1.66))))
    _key(phone,"rotation_euler",(
        (start,(0.,0.,0.)),
        (end,(-.3141592654,0.,0.))))
    return phone


def add_detail_steps(collection,steps,base,back,lip):
    """Append 6 scripted design decisions to the existing 3-step stand.

    Returns a dict keyed by step ID with the Blender reference objects and
    modifiers created for that step (useful for real bpy integration tests).
    """
    by_id={step["id"]:step for step in steps}
    required=("base_round","cable","ribs","pads","back_window","fit")
    if not all(k in by_id for k in required):
        return {}
    artifacts={}
    artifacts["base_round"]={
        "bevel":_bevel(base,by_id["base_round"],
                       "04 Round base edges",.11,5),
        "objects":[base],
    }
    cutter,modifier=_slot(
        collection,lip,by_id["cable"],
        "exCADmple | 05 Cable passage cutter",
        (-2.8,-3.0,.39),(-2.8,-.94,.39),(.29,.42,.22))
    artifacts["cable"]={"objects":[lip,cutter],"boolean":modifier}
    artifacts["ribs"]={"objects":[
        _triangular_rib(collection,by_id["ribs"],-3.90,"L"),
        _triangular_rib(collection,by_id["ribs"],-1.70,"R"),
    ]}
    artifacts["pads"]={"objects":_pads(collection,by_id["pads"])}
    # Removing a broad center region from the back support preserves its
    # side rails. This is an explicit modeled trade-off, not an optimized FEA.
    cutter,modifier=_slot(
        collection,back,by_id["back_window"],
        "exCADmple | 08 Back window cutter",
        (2.0,.95,1.05),(-2.8,.95,1.05),(.55,.64,.39))
    artifacts["back_window"]={"objects":[back,cutter],"boolean":modifier}
    artifacts["fit"]={"objects":[_fit_proxy(collection,by_id["fit"])]}
    return artifacts
