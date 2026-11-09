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
* Move (bodies or faces, rigid transform): the moved bodies travel from
  where they were to where they end, along the real transform (rotation
  about its own axis). The end state is exact; the path is illustrative,
  since the designer's drag path was not recorded.

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


def _token_of(obj):
    try:
        return obj.entityToken or ""
    except Exception:
        return ""


def _attr(obj, name):
    """An attribute Fusion may refuse to read (RuntimeError) in this state."""
    try:
        return getattr(obj, name)
    except Exception:
        return None


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
        elif kind == "MoveFeature":
            # Fusion reads a Move's transform and inputs only with the
            # marker before it ("Didn't roll editing feature back").
            inputs["move_matrix"] = _move_transform(entity)
            targets = []
            for item in _items(entity.inputEntities):
                targets.append((_type(item), _token_of(item)))
            inputs["move_targets"] = targets
    except Exception:
        pass
    return {k: v for k, v in inputs.items() if v}


class Refused(Exception):
    """This feature keeps native recompute, for the given reason."""


def _still(_t):
    return identity()


class Piece:
    """Things drawn together: their transform and (optionally) opacity at
    each progress. ``kind`` "brep" items are copied faces/bodies, "curve"
    items are curves (a revolve's profile). ``role`` picks the look:
    None (moving face teal, other feature faces plain), "change" (teal),
    "before" / "after" (plain body), "profile" (blue curve)."""

    def __init__(self, faces, motion=_still, opacity=None, kind="brep", role=None, copied=False):
        self.faces, self.motion = list(faces), motion
        self.opacity_curve, self.kind, self.role = opacity, kind, role
        self.copied = copied          # items are already transient copies

    def matrix(self, progress):
        return self.motion(max(0.0, min(1.0, float(progress))))

    def opacity(self, progress):
        if self.opacity_curve is None:
            return None
        return max(0.0, min(1.0, self.opacity_curve(max(0.0, min(1.0, float(progress))))))


class Plan:
    def __init__(self, pieces, accuracy, label, handle_motion=None):
        self.pieces, self.accuracy, self.label = pieces, accuracy, label
        # How manipulator handles move; default: with the first piece.
        self.handle_motion = handle_motion or (pieces[0].matrix if pieces else _still)


def _extrude_plan(entity, inputs, start_fraction):
    if not inputs.get("plane"):
        raise Refused("the profile plane could not be read")
    if "ProfilePlaneStart" not in _type(getattr(entity, "startExtent", None)) and \
            getattr(entity, "startExtent", None) is not None:
        raise Refused("the extrude does not start on the profile plane")
    for name in ("extentOne", "extentTwo"):
        extent = getattr(entity, name, None)
        if extent is not None and _type(extent) not in ("DistanceExtentDefinition",
                                                         "SymmetricExtentDefinition", ""):
            raise Refused("extent type " + _type(extent) + " cannot be scaled")
    if getattr(entity, "extentOne", None) is None:
        raise Refused("no extent")
    for name in ("taperAngleOne", "taperAngleTwo"):
        value = _value(getattr(entity, name, None))
        if value is not None and abs(value) > 1e-9:
            raise Refused("the extrude has a taper angle")
    faces = _items(getattr(entity, "faces", None))
    if not faces:
        raise Refused("the feature reports no faces")
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
            raise Refused("a pattern transform could not be read")
        faces = _items(getattr(element, "faces", None))
        if not faces:
            continue
        if all(abs(final[r][c] - (1.0 if r == c else 0.0)) < 1e-9 for r in range(3) for c in range(4)):
            continue                                  # the source itself
        back = invert_rigid(final)
        pieces.append(Piece(faces, lambda t, final=final, back=back: matmul(screw_partial(final, t), back)))
    if not pieces:
        raise Refused("the pattern instances report no faces")
    return Plan(pieces, ILLUSTRATIVE, "instances move from the source")


def _mirror_plan(entity, inputs):
    if not inputs.get("mirror"):
        raise Refused("the mirror plane could not be read")
    faces = _items(getattr(entity, "faces", None))
    if not faces:
        raise Refused("the feature reports no faces")
    origin, normal = inputs["mirror"]
    reflect = scale_along(normal, origin, -1.0)
    return Plan([Piece(faces, lambda t: matmul(scale_along(normal, origin, 1.0 - 2.0 * t), reflect))],
                ILLUSTRATIVE, "the copy folds over the mirror plane")


def _revolve_plan(entity, inputs):
    """The profile sweeps about the real axis while the revolved faces
    appear. (Turning the finished solid about its own axis showed nothing
    for a full revolve: a body of revolution looks the same at any angle.)"""
    if not inputs.get("axis"):
        raise Refused("the revolve axis could not be read")
    extent = _attr(entity, "extentDefinition")
    if _type(extent) != "AngleExtentDefinition":
        raise Refused("extent type " + _type(extent) + " is not a single angle")
    angle = _value(_attr(extent, "angle"))
    faces = _items(_attr(entity, "faces"))
    if not angle or not faces:
        raise Refused("no angle or no faces")
    point, direction = inputs["axis"]
    sign = 1.0
    starts = [c for c in (_centroid(f) for f in _items(_attr(entity, "startFaces"))) if c]
    ends = [c for c in (_centroid(f) for f in _items(_attr(entity, "endFaces"))) if c]
    if starts and ends:
        # Which way the sweep goes: rotating the start face by +angle or
        # -angle must land on the end face.
        forward = apply(rotation_about(direction, point, angle), starts[0])
        backward = apply(rotation_about(direction, point, -angle), starts[0])
        sign = 1.0 if _dist(forward, ends[0]) <= _dist(backward, ends[0]) else -1.0
    sweep = lambda t: rotation_about(direction, point, sign * t * angle)
    pieces = []
    profile = list(inputs.get("profile_curves") or [])
    if profile:
        pieces.append(Piece(profile, sweep, kind="curve", role="profile"))
    pieces.append(Piece(faces, opacity=lambda t: t, role="change"))
    return Plan(pieces, ILLUSTRATIVE, "the profile sweeps about the axis",
                handle_motion=lambda t: rotation_about(direction, point, sign * (t - 1.0) * angle))


