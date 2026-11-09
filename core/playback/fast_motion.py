"""Fast HiM motion: move the feature's real faces instead of recomputing.

Native HiM playback changes a parameter every frame and lets Fusion
recompute the whole model. For many operations the intermediate shape is a
rigid or affine motion of the feature's final faces, so Fusion only has to
compute the result once:

* Extrude (distance extent, no taper, starts on the profile plane): the
  faces are scaled along the extrude direction about the profile plane.
  For a new body this is exactly the native intermediate shape; for
  join/cut it is exact until the tool meets non-planar geometry, so it is
  marked approximate.
* Rectangular / circular pattern: every instance moves from the source
  along its real pattern transform (translation, or rotation about the
  pattern axis). The end state is exact; the path is illustrative.
* Mirror: the mirrored faces fold over from the source through the mirror
  plane. End state exact; path illustrative.
* Revolve (one angle): the revolved faces turn about the real axis from
  the profile position to their final angle. Illustrative.

Fillet, chamfer, shell and anything not recognised keep native recompute.
When playback pauses the panel asks for one more frame marked ``settle``;
operations with parameters are then recomputed natively, so a paused model
is always the real one.

Pure Python: matrices are 4x4 nested lists (row-major); Fusion objects are
read by attribute, so the planners also run on stubs.
"""
import math

NEW_SOLID = (3, 4)
EXACT = "exact"
APPROXIMATE = "approximate"
ILLUSTRATIVE = "illustrative"


# --- 4x4 matrices ------------------------------------------------------------------------
def identity():
    return [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]


def matmul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def apply(m, p):
    return tuple(m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3] for r in range(3))


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    if n < 1e-12:
        raise ValueError("zero-length direction")
    return tuple(c / n for c in v)


def _about(linear, point):
    """Affine map with 3x3 ``linear`` part that keeps ``point`` fixed."""
    m = identity()
    for r in range(3):
        for c in range(3):
            m[r][c] = linear[r][c]
        m[r][3] = point[r] - sum(linear[r][c] * point[c] for c in range(3))
    return m


def scale_along(axis, point, s):
    """Scale by ``s`` along ``axis`` about the plane through ``point``."""
    u = _unit(axis)
    linear = [[(1.0 if r == c else 0.0) + (s - 1.0) * u[r] * u[c] for c in range(3)] for r in range(3)]
    return _about(linear, point)


