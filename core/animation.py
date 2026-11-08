"""Pure geometry for safe in-canvas CAD feature previews.

Unlike HiM's two-Fusion-instance implementation, this prototype constructs
transient meshes from *explicitly authored or exported* feature data. It
does NOT alter a real Fusion feature parameter, native timeline, or model.
"""
import math


class AnimationError(ValueError):
    pass


def _point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise AnimationError("Expected a 3D point")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise AnimationError("Points must contain finite coordinates")
    return [float(v) for v in value]


def validate_animation(data):
    """Validate v1 extrusion preview specification; reject unsupported ops."""
    if not isinstance(data, dict):
        raise AnimationError("Animation must be an object")
    if data.get("type") == "reveal":
        meshes = data.get("new_meshes")
        if not isinstance(meshes, list) or not 1 <= len(meshes) <= 25:
            raise AnimationError("Reveal needs 1–25 new meshes")
        context = data.get("context_meshes", [])
        if not isinstance(context, list) or len(context) > 25:
            raise AnimationError("Reveal context needs 0–25 meshes")
        return data
    if data.get("type") in ("revolve", "pattern", "mirror", "transform"):
        return validate_transform_animation(data)
    if data.get("type") != "extrude":
        raise AnimationError("Supported previews: extrude and reveal")
    profile = data.get("profile")
    if not isinstance(profile, list) or not 3 <= len(profile) <= 120:
        raise AnimationError("Extrude profile requires 3–120 vertices")
    profile = [_point(p) for p in profile]
    direction = _point(data.get("direction_cm"))
    if sum(v * v for v in direction) < 1e-8:
        raise AnimationError("Extrude direction cannot be zero")
    caps = data.get("cap_triangles")
    if not isinstance(caps, list) or not caps or len(caps) > 240:
        raise AnimationError("An explicitly triangulated cap is required")
    for triangle in caps:
        if not isinstance(triangle, list) or len(triangle) != 3 or any(
            not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= len(profile)
            for i in triangle
        ):
            raise AnimationError("Invalid cap triangle")
        if len(set(triangle)) != 3:
            raise AnimationError("Degenerate cap triangle")
    context = data.get("context_meshes", [])
    if not isinstance(context, list) or len(context) > 25:
        raise AnimationError("Context must contain 0–25 precomputed meshes")
    return data


def extrude_mesh(animation, progress):
    """Return an explicit BRep-like triangular prism mesh at progress 0–1.

    Topology is fixed across frames and uses centimeter coordinates, Fusion's
    internal unit. The original profile must be ordered and triangulated.
    This is a *visual demonstration* of distance, not a feature recomputation.
    Does not calculate Join/Cut intersections or draft/taper angles.
    """
    validate_animation(animation)
    if isinstance(progress, bool) or not isinstance(progress, (int, float)) or not math.isfinite(progress):
        raise AnimationError("Invalid animation progress")
    t = min(1.0, max(0.0, float(progress)))
    # Avoid degenerate facets at exactly zero, where Fusion can refuse mesh.
    t = max(0.0005, t)
    profile = animation["profile"]
    direction = animation["direction_cm"]
    count = len(profile)
    vertices = [list(p) for p in profile] + [
        [p[i] + t * direction[i] for i in range(3)] for p in profile
    ]
    triangles = []
    for a, b, c in animation["cap_triangles"]:
        triangles.append([c, b, a])
        triangles.append([a + count, b + count, c + count])
    for i in range(count):
        j = (i + 1) % count
        triangles.append([i, j, j + count])
        triangles.append([i, j + count, i + count])
    return {"vertices": vertices, "triangles": triangles}

def reveal_meshes(animation, progress):
    """Illustrative new-part appearance; not native feature recomputation."""
    validate_animation(animation)
    if animation["type"] != "reveal":
        raise AnimationError("Expected reveal animation")
    if isinstance(progress, bool) or not isinstance(progress, (int, float)) or not math.isfinite(progress):
        raise AnimationError("Invalid animation progress")
    t = max(0.001, min(1.0, float(progress)))
    if t >= 1.0:
        return list(animation.get("context_meshes", [])) + list(animation["new_meshes"])
    output = list(animation.get("context_meshes", []))
    for mesh in animation["new_meshes"]:
        vertices = mesh["vertices"]
        center = [sum(p[i] for p in vertices) / len(vertices) for i in range(3)]
        output.append({
            "vertices": [[center[i] + (p[i] - center[i]) * t for i in range(3)] for p in vertices],
            "triangles": mesh["triangles"]
        })
    return output

