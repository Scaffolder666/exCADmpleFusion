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


class ReferenceRenderer:
    def __init__(self, app):
        self.app = app
        self.group = None
        self.animation_group = None
        self.pointer_group = None
        self.hud_group = None
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

    def clear(self):
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
            if self.group and self.group.isValid:
                self.group.isVisible = False
            if self.animation_group and self.animation_group.isValid:
                self.animation_group.isVisible = False
        elif self.animation_group and self.animation_group.isValid:
            self.animation_group.isVisible = True
        elif self.group and self.group.isValid:
            self.group.isVisible = True
        elif self.visible and self.last_step:
            self.render(self.last_step, self.last_offset, self.last_previous)
            return
        self._refresh()