def _centroid(face):
    try:
        return _xyz(face.centroid)
    except Exception:
        return None


def _dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _crossfade_plan(entity, inputs):
    """Any other operation (combine, offset faces, copy/paste, fillet,
    chamfer, shell, ...): the affected bodies as they were before fade out,
    the result fades in with the feature's own faces in teal. Bodies the
    operation consumed (combine tools) fade out; new bodies fade in."""
    before = inputs.get("before_bodies") or {}
    after_tokens = inputs.get("after_tokens")
    results = _items(_attr(entity, "bodies"))
    result_tokens = {_token_of(b) for b in results}
    fading = [copy for token, copy in before.items()
              if token in result_tokens or (after_tokens is not None and token not in after_tokens)]
    faces = _items(_attr(entity, "faces"))
    pieces = []
    if fading:
        pieces.append(Piece(fading, opacity=lambda t: 1.0 - t, role="before", copied=True))
    if results:
        pieces.append(Piece(results, opacity=lambda t: t, role="after"))
    if faces:
        pieces.append(Piece(faces, opacity=lambda t: t, role="change"))
    if not pieces:
        raise Refused("nothing to show before or after the operation")
    return Plan(pieces, ILLUSTRATIVE, "the result replaces what was there")


def _is_rigid(m, tol=1e-6):
    """Rotation (orthonormal, det +1) plus translation."""
    for r in range(3):
        for c in range(3):
            dot = sum(m[k][r] * m[k][c] for k in range(3))
            if abs(dot - (1.0 if r == c else 0.0)) > tol:
                return False
    det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
           - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
           + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    return abs(det - 1.0) < tol and all(abs(m[3][c] - (1.0 if c == 3 else 0.0)) < tol for c in range(4))


def _move_transform(entity):
    """The Move feature's real transform: MoveFeature.transform (free move),
    else its definition's transform."""
    for getter in (lambda e: e.transform, lambda e: e.definition.transform):
        try:
            transform = getter(entity)
            return [[float(transform.getCell(r, c)) for c in range(4)] for r in range(4)]
        except Exception:
            continue
    return None


def _move_plan(entity, inputs):
    final = inputs.get("move_matrix") or _move_transform(entity)
    if final is None:
        raise Refused("the move transform could not be read")
    if not _is_rigid(final):
        raise Refused("the move is not a rigid motion")
    # What moved: the input bodies (whole bodies, copied as one piece each)
    # or input faces, read before the feature and found again by token
    # now that the marker is after it. Occurrences (component moves) are
    # not handled.
    targets = inputs.get("move_targets")
    if targets is None:
        targets = [(_type(item), _token_of(item)) for item in _items(_attr(entity, "inputEntities"))]
    resolve = inputs.get("resolve") or (lambda token: None)
    moved = []
    for kind, token in targets:
        if kind not in ("BRepBody", "BRepFace"):
            raise Refused("moving a " + (kind or "component") + " is not animated")
        item = resolve(token) if token else None
        if item is None:
            raise Refused("a moved " + kind + " could not be found after the move")
        moved.append(item)
    if not moved:
        moved = _items(_attr(entity, "bodies"))
    if not moved:
        raise Refused("the moved bodies could not be read")
    back = invert_rigid(final)
    return Plan([Piece(moved, lambda t: matmul(screw_partial(final, t), back))],
                ILLUSTRATIVE, "the bodies move along the real transform")


SPECIFIC = {"ExtrudeFeature", "RectangularPatternFeature", "CircularPatternFeature",
            "MirrorFeature", "RevolveFeature", "MoveFeature"}


def _specific_plan(kind, entity, inputs, start_fraction):
    if kind == "ExtrudeFeature":
        return _extrude_plan(entity, inputs, start_fraction)
    if kind in ("RectangularPatternFeature", "CircularPatternFeature"):
        return _pattern_plan(entity)
    if kind == "MirrorFeature":
        return _mirror_plan(entity, inputs)
    if kind == "RevolveFeature":
        return _revolve_plan(entity, inputs)
    if kind == "MoveFeature":
        return _move_plan(entity, inputs)
    raise Refused("no motion of its own for " + (kind or "this feature"))


def plan_for(kind, entity, inputs, start_fraction=0.02, reasons=None):
    """A fast-motion Plan for this feature, or None (keep native recompute).
    A feature without a motion of its own (or whose own motion cannot be
    used) gets the before/after crossfade. Why each was refused is
    appended to ``reasons`` when a list is given."""
    notes = []
    for planner in (lambda: _specific_plan(kind, entity, inputs, start_fraction),
                    lambda: _crossfade_plan(entity, inputs)):
        try:
            plan = planner()
            plan.note = "; ".join(notes)          # why a more specific motion was not used
            return plan
        except Refused as refused:
            notes.append(str(refused))
        except Exception as error:
            notes.append("{}: {}".format(type(error).__name__, error))
    if reasons is not None:
        reasons.append("; ".join(notes))
    return None
