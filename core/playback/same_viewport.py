"""Show the reference model in the user's own viewport (same-viewport mode).

The designer's .f3d stays in its own, never-saved reference document with
its real Feature Timeline; HiM rolls that Timeline and animates its
parameters exactly as before. The user's Design stays the active, editable
document. This presenter draws the reference's *current* visible state into
the user's Design as non-selectable Custom Graphics:

* a transient BRep copy (TemporaryBRepManager) of every visible reference
  body, with the body's current opacity, so HiM's dimming and ghost hiding
  carry over unchanged; bodies HiM hid completely are skipped;
* the curves of visible sketches in the reference root component.

Everything is moved by one fixed offset chosen at load so the reference sits
beside the user's model. Custom Graphics are not features: nothing is added
to the user's Timeline, parameters or bodies.
"""
import adsk.core
import adsk.fusion

HIDDEN_OPACITY = 0.01         # HiM hides native faces at 0.001 in ghost mode
SKETCH_COLOR = (90, 98, 112, 255)
GAP_CM = 5.0


def _items(collection, limit=5000):
    try:
        return [collection.item(i) for i in range(min(collection.count, limit))]
    except Exception:
        return []


def _token(entity):
    try:
        return entity.entityToken or ""
    except Exception:
        return ""


def visible_bodies(design):
    """Visible bodies of a design, occurrence proxies included (world position)."""
    root = design.rootComponent
    bodies = list(_items(root.bRepBodies))
    for occurrence in _items(root.allOccurrences):
        bodies.extend(_items(occurrence.bRepBodies))
    out = []
    for body in bodies:
        try:
            if body.isVisible:
                out.append(body)
        except Exception:
            continue
    return out


def _bounds(bodies):
    lo, hi = [float("inf")] * 3, [float("-inf")] * 3
    for body in bodies:
        try:
            box = body.boundingBox
            for i, axis in enumerate("xyz"):
                lo[i] = min(lo[i], getattr(box.minPoint, axis))
                hi[i] = max(hi[i], getattr(box.maxPoint, axis))
        except Exception:
            continue
    return None if lo[0] == float("inf") else (lo, hi)


def side_by_side_offset(user_design, reference_design, preferred=None):
    """Fixed translation (cm) placing the reference to the +X side of the
    user's current model, chosen once per loaded tutorial."""
    if isinstance(preferred, (list, tuple)) and len(preferred) == 3:
        return tuple(float(v) for v in preferred)
    reference = _bounds(visible_bodies(reference_design))
    if reference is None:
        return (0.0, 0.0, 0.0)
    user = _bounds(visible_bodies(user_design)) if user_design else None
    user_max_x = max(0.0, user[1][0]) if user else 0.0
    width = reference[1][0] - reference[0][0]
    return (user_max_x + max(GAP_CM, 0.2 * width) - reference[0][0], 0.0, 0.0)


def offset_matrix(offset):
    matrix = adsk.core.Matrix3D.create()
    matrix.setCell(0, 3, offset[0])
    matrix.setCell(1, 3, offset[1])
    matrix.setCell(2, 3, offset[2])
    return matrix


def place(group, offset):
    """Move every entity of a Custom Graphics group by ``offset``, keeping
    any transform it already has (e.g. a fade scale)."""
    if not group or not any(offset):
        return
    for entity in _items(group):
        try:
            matrix = entity.transform
            matrix = matrix.copy() if matrix is not None else adsk.core.Matrix3D.create()
            matrix.transformBy(offset_matrix(offset))
            entity.transform = matrix
        except Exception:
            continue


class SameViewportPresenter:
    """Draws the reference design's current state into the user's design."""

    def __init__(self, log=None):
        self.log = log or (lambda *_: None)
        self.reference = None          # reference Design (separate document)
        self.target = None             # the user's Design (active document)
        self.offset = (0.0, 0.0, 0.0)
        self.static_group = None       # bodies that do not change in this frame
        self.dynamic_group = None      # bodies being recomputed every frame
        self.sketch_group = None
        self._static_key = None

    @property
    def attached(self):
        return self.reference is not None and self.target is not None

    def attach(self, reference_design, target_design, offset):
        self.clear()
        self.reference, self.target, self.offset = reference_design, target_design, tuple(offset)

    def detach(self):
        self.clear()
        self.reference = self.target = None

    def _group(self):
        group = self.target.rootComponent.customGraphicsGroups.add()
        group.isSelectable = False
        try:
            group.isChildrenSelectable = False
        except Exception:
            pass
        return group

    @staticmethod
    def _delete(group):
        try:
            if group is not None and group.isValid:
                group.deleteMe()
        except Exception:
            pass

    def clear(self):
        for name in ("static_group", "dynamic_group", "sketch_group"):
            self._delete(getattr(self, name))
            setattr(self, name, None)
        self._static_key = None

    def _draw_bodies(self, group, bodies):
        manager = adsk.fusion.TemporaryBRepManager.get()
        drawn = 0
        for body in bodies:
            try:
                opacity = float(body.opacity)
            except Exception:
                opacity = 1.0
            if opacity < HIDDEN_OPACITY:
                continue
            copy = manager.copy(body)
            if copy is None:
                raise RuntimeError("Fusion could not copy a reference body")
            entity = group.addBRepBody(copy)
            if entity is None:
                raise RuntimeError("Fusion could not draw a reference body")
            try:
                appearance = body.appearance
                if appearance is not None:
                    entity.color = adsk.fusion.CustomGraphicsAppearanceColorEffect.create(appearance)
            except Exception:
                pass
            if opacity < 1.0:
                entity.setOpacity(opacity, True)
            entity.isSelectable = False
            drawn += 1
        place(group, self.offset)
        return drawn

    def _draw_sketches(self):
        self._delete(self.sketch_group)
        self.sketch_group = None
        sketches = [s for s in _items(self.reference.rootComponent.sketches)
                    if getattr(s, "isVisible", False)]
        if not sketches:
            return
        group = self._group()
        color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*SKETCH_COLOR))
        for sketch in sketches:
            for curve in _items(sketch.sketchCurves):
                try:
                    line = group.addCurve(curve.worldGeometry)
                    line.color = color
                    line.weight = 1
                    line.isSelectable = False
                except Exception:
                    continue
        place(group, self.offset)
        self.sketch_group = group

    def refresh(self, state_key=None, changing=()):
        """Redraw the reference. ``changing`` (body tokens) are the bodies
        being recomputed by the current parameter frame; the others are
        redrawn only when ``state_key`` (timeline state + opacity setup)
        changes. With no ``state_key`` everything is redrawn."""
        if not self.attached:
            return 0
        changing = set(changing or ())
        bodies = visible_bodies(self.reference)
        static = [b for b in bodies if _token(b) not in changing]
        dynamic = [b for b in bodies if _token(b) in changing]
        drawn = 0
        if state_key is None or state_key != self._static_key:
            self._delete(self.static_group)
            self.static_group = self._group()
            drawn += self._draw_bodies(self.static_group, static)
            self._static_key = state_key
            self._draw_sketches()
        self._delete(self.dynamic_group)
        self.dynamic_group = None
        if dynamic:
            self.dynamic_group = self._group()
            drawn += self._draw_bodies(self.dynamic_group, dynamic)
        return drawn
