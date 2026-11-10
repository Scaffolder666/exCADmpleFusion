"""Fusion-style manipulators for HiM playback: which face moves, and where.

Like Fusion's own Extrude command, the operation is shown by the face that
moves (highlighted) and an arrow with the current value, not by colouring
the whole result:

* Extrude: the end face(s) move along the extrude direction; one arrow per
  moving face, labelled with that side's distance. A one-sided extrude's
  start face stays on the profile plane and is not highlighted.
* Revolve: the end face turns about the axis; the arrow is tangent to the
  rotation, labelled with the angle.

Everything is read from the feature itself (endFaces, startFaces, extents,
profile plane, axis): nothing is guessed. Pure Python, duck-typed.
"""
import math

MOVING = "moving"
BODY = "body"


def _items(collection, limit=2000):
    if collection is None:
        return []
    try:
        return [collection.item(i) for i in range(min(collection.count, limit))]
    except Exception:
        return []


def _token(entity):
    try:
        return entity.entityToken or ""
    except Exception:
        return ""


def _xyz(point):
    return (float(point.x), float(point.y), float(point.z))


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v):
    n = math.sqrt(_dot(v, v))
    return tuple(c / n for c in v) if n > 1e-12 else None


def centroid(face):
    for name in ("centroid", "pointOnFace"):
        try:
            return _xyz(getattr(face, name))
        except Exception:
            continue
    return None


def _two_sided(entity):
    if getattr(entity, "hasTwoExtents", False) is True:
        return True
    if getattr(entity, "extentTwo", None) is not None:
        return True
    try:
        return "Symmetric" in (entity.extentOne.objectType or "")
    except Exception:
        return False


def moving_faces(kind, entity):
    """Tokens of the faces the operation moves; empty when not applicable."""
    if kind == "ExtrudeFeature":
        faces = _items(getattr(entity, "endFaces", None))
        if _two_sided(entity):
            faces += _items(getattr(entity, "startFaces", None))
    elif kind == "RevolveFeature":
        faces = _items(getattr(entity, "endFaces", None))
    else:
        return set()
    return {_token(f) for f in faces if _token(f)}


def _parameter(entity, path):
    value = entity
    for part in path.split("."):
        value = getattr(value, part, None)
        if value is None:
            return None
    return value


def handles(kind, entity, inputs):
    """[{anchor, direction, parameter}] for the moving faces, or []."""
    out = []
    if kind == "ExtrudeFeature" and inputs.get("plane"):
        origin, normal = inputs["plane"]
        normal = _unit(normal)
        sides = [("endFaces", "extentOne.distance")]
        if _two_sided(entity):
            symmetric = _parameter(entity, "extentTwo.distance") is None
            sides.append(("startFaces", "extentOne.distance" if symmetric else "extentTwo.distance"))
        for faces_name, parameter in sides:
            for face in _items(getattr(entity, faces_name, None)):
                c = centroid(face)
                if c is None or normal is None:
                    continue
                d = _dot(_sub(c, origin), normal)
                if abs(d) < 1e-9:
                    continue                          # still on the profile plane
                direction = tuple(n * (1 if d > 0 else -1) for n in normal)
                out.append({"anchor": c, "direction": direction,
                            "parameter": _parameter(entity, parameter), "unit": "length"})
    elif kind == "RevolveFeature" and inputs.get("axis"):
        point, axis = inputs["axis"]
        axis = _unit(axis)
        starts = [centroid(f) for f in _items(getattr(entity, "startFaces", None))]
        starts = [s for s in starts if s is not None]
        for face in _items(getattr(entity, "endFaces", None)):
            c = centroid(face)
            if c is None or axis is None:
                continue
            tangent = _unit(_cross(axis, _sub(c, point)))
            if tangent is None:
                continue
            if starts and _dot(tangent, _sub(c, starts[0])) < 0:
                tangent = tuple(-t for t in tangent)  # point away from where it started
            out.append({"anchor": c, "direction": tangent,
                        "parameter": _parameter(entity, "extentDefinition.angle"), "unit": "angle"})
    return out


def arrow_lines(anchor, direction, length):
    """Shaft from the face outwards plus a two-line head: (points, index pairs)."""
    u = _unit(direction)
    if u is None or length <= 0:
        return None
    tip = tuple(anchor[i] + u[i] * length for i in range(3))
    helper = (1.0, 0.0, 0.0) if abs(u[0]) < 0.9 else (0.0, 1.0, 0.0)
    side = _unit(_cross(u, helper))
    head = length * 0.28
    left = tuple(tip[i] - u[i] * head + side[i] * head * 0.5 for i in range(3))
    right = tuple(tip[i] - u[i] * head - side[i] * head * 0.5 for i in range(3))
    return [anchor, tip, left, right], [0, 1, 1, 2, 1, 3]


def arrow_length(faces_span):
    """A readable arrow: a fraction of the feature size, within limits (cm)."""
    return max(0.6, min(3.0, 0.35 * faces_span)) if faces_span > 0 else 1.0
