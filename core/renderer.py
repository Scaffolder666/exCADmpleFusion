"""Read-only transient reference geometry and non-destructive animated previews.

The feature animation uses a bounded number of frame updates from the HTML
palette. The model's native history marker and feature parameters are untouched.
"""
import adsk.core
import adsk.fusion

import math

from .animation import animation_meshes
from .pointer import sample as sample_pointer
from .step_changes import ChangeDetector, MAX_EXAMINED

POINTER_COLOR = (245, 140, 20, 255)
# Spatial guidance: the triangles this step created or modified (compared
# with the previous step's snapshot) are drawn teal, the rest unchanged.
CHANGE_COLOR = (20, 184, 166, 255)
FRAME_BUDGET = 6000      # triangles compared per animation frame
TRAIL_COLOR = (250, 190, 90, 255)

ARROW_COLOR = (235, 109, 35, 255)  # orange locator, distinct from teal surface highlight


def mesh_target_bounds(meshes):
    """Bounds of the *changed* geometry, never of the whole CAD example."""
    lo, hi = [float("inf")] * 3, [float("-inf")] * 3
    found = False
    for mesh in meshes or ():
        for point in mesh.get("vertices", ()):
            if len(point) != 3 or not all(math.isfinite(float(v)) for v in point):
                continue
            found = True
            for axis in range(3):
                lo[axis] = min(lo[axis], float(point[axis]))
                hi[axis] = max(hi[axis], float(point[axis]))
    return (lo, hi) if found else None


def body_target_bounds(bodies):
    """Bounds of trustworthy native feature geometry (faces if available)."""
    lo, hi = [float("inf")] * 3, [float("-inf")] * 3
    found = False
    for body in bodies or ():
        try:
            box = body.boundingBox
            a, b = box.minPoint, box.maxPoint
            values = ((a.x, a.y, a.z), (b.x, b.y, b.z))
            if not all(math.isfinite(float(v)) for point in values for v in point):
                continue
            found = True
            for axis in range(3):
                lo[axis] = min(lo[axis], values[0][axis])
                hi[axis] = max(hi[axis], values[1][axis])
        except Exception:
            continue
    return (lo, hi) if found else None


def arrow_geometry(bounds, offset=(0, 0, 0)):
    """Four points and three line segments, arrowhead touching target bounds.

    This is a locator, not a reconstruction of the original designer's mouse
    movement. The tip is placed at the top-center of the detected change.
    """
    if not bounds:
        return None
    lo, hi = bounds
    if not all(math.isfinite(float(x)) for x in lo + hi + list(offset)):
        return None
    span = max(hi[i] - lo[i] for i in range(3))
    distance = max(0.55, min(2.0, 0.36 * span))
    tip = [(lo[0] + hi[0]) / 2 + offset[0],
           (lo[1] + hi[1]) / 2 + offset[1], hi[2] + offset[2]]
    tail = [tip[0] + distance * 0.8,
            tip[1] - distance * 0.7,
            tip[2] + distance * 0.95]
    delta = [tail[i] - tip[i] for i in range(3)]
    length = math.sqrt(sum(x * x for x in delta))
    if length <= 1e-9:
        return None
    unit = [x / length for x in delta]
    perpendicular = [-unit[1], unit[0], 0.0]
    norm = math.hypot(perpendicular[0], perpendicular[1])
    perpendicular = [x / norm for x in perpendicular] if norm > 1e-9 else [1, 0, 0]
    head = max(0.14, min(0.35, distance * 0.22))
    base = [tip[i] + head * unit[i] for i in range(3)]
    left = [base[i] + head * 0.45 * perpendicular[i] for i in range(3)]
    right = [base[i] - head * 0.45 * perpendicular[i] for i in range(3)]
    return (tail, tip, left, right), (0, 1, 2, 1, 3, 1)


def add_target_arrow(group, bounds, offset=(0, 0, 0)):
    """Attach a nonselectable 3D arrow to an existing temporary graphics group."""
    if not hasattr(group, "addLines"):
        return False
    shape = arrow_geometry(bounds, offset)
    if shape is None:
        return False
    vertices, indices = shape
    flat = [v for xyz in vertices for v in xyz]
    arrow = group.addLines(adsk.fusion.CustomGraphicsCoordinates.create(flat), list(indices), False)
    if not arrow:
        return False
    arrow.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*ARROW_COLOR))
    arrow.weight = 4
    arrow.depthPriority = 2
    arrow.isSelectable = False
    return True


