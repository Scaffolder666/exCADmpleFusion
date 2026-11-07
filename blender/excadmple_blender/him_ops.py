"""HiM-inspired operation animation catalog for the exCADmple Blender spike.

A feature is an explicit, replayable step specification, not the recovered
history of an arbitrary CAD file. This file creates reference-only Blender
objects and keyframes, leaving the user's objects untouched.

The catalog includes parameter animations (extrude, revolve, fillet,
chamfer, patterns, shell, draft) and clear visual reenactments for the
remaining operations. Exact CAD operation semantics are not claimed for
the reenactment operations.
"""
import math
import bpy

from .procedural import build_extrusion

OPERATION_TYPES = (
    "extrude", "revolve", "fillet", "chamfer",
    "circular_pattern", "rectangular_pattern",
    "mirror", "copy", "move", "scale", "combine", "split",
    "import", "export", "shell", "draft", "sweep",
    "loft", "thread", "hole"
)


def _material(name, rgb):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        material.diffuse_color = (*rgb, 1.0)
        material.use_nodes = True
        principled = material.node_tree.nodes.get("Principled BSDF")
        if principled:
            principled.inputs["Base Color"].default_value = (*rgb, 1.0)
    return material


def _mesh(collection, name, vertices, faces, step_id, color=(.27, .53, .81)):
    mesh = bpy.data.meshes.new(name + " geometry")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(_material("exCADmple | Feature showcase blue", color))
    obj["excadmple_reference"] = True
    obj["excadmple_step"] = step_id
    return obj


def _cube(collection, name, step_id, location, scale=(1, 1, 1), aux=False):
    vertices = [
        (-.5,-.5,-.5),(.5,-.5,-.5),(.5,.5,-.5),(-.5,.5,-.5),
        (-.5,-.5,.5),(.5,-.5,.5),(.5,.5,.5),(-.5,.5,.5)
    ]
    faces = [
        (0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),
        (2,3,7,6),(3,0,4,7)
    ]
    obj = _mesh(collection, name, vertices, faces, step_id)
    obj.location = location
    obj.scale = scale
    if aux:
        obj["excadmple_auxiliary"] = True
    return obj


def _set_key(obj, path, frames):
    for frame, value in frames:
        setattr(obj, path, value)
        obj.keyframe_insert(data_path=path, frame=frame)


def _reveal(obj, start, end, final_scale):
    # In-CAD appearance/disappearance animation: no native feature mutation.
    eps = tuple(max(0.0001, abs(v) * .001) for v in final_scale)
    _set_key(obj, "scale", ((start, eps), (end, final_scale)))


def _phase_frames(step):
    start, end = int(step["start"]), int(step["end"])
    return start, start + max(1, int((end-start)*.20)), end


def _mesh_evaluated_count(obj):
    return len(obj.data.vertices)


