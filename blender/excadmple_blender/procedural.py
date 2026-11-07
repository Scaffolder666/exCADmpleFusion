"""HiM-inspired *visual* CAD operations in Blender 4.5+.

An animated extrusion is built from a real 2D profile and animated vertices,
not from uniformly scaling an existing cube. A traced Sketch curve and moving
manipulator make the operation legible. Nothing is written to user geometry.

This is an operation reenactment supplied by an example package, not a
recovered or verified history from an arbitrary Blender/Fusion model.
"""
import bpy

from .core import validate_extrude_animation


def _material(name, rgb):
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*rgb, 1.0)
        mat.use_nodes = True
        node = mat.node_tree.nodes.get("Principled BSDF")
        if node:
            node.inputs["Base Color"].default_value = (*rgb, 1.0)
            node.inputs["Roughness"].default_value = .38
    return mat


def _animate_shape_key(obj, final_positions, start, grow_start, end):
    obj.shape_key_add(name="Basis", from_mix=False)
    target = obj.shape_key_add(name="Extrude", from_mix=False)
    if len(target.data) != len(final_positions):
        raise ValueError("Extrusion shape key has a mismatched vertex count")
    for point, end_point in zip(target.data, final_positions):
        point.co = end_point
    for frame, value in ((start, 0.0), (grow_start, 0.0), (end, 1.0)):
        target.value = value
        target.keyframe_insert(data_path="value", frame=frame)
    obj["excadmple_extrude_start"] = int(grow_start)
    obj["excadmple_extrude_end"] = int(end)
    return target


def _prism_mesh(profile, distance):
    """Generate a prism with static topology and two cap polygon faces."""
    n = len(profile)
    eps = .001  # nonzero early thickness avoids degenerate viewport faces
    vertices = (
        [(x, y, 0.0) for x, y in profile] +
        [(x, y, eps) for x, y in profile]
    )
    target_vertices = (
        [(x, y, 0.0) for x, y in profile] +
        [(x, y, distance) for x, y in profile]
    )
    faces = [tuple(reversed(range(n))), tuple(range(n, 2*n))]
    faces.extend(
        (i, (i+1) % n, (i+1) % n + n, i+n)
        for i in range(n)
    )
    return vertices, target_vertices, faces


def _sketch_outline(collection, name, profile, origin, start, end):
    curve = bpy.data.curves.new(name + " curve", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = .014
    curve.resolution_u = 1
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(len(profile)-1)
    for i,(x,y) in enumerate(profile):
        spline.points[i].co = (x, y, 0.0, 1.0)
    spline.use_cyclic_u = True
    curve.bevel_factor_mapping_end = "SPLINE"
    for frame,factor in ((start, 0.0), (min(end,start+20), 1.0)):
        curve.bevel_factor_end = factor
        curve.keyframe_insert(data_path="bevel_factor_end", frame=frame)
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    obj.location = origin
    curve.materials.append(_material("exCADmple | Sketch amber", (.97,.58,.16)))
    obj["excadmple_auxiliary"] = True
    return obj


def _extrude_gizmo(collection, name, origin, distance, start, grow_start, end):
    """A simple 3D arrow that grows together with the extruded profile."""
    # Shaft square, wider arrowhead ring and apex.
    e = .017
    z0 = .004
    low = [(-e,-e,0),(e,-e,0),(e,e,0),(-e,e,0)]
    high = [(-e,-e,z0),(e,-e,z0),(e,e,z0),(-e,e,z0)]
    ring = [(-.09,-.09,z0),(.09,-.09,z0),(.09,.09,z0),(-.09,.09,z0)]
    vertices = low + high + ring + [(0,0,z0+.007)]
    faces = [(0,3,2,1)]
    faces.extend((i,(i+1)%4, (i+1)%4+4,i+4) for i in range(4))
    faces.extend((8+i,8+(i+1)%4,12) for i in range(4))
    mesh = bpy.data.meshes.new(name+" geometry")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    arrow = bpy.data.objects.new(name,mesh)
    collection.objects.link(arrow)
    arrow.location = origin
    mesh.materials.append(_material("exCADmple | Manipulator gold", (.95,.72,.16)))
    target = low + [
        (x,y,distance*.80) for x,y,_ in high
    ] + [
        (x,y,distance*.80) for x,y,_ in ring
    ] + [(0,0,distance)]
    _animate_shape_key(arrow, target, start, grow_start, end)
    arrow["excadmple_auxiliary"] = True
    return arrow


def build_extrusion(collection, step, name):
    """Build a testable feature reenactment from explicit profile metadata."""
    spec = validate_extrude_animation(step["animation"])
    profile = [tuple(p) for p in spec["profile_xy"]]
    origin = tuple(spec["origin_xyz"])
    distance = float(spec["distance"])
    start, end = step["start"], step["end"]
    grow_start = start + max(2, round((end - start)*.31))
    vertices, target_vertices, faces = _prism_mesh(profile, distance)
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.location = origin
    mesh.materials.append(_material("exCADmple | Animated extrusion blue", (.27,.53,.81)))
    obj.color = (.27,.53,.81,1)
    obj["excadmple_reference"] = True
    obj["excadmple_step"] = step["id"]
    obj["excadmple_operation"] = "EXTRUDE"
    obj["excadmple_distance"] = distance
    _animate_shape_key(obj, target_vertices, start, grow_start, end)
    outline = _sketch_outline(collection, name + " — sketch", profile, origin, start, end)
    outline["excadmple_step"] = step["id"]
    # The arrow appears just beside the profile, to avoid covering the solid.
    maxx = max(x for x,y in profile)
    arrow_origin = (origin[0] + maxx + .22, origin[1], origin[2])
    arrow = _extrude_gizmo(
        collection, name + " — manipulator", arrow_origin,
        distance, start, grow_start, end
    )
    arrow["excadmple_step"] = step["id"]
    return obj, outline, arrow