def validate_transform_animation(data):
    """Validate authored mesh and operation parameters (centimeter units)."""
    typ = data["type"]
    meshes = data.get("new_meshes")
    if not isinstance(meshes, list) or not 1 <= len(meshes) <= 25:
        raise AnimationError("Operation requires 1–25 source meshes")
    for mesh in meshes:
        if not isinstance(mesh, dict) or not mesh.get("vertices") or not mesh.get("triangles"):
            raise AnimationError("Source mesh requires vertices and triangles")
        for vertex in mesh["vertices"]:
            _point(vertex)
        for tri in mesh["triangles"]:
            if len(tri) != 3 or any(not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= len(mesh["vertices"]) for i in tri):
                raise AnimationError("Invalid source triangle")
    context = data.get("context_meshes", [])
    if not isinstance(context, list) or len(context) > 25:
        raise AnimationError("Invalid context meshes")
    if typ in ("revolve", "pattern"):
        _point(data.get("axis_origin_cm"))
        axis = _point(data.get("axis_direction"))
        if sum(v*v for v in axis) < 1e-8:
            raise AnimationError("Axis cannot be zero")
        angle = data.get("angle_deg", 360)
        if isinstance(angle, bool) or not isinstance(angle, (int, float)) or not math.isfinite(angle):
            raise AnimationError("Invalid angle")
        if typ == "pattern":
            count = data.get("count")
            if not isinstance(count, int) or isinstance(count, bool) or not 2 <= count <= 24:
                raise AnimationError("Pattern count must be 2–24")
    if typ == "mirror":
        _point(data.get("plane_origin_cm"))
        normal = _point(data.get("plane_normal"))
        if sum(v*v for v in normal) < 1e-8:
            raise AnimationError("Mirror plane normal cannot be zero")
    if typ == "transform":
        _point(data.get("translation_cm"))
    return data


def operation_meshes(animation, progress):
    """Transient geometry for authored revolve/pattern/mirror/transform previews.

    Revolve rotates an authored mesh around an axis; it does not sweep a sketch
    into a native BRep. Pattern duplicates meshes around the given axis.
    """
    validate_transform_animation(animation)
    if isinstance(progress, bool) or not isinstance(progress, (int, float)) or not math.isfinite(progress):
        raise AnimationError("Invalid animation progress")
    t = max(0.0, min(1.0, float(progress)))
    typ = animation["type"]
    output = list(animation.get("context_meshes", []))
    origin = animation.get("axis_origin_cm", [0, 0, 0])
    axis = animation.get("axis_direction", [0, 0, 1])
    length = math.sqrt(sum(v*v for v in axis))
    axis = [v/length for v in axis]
    def rotate(p, angle):
        v = [p[i]-origin[i] for i in range(3)]
        c, sn = math.cos(angle), math.sin(angle)
        cross = [axis[1]*v[2]-axis[2]*v[1],
                 axis[2]*v[0]-axis[0]*v[2],
                 axis[0]*v[1]-axis[1]*v[0]]
        dot = sum(axis[i]*v[i] for i in range(3))
        return [origin[i]+v[i]*c+cross[i]*sn+axis[i]*dot*(1-c) for i in range(3)]
    def transformed(mesh, fn, reverse=False):
        return {"vertices": [fn(p) for p in mesh["vertices"]],
                "triangles": [[tri[0], tri[2], tri[1]] for tri in mesh["triangles"]] if reverse else mesh["triangles"]}
    if typ == "pattern":
        count = animation["count"]
        angle = math.radians(animation.get("angle_deg", 360))
        for i in range(count):
            if i > (count-1)*t + 1e-9:
                break
            for mesh in animation["new_meshes"]:
                output.append(transformed(mesh, lambda p, a=angle*i/count: rotate(p, a)))
    elif typ == "revolve":
        angle = math.radians(animation.get("angle_deg", 360))*t
        for mesh in animation["new_meshes"]:
            output.append(transformed(mesh, lambda p: rotate(p, angle)))
    elif typ == "mirror":
        normal = animation["plane_normal"]
        norm = math.sqrt(sum(v*v for v in normal))
        n = [v/norm for v in normal]
        o = animation["plane_origin_cm"]
        for mesh in animation["new_meshes"]:
            output.append(mesh)
            if t > 0:
                output.append(transformed(mesh, lambda p: [p[i]-2*t*sum((p[j]-o[j])*n[j] for j in range(3))*n[i] for i in range(3)], reverse=True))
    elif typ == "transform":
        translation = animation["translation_cm"]
        for mesh in animation["new_meshes"]:
            output.append(transformed(mesh, lambda p: [p[i]+t*translation[i] for i in range(3)]))
    return output