class ReferenceRenderer:
    def __init__(self, app):
        self.app = app
        self.group = None
        self.animation_group = None
        self.pointer_group = None
        self.hud_group = None
        self.command_group = None
        self.guidance_group = None
        self.visible = True
        self.last_step = None
        self.last_offset = None
        self.last_previous = None
        self._detectors = {}

    def _delete(self, group):
        try:
            if group and group.isValid:
                group.deleteMe()
        except Exception:
            pass

    def clear_animation(self):
        self._delete(self.animation_group)
        self.animation_group = None
        if self.group and self.group.isValid:
            self.group.isVisible = self.visible
        self._refresh()

    def clear_pointer(self):
        self._delete(self.pointer_group)
        self.pointer_group = None

    def clear_hud(self):
        self._delete(self.hud_group)
        self.hud_group = None

    def render_hud(self, lines):
        """Text pinned to the upper-left corner of the canvas (Custom Graphics
        view placement), so the tutorial is visible inside the viewport."""
        self.clear_hud()
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        if not design or not self.visible or not lines:
            return False
        group = design.rootComponent.customGraphicsGroups.add()
        group.isSelectable = False
        origin = adsk.core.Point3D.create(0, 0, 0)
        try:
            for row, line in enumerate(lines):
                text = group.addText(line, "Arial", 15 if row == 0 else 13,
                                     adsk.core.Matrix3D.create())
                text.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
                    adsk.core.Color.create(*((37, 99, 235, 255) if row == 0 else (40, 48, 60, 255))))
                text.isSelectable = False
                text.depthPriority = 3
                text.viewPlacement = adsk.fusion.CustomGraphicsViewPlacement.create(
                    origin, adsk.fusion.ViewCorners.upperLeftViewCorner,
                    adsk.core.Point2D.create(24, 70 + 24 * row))
        except Exception:
            self._delete(group)
            raise
        self.hud_group = group
        self._refresh()
        return True

    def clear_guidance(self):
        self._delete(self.guidance_group)
        self.guidance_group = None
        self._delete(self.command_group)
        self.command_group = None

    def render_command(self, step):
        """One short Fusion-tool label within the CAD viewport, not in the panel."""
        self._delete(self.command_group)
        self.command_group = None
        tools = [str(tool).strip() for tool in (step.get("tools") or []) if str(tool).strip()]
        if not tools or not self.visible:
            return False
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        if not design:
            return False
        group = design.rootComponent.customGraphicsGroups.add()
        group.isSelectable = False
        group.isChildrenSelectable = False
        try:
            label = "FUSION  ·  " + "  →  ".join(tools[:4])
            if len(tools) > 4:
                label += "  …"
            graphic = group.addText(label, "Arial", 15, adsk.core.Matrix3D.create())
            graphic.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
                adsk.core.Color.create(*ARROW_COLOR))
            graphic.isSelectable = False
            graphic.depthPriority = 3
            graphic.viewPlacement = adsk.fusion.CustomGraphicsViewPlacement.create(
                adsk.core.Point3D.create(0, 0, 0),
                adsk.fusion.ViewCorners.upperLeftViewCorner,
                adsk.core.Point2D.create(350, 95))
        except Exception:
            self._delete(group)
            return False
        self.command_group = group
        self._refresh()
        return True

    def render_target_arrow(self, changed, offset):
        """Highlight locator persists independently of changing animation meshes."""
        self._delete(self.guidance_group)
        self.guidance_group = None
        bounds = mesh_target_bounds(changed)
        if not bounds or not self.visible:
            return False
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        if not design:
            return False
        group = design.rootComponent.customGraphicsGroups.add()
        group.isSelectable = False
        group.isChildrenSelectable = False
        try:
            if not add_target_arrow(group, bounds, offset):
                group.deleteMe()
                return False
        except Exception:
            self._delete(group)
            return False
        self.guidance_group = group
        return True

    def clear(self):
        self.clear_guidance()
        self.clear_hud()
        self.clear_pointer()
        self._delete(self.animation_group)
        self.animation_group = None
        self._delete(self.group)
        self.group = None
        self._refresh()

    def _refresh(self):
        try:
            self.app.activeViewport.refresh()
        except Exception:
            pass

    @staticmethod
    def _offset(value):
        if isinstance(value, (list, tuple)) and len(value) == 3:
            return value
        return [15.0, 0.0, 0.0]

    # --- spatial guidance --------------------------------------------------------------
    def _detector(self, step, previous):
        key = (step.get("id"), id(previous))
        entry = self._detectors.get(key)
        if entry is None or entry[0] is not previous:
            if len(self._detectors) > 64:
                self._detectors.clear()
            entry = (previous, ChangeDetector(previous, step.get("geometry", {}).get("meshes", [])), {})
            self._detectors[key] = entry
        return entry

    def guided(self, step, meshes, previous, budget=MAX_EXAMINED):
        """(unchanged meshes, changed meshes). No previous snapshot known or
        too much geometry to compare: nothing is marked as changed."""
        if previous is None or not meshes:
            return meshes, []
        try:
            _, detector, cache = self._detector(step, previous)
            if id(meshes) in cache and cache[id(meshes)][0] is meshes:
                return cache[id(meshes)][1]
            if detector.examined_count(meshes) > budget:
                return meshes, []
            split = detector.split(meshes)
        except Exception:
            return meshes, []
        if split is None:
            return meshes, []
        if budget >= MAX_EXAMINED:
            cache[id(meshes)] = (meshes, split)       # the step's final snapshot
        return split

    @staticmethod
    def _change_effect():
        color = adsk.core.Color.create(*CHANGE_COLOR)
        try:
            return adsk.fusion.CustomGraphicsBasicMaterialColorEffect.create(
                color, adsk.core.Color.create(10, 92, 83, 255), adsk.core.Color.create(60, 60, 60, 255),
                adsk.core.Color.create(0, 0, 0, 255), 5.0, 1.0)
        except Exception:
            return adsk.fusion.CustomGraphicsSolidColorEffect.create(color)

    def _create_group(self, meshes, offset, name, changed=()):
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        if not design:
            return None
        group = design.rootComponent.customGraphicsGroups.add()
        group.name = name
        group.isChildrenSelectable = False
        group.isSelectable = False
        try:
            for mesh_data in meshes:
                flat = []
                for x, y, z in mesh_data["vertices"]:
                    flat.extend((x + offset[0], y + offset[1], z + offset[2]))
                triangles = [index for face in mesh_data["triangles"] for index in face]
                coords = adsk.fusion.CustomGraphicsCoordinates.create(flat)
                entity = group.addMesh(coords, triangles, [], [])
                if not entity:
                    raise RuntimeError("Fusion refused to draw the animation/reference mesh")
                entity.isSelectable = False
            if changed:
                effect = self._change_effect()
                for mesh_data in changed:
                    flat = []
                    for x, y, z in mesh_data["vertices"]:
                        flat.extend((x + offset[0], y + offset[1], z + offset[2]))
                    triangles = [index for face in mesh_data["triangles"] for index in face]
                    entity = group.addMesh(adsk.fusion.CustomGraphicsCoordinates.create(flat), triangles, [], [])
                    if not entity:
                        raise RuntimeError("Fusion refused to draw the step highlight")
                    entity.color = effect
                    entity.isSelectable = False
        except Exception:
            self._delete(group)
            raise
        return group

    def render(self, step, offset=None, previous=None):
        """Draw the step's snapshot. With ``previous`` (the previous step's
        snapshot, [] for the first step) what this step changed is teal."""
        self.clear()
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        if not design:
            return False
        self.last_step = step
        self.last_offset = offset
        self.last_previous = previous
        if not self.visible:
            return True
        meshes = step.get("geometry", {}).get("meshes", [])
        if meshes:
            plain, changed = self.guided(step, meshes, previous)
            self.group = self._create_group(plain, self._offset(offset), "exCADmple reference (read-only)", changed)
            self.render_target_arrow(changed, self._offset(offset))
        self._refresh()
        return True

    def render_animation(self, step, offset, progress, previous=None):
        """Redraw only the transient animation group at a requested progress.

        A live Fusion Python event is required; this cannot be tested with the
        standalone unit tests. Never change the user's native feature state.
        """
        if not step.get("animation"):
            return False
        if not self.visible:
            return True
        meshes = animation_meshes(step["animation"], progress)
        plain, changed = self.guided(step, meshes, previous, FRAME_BUDGET)
        # Hide the completed reference mesh before rendering partial geometry.
        if self.group and self.group.isValid:
            self.group.isVisible = False
        self._delete(self.animation_group)
        self.animation_group = None
        try:
            self.animation_group = self._create_group(
                plain, self._offset(offset),
                "exCADmple step animation (temporary)", changed
            )
            self._refresh()
            return True
        except Exception:
            if self.group and self.group.isValid:
                self.group.isVisible = True
            raise

    def render_pointer(self, step, offset, progress):
        """Draw the Ghost Pointer: a small marker, its recent trail and a
        ring while it presses (click / drag). Never moves the real mouse."""
        self.clear_pointer()
        points = step.get("pointer")
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        if not points or not design or not self.visible:
            return False
        state = sample_pointer(points, progress * step.get("duration_ms", 8000))
        o = self._offset(offset)
        x, y, z = (state["xyz"][i] + o[i] for i in range(3))
        group = design.rootComponent.customGraphicsGroups.add()
        group.isSelectable = False
        color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*POINTER_COLOR))
        try:
            r = 0.32 if state["pressed"] else 0.22
            tip = [x, y, z]
            verts = [x + r, y, z + r, x - r, y, z + r, x, y + r, z + r, x, y - r, z + r,
                     x, y, z + 2.2 * r] + tip
            # an inverted pyramid "cursor" pointing at the model
            tris = [5, 0, 2, 5, 2, 1, 5, 1, 3, 5, 3, 0, 4, 2, 0, 4, 1, 2, 4, 3, 1, 4, 0, 3]
            marker = group.addMesh(adsk.fusion.CustomGraphicsCoordinates.create(verts), tris, [], [])
            marker.color = color
            marker.depthPriority = 2
            trail = [c + o[i % 3] for point in state["trail"] for i, c in enumerate(point)]
            if len(trail) >= 6:
                lines = group.addLines(adsk.fusion.CustomGraphicsCoordinates.create(trail), [], True)
                lines.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*TRAIL_COLOR))
                lines.weight = 2
                lines.depthPriority = 1
            if state["pressed"]:
                ring = []
                for k in range(25):
                    a = 2 * math.pi * k / 24
                    ring.extend((x + 0.55 * math.cos(a), y + 0.55 * math.sin(a), z))
                circle = group.addLines(adsk.fusion.CustomGraphicsCoordinates.create(ring), [], True)
                circle.color = color
                circle.weight = 3
                circle.depthPriority = 2
        except Exception:
            self._delete(group)
            raise
        self.pointer_group = group
        self._refresh()
        return True

    def finish_animation(self):
        """Return to the original complete step reference mesh."""
        self.clear_animation()

    def set_visible(self, visible):
        self.visible = bool(visible)
        if not self.visible:
            self.clear_pointer()
            self.clear_hud()
            for overlay in (self.guidance_group, self.command_group):
                if overlay and overlay.isValid:
                    overlay.isVisible = False
            if self.group and self.group.isValid:
                self.group.isVisible = False
            if self.animation_group and self.animation_group.isValid:
                self.animation_group.isVisible = False
        elif self.animation_group and self.animation_group.isValid:
            self.animation_group.isVisible = True
            for overlay in (self.guidance_group, self.command_group):
                if overlay and overlay.isValid:
                    overlay.isVisible = True
        elif self.group and self.group.isValid:
            self.group.isVisible = True
            for overlay in (self.guidance_group, self.command_group):
                if overlay and overlay.isValid:
                    overlay.isVisible = True
        elif self.visible and self.last_step:
            self.render(self.last_step, self.last_offset, self.last_previous)
            return
        self._refresh()