def build_operation(collection, step):
    """Dispatch one typed visual operation to independent Blender reference objects."""
    feature = step.get("operation") or {}
    operation = feature.get("type")
    if operation not in OPERATION_TYPES:
        raise ValueError("Unsupported animation operation: " + str(operation))
    name = "exCADmple | " + operation.replace("_", " ").title() + " | " + step["id"]
    step_id = step["id"]
    start, mid, end = _phase_frames(step)

    if operation == "extrude":
        # Real profile vertex morph, sketch trace and a moving 3D manipulator.
        return list(build_extrusion(collection, step, name))

    if operation == "revolve":
        vertices = [(1.05,0,0), (1.15,0,.15), (.62,0,.75), (.4,0,1.20)]
        edges = [(0,1),(1,2),(2,3)]
        mesh = bpy.data.meshes.new(name + " sketch")
        mesh.from_pydata(vertices, edges, [])
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        obj["excadmple_reference"] = True
        obj["excadmple_step"] = step_id
        modifier = obj.modifiers.new("Animated revolve angle", "SCREW")
        modifier.axis = "Z"
        modifier.steps = 32
        modifier.render_steps = 32
        modifier.use_merge_vertices = False
        modifier.angle = 0.001
        for frame, angle in ((start,.001),(mid,.001),(end,2*math.pi)):
            modifier.angle = angle
            modifier.keyframe_insert(data_path="angle", frame=frame)
        return [obj]

    if operation in ("fillet","chamfer"):
        obj = _cube(collection, name, step_id, (0,0,.7), (2.1,1.6,1.4))
        bevel = obj.modifiers.new("Animated " + operation, "BEVEL")
        bevel.limit_method = "NONE"
        bevel.segments = 6 if operation == "fillet" else 1
        bevel.width = .0001
        for frame,width in ((start,.0001),(mid,.0001),(end,.26)):
            bevel.width = width
            bevel.keyframe_insert(data_path="width", frame=frame)
        return [obj]

    if operation in ("circular_pattern","rectangular_pattern"):
        items = []
        count = 6
        for i in range(count):
            initial = (0.0,0.0,.45)
            if operation == "circular_pattern":
                angle = 2*math.pi*i/count
                target = (2.0*math.cos(angle),2.0*math.sin(angle),.45)
            else:
                target = ((i%3-1)*1.65,(i//3-.5)*1.65,.45)
            obj = _cube(collection, name+" copy "+str(i+1), step_id,
                        initial,(.45,.45,.90))
            _set_key(obj,"location",((start, initial),(end,target)))
            if i:
                _reveal(obj, min(end-1,start+5*i), end, (.45,.45,.90))
            items.append(obj)
        return items

    if operation == "mirror":
        original = _cube(collection,name+" source",step_id,(1.25,0,.6),(.8,.8,1.2))
        mirror = _cube(collection,name+" mirrored",step_id,(1.25,0,.6),(.8,.8,1.2))
        _set_key(mirror,"location",((start,(1.25,0,.6)),(end,(-1.25,0,.6))))
        _reveal(mirror,start,end,(.8,.8,1.2))
        return [original,mirror]

    if operation in ("copy","move","scale","import","export"):
        obj = _cube(collection,name,step_id,(0,0,.65),(1.1,1.1,1.3))
        if operation == "copy":
            obj2 = _cube(collection,name+" source",step_id,(-1.5,0,.65),(1.1,1.1,1.3))
            _set_key(obj,"location",((start,(-1.5,0,.65)),(end,(1.5,0,.65))))
            _reveal(obj,start,end,(1.1,1.1,1.3))
            return [obj2,obj]
        if operation == "move":
            _set_key(obj,"location",((start,(-1.4,0,.65)),(end,(1.4,0,.65))))
        elif operation == "scale":
            _reveal(obj,start,end,(1.65,1.65,1.65))
        elif operation == "import":
            _reveal(obj,start,end,(1.1,1.1,1.3))
        elif operation == "export":
            _set_key(obj,"location",((start,(0,0,.65)),(end,(1.5,0,1.3))))
            _reveal(obj,start,end,(.001,.001,.001))
        return [obj]

    if operation == "combine":
        # Visual approach/overlap, *not* a Boolean BRep history reconstruction.
        first = _cube(collection,name+" A",step_id,(-1.2,0,.6),(1.7,1.0,1.2))
        second = _cube(collection,name+" B",step_id,(1.2,0,.6),(1.5,1.1,1.0))
        _set_key(first,"location",((start,(-1.2,0,.6)),(end,(-.35,0,.6))))
        _set_key(second,"location",((start,(1.2,0,.6)),(end,(.35,0,.6))))
        return [first,second]

    if operation == "split":
        a = _cube(collection,name+" left half",step_id,(-.5,0,.65),(1.0,1.5,1.3))
        b = _cube(collection,name+" right half",step_id,(.5,0,.65),(1.0,1.5,1.3))
        _set_key(a,"location",((start,(-.5,0,.65)),(end,(-1.1,0,.65))))
        _set_key(b,"location",((start,(.5,0,.65)),(end,(1.1,0,.65))))
        return [a,b]

    if operation == "shell":
        # Open-top surface becomes thick-walled via Solidify.
        vertices = [(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0),
                    (-1,-1,1.6),(1,-1,1.6),(1,1,1.6),(-1,1,1.6)]
        faces = [(0,3,2,1),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        obj = _mesh(collection,name,vertices,faces,step_id)
        modifier = obj.modifiers.new("Animated shell thickness","SOLIDIFY")
        modifier.thickness=.001
        for frame,value in ((start,.001),(mid,.001),(end,.20)):
            modifier.thickness=value
            modifier.keyframe_insert(data_path="thickness",frame=frame)
        return [obj]

    if operation == "draft":
        obj = _cube(collection,name,step_id,(0,0,.65),(2,1.4,1.3))
        obj.shape_key_add(name="Basis",from_mix=False)
        shape = obj.shape_key_add(name="Draft angle",from_mix=False)
        for vert in shape.data:
            if vert.co.z > 0:
                vert.co.x = vert.co.x + .20
        for frame,value in ((start,0.),(mid,0.),(end,1.)):
            shape.value=value
            shape.keyframe_insert(data_path="value",frame=frame)
        return [obj]

    if operation in ("sweep","thread"):
        curve = bpy.data.curves.new(name+" curve","CURVE")
        curve.dimensions="3D"
        curve.bevel_depth=.09 if operation == "sweep" else .047
        curve.resolution_u=3
        curve.bevel_resolution=2
        spline=curve.splines.new("POLY")
        points=[]
        n=80
        for i in range(n):
            t=i/(n-1)
            if operation == "sweep":
                points.append((2*t-1, .55*math.sin(2*math.pi*t),1.6*t,1))
            else:
                angle=math.pi*10*t
                points.append((.55*math.cos(angle),.55*math.sin(angle),2*t,1))
        spline.points.add(len(points)-1)
        for point,value in zip(spline.points,points):
            point.co=value
        curve.bevel_factor_mapping_end="SPLINE"
        obj=bpy.data.objects.new(name,curve)
        collection.objects.link(obj)
        curve.materials.append(_material("exCADmple | Sweep material",(.27,.53,.81)))
        obj["excadmple_reference"]=True
        obj["excadmple_step"]=step_id
        for frame,value in ((start,0.001),(mid,.001),(end,1.)):
            curve.bevel_factor_end=value
            curve.keyframe_insert(data_path="bevel_factor_end",frame=frame)
        return [obj]

    if operation == "loft":
        lower=[(-.65,-.65,0),(.65,-.65,0),(.65,.65,0),(-.65,.65,0)]
        upper=[(-.65,-.65,1.6),(.65,-.65,1.6),(.65,.65,1.6),(-.65,.65,1.6)]
        target=[(-1.05,-.9,1.6),(1.05,-.9,1.6),(1.05,.9,1.6),(-1.05,.9,1.6)]
        faces=[(0,3,2,1),(4,5,6,7)] + [(i,(i+1)%4,(i+1)%4+4,i+4) for i in range(4)]
        obj=_mesh(collection,name,lower+upper,faces,step_id)
        obj.shape_key_add(name="Basis",from_mix=False)
        shape=obj.shape_key_add(name="Loft profile",from_mix=False)
        for index,coord in enumerate(lower+target):
            shape.data[index].co=coord
        for frame,value in ((start,0.),(mid,0.),(end,1.)):
            shape.value=value
            shape.keyframe_insert(data_path="value",frame=frame)
        return [obj]

    if operation == "hole":
        target=_cube(collection,name+" target",step_id,(0,0,.7),(2.4,2.4,1.4))
        # A cutter is modeled inside the reference collection. Its evolving
        # radius changes a live Blender Boolean result at each frame.
        count=32
        verts=[]
        for z in (-1.2,1.2):
            verts.extend((math.cos(2*math.pi*i/count),math.sin(2*math.pi*i/count),z)
                         for i in range(count))
        faces=[tuple(reversed(range(count))),tuple(range(count,2*count))]
        faces.extend((i,(i+1)%count,(i+1)%count+count,i+count) for i in range(count))
        cutter=_mesh(collection,name+" cutter",verts,faces,step_id,(.95,.65,.24))
        cutter["excadmple_auxiliary"]=True
        cutter.display_type="WIRE"
        modifier=target.modifiers.new("Animated hole cut","BOOLEAN")
        modifier.operation="DIFFERENCE"
        modifier.solver="EXACT"
        modifier.object=cutter
        _set_key(cutter,"scale",((start,(.001,.001,1)),(mid,(.001,.001,1)),(end,(.55,.55,1))))
        return [target,cutter]

    raise AssertionError("Missing implementation for " + operation)