def rotation_about(axis, point, angle):
    """Rotation by ``angle`` (rad) about the line through ``point``."""
    x, y, z = _unit(axis)
    c, s, t = math.cos(angle), math.sin(angle), 1 - math.cos(angle)
    linear = [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
              [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
              [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]
    return _about(linear, point)


def invert_rigid(m):
    """Inverse of a rotation + translation."""
    rt = [[m[c][r] for c in range(3)] for r in range(3)]
    out = identity()
    for r in range(3):
        for c in range(3):
            out[r][c] = rt[r][c]
        out[r][3] = -sum(rt[r][c] * m[c][3] for c in range(3))
    return out


def screw_partial(m, t):
    """The fraction ``t`` of a rigid motion ``m``: rotation angle and the
    translation along the rotation axis are scaled, about the motion's own
    axis (a circular pattern turns along its arc, not a chord)."""
    t = max(0.0, min(1.0, float(t)))
    trace = m[0][0] + m[1][1] + m[2][2]
    angle = math.acos(max(-1.0, min(1.0, (trace - 1.0) / 2.0)))
    d = (m[0][3], m[1][3], m[2][3])
    if angle < 1e-9:                                   # pure translation
        out = identity()
        for r in range(3):
            out[r][3] = d[r] * t
        return out
    if math.pi - angle < 1e-6:
        # 180 degrees: axis from the symmetric part of the rotation.
        diag = [m[i][i] for i in range(3)]
        i = max(range(3), key=lambda k: diag[k])
        col = [(m[r][i] + (1.0 if r == i else 0.0)) / 2.0 for r in range(3)]
        axis = _unit(col)
    else:
        axis = _unit((m[2][1] - m[1][2], m[0][2] - m[2][0], m[1][0] - m[0][1]))
    along = sum(d[i] * axis[i] for i in range(3))
    perp = [d[i] - along * axis[i] for i in range(3)]
    # A point c on the axis satisfies (I - R) c = perp; solve in the plane
    # perpendicular to the axis: c = (perp + cot(angle/2) * axis x perp) / 2.
    cross = (axis[1] * perp[2] - axis[2] * perp[1], axis[2] * perp[0] - axis[0] * perp[2],
             axis[0] * perp[1] - axis[1] * perp[0])
    cot = math.cos(angle / 2) / math.sin(angle / 2)
    center = tuple((perp[i] + cot * cross[i]) / 2.0 for i in range(3))
    out = rotation_about(axis, center, angle * t)
    for r in range(3):
        out[r][3] += axis[r] * along * t
    return out


def flatten(m):
    return [m[r][c] for r in range(4) for c in range(4)]


def unflatten(values):
    values = list(values)
    return [values[r * 4:(r + 1) * 4] for r in range(4)]


# --- reading Fusion objects (duck-typed) ---------------------------------------------------
def _items(collection, limit=2000):
    if collection is None:
        return []
    try:
        return [collection.item(i) for i in range(min(collection.count, limit))]
    except Exception:
        return []


def _xyz(point):
    return (float(point.x), float(point.y), float(point.z))


def _type(obj):
    try:
        return (obj.objectType or "").split("::")[-1]
    except Exception:
        return ""


def _value(param):
    try:
        return float(param.value)
    except Exception:
        return None


def plane_of(entity):
    """(origin, normal) of a profile, planar face or construction plane."""
    for getter in (lambda e: e.plane, lambda e: e.geometry):
        try:
            plane = getter(entity)
            return _xyz(plane.origin), _xyz(plane.normal)
        except Exception:
            continue
    return None


def line_of(entity):
    """(point, direction) of a construction axis, linear edge or sketch line."""
    for getter in (lambda e: e.geometry, lambda e: e.worldGeometry, lambda e: e):
        try:
            geometry = getter(entity)
        except Exception:
            continue
        try:
            return _xyz(geometry.origin), _xyz(geometry.direction)        # InfiniteLine3D
        except Exception:
            pass
        try:
            a, b = _xyz(geometry.startPoint), _xyz(geometry.endPoint)       # Line3D
            return a, tuple(b[i] - a[i] for i in range(3))
        except Exception:
            continue
    return None


def capture_inputs(kind, entity):
    """Read what the planners need while the Timeline marker is BEFORE the
    feature (the Fusion API reads profiles and axes there)."""
    inputs = {}
    try:
        if kind == "ExtrudeFeature":
            profile = entity.profile
            first = _items(profile)[0] if hasattr(profile, "count") else profile
            inputs["plane"] = plane_of(first)
        elif kind == "RevolveFeature":
            inputs["axis"] = line_of(entity.axis)
            profile = entity.profile
            first = _items(profile)[0] if hasattr(profile, "count") else profile
            inputs["plane"] = plane_of(first)
        elif kind == "MirrorFeature":
            inputs["mirror"] = plane_of(entity.mirrorPlane)
    except Exception:
        pass
    return {k: v for k, v in inputs.items() if v}


class Piece:
    """Faces that move together, and their transform at each progress."""

    def __init__(self, faces, motion):
        self.faces, self.motion = list(faces), motion

    def matrix(self, progress):
        return self.motion(max(0.0, min(1.0, float(progress))))


class Plan:
    def __init__(self, pieces, accuracy, label):
        self.pieces, self.accuracy, self.label = pieces, accuracy, label


def _extrude_plan(entity, inputs, start_fraction):
    if not inputs.get("plane"):
        return None
    if "ProfilePlaneStart" not in _type(getattr(entity, "startExtent", None)) and \
            getattr(entity, "startExtent", None) is not None:
        return None                                   # offset / from-object start
    for name in ("extentOne", "extentTwo"):
        extent = getattr(entity, name, None)
        if extent is not None and _type(extent) not in ("DistanceExtentDefinition",
                                                         "SymmetricExtentDefinition", ""):
            return None                               # to-object / all / to-next
    if getattr(entity, "extentOne", None) is None:
        return None
    for name in ("taperAngleOne", "taperAngleTwo"):
        value = _value(getattr(entity, name, None))
        if value is not None and abs(value) > 1e-9:
            return None
    faces = _items(getattr(entity, "faces", None))
    if not faces:
        return None
    origin, normal = inputs["plane"]

    def motion(t):
        s = start_fraction + (1.0 - start_fraction) * t
        return scale_along(normal, origin, s)
    # adsk.fusion.FeatureOperations: 3 = new body, 4 = new component. Join,
    # cut and intersect depend on the other geometry: approximate.
    exact = getattr(entity, "operation", None) in NEW_SOLID
    return Plan([Piece(faces, motion)], EXACT if exact else APPROXIMATE,
                "extrude grows along its direction")


def _pattern_plan(entity):
    pieces = []
    for element in _items(getattr(entity, "patternElements", None)):
        try:
            transform = element.transform
            final = [[float(transform.getCell(r, c)) for c in range(4)] for r in range(4)]
        except Exception:
            return None
        faces = _items(getattr(element, "faces", None))
        if not faces:
            continue
        if all(abs(final[r][c] - (1.0 if r == c else 0.0)) < 1e-9 for r in range(3) for c in range(4)):
            continue                                  # the source itself
        back = invert_rigid(final)
        pieces.append(Piece(faces, lambda t, final=final, back=back: matmul(screw_partial(final, t), back)))
    return Plan(pieces, ILLUSTRATIVE, "instances move from the source") if pieces else None


def _mirror_plan(entity, inputs):
    if not inputs.get("mirror"):
        return None
    faces = _items(getattr(entity, "faces", None))
    if not faces:
        return None
    origin, normal = inputs["mirror"]
    reflect = scale_along(normal, origin, -1.0)
    return Plan([Piece(faces, lambda t: matmul(scale_along(normal, origin, 1.0 - 2.0 * t), reflect))],
                ILLUSTRATIVE, "the copy folds over the mirror plane")


def _revolve_plan(entity, inputs):
    if not inputs.get("axis"):
        return None
    extent = getattr(entity, "extentDefinition", None)
    if _type(extent) != "AngleExtentDefinition":
        return None
    angle = _value(getattr(extent, "angle", None))
    faces = _items(getattr(entity, "faces", None))
    if not angle or not faces:
        return None
    point, direction = inputs["axis"]
    # Rotate so the faces start at the profile and end at their real angle.
    return Plan([Piece(faces, lambda t: rotation_about(direction, point, -(1.0 - t) * angle))],
                ILLUSTRATIVE, "the revolved faces turn about the axis")


def plan_for(kind, entity, inputs, start_fraction=0.02):
    """A fast-motion Plan for this feature, or None (keep native recompute)."""
    try:
        if kind == "ExtrudeFeature":
            return _extrude_plan(entity, inputs, start_fraction)
        if kind in ("RectangularPatternFeature", "CircularPatternFeature"):
            return _pattern_plan(entity)
        if kind == "MirrorFeature":
            return _mirror_plan(entity, inputs)
        if kind == "RevolveFeature":
            return _revolve_plan(entity, inputs)
    except Exception:
        return None
    return None
