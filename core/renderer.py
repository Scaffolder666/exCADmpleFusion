"""Read-only transient reference geometry and non-destructive animated previews.

The feature animation uses a bounded number of frame updates from the HTML
palette. The model's native history marker and feature parameters are untouched.
"""
import adsk.core
import adsk.fusion

import math

from .animation import animation_meshes
from .pointer import sample as sample_pointer

POINTER_COLOR = (245, 140, 20, 255)
TRAIL_COLOR = (250, 190, 90, 255)


class ReferenceRenderer:
    def __init__(self, app):
        self.app = app
        self.group = None
        self.animation_group = None
        self.pointer_group = None
        self.visible = True
        self.last_step = None
        self.last_offset = None

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

    def clear(self):
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

    def _create_group(self, meshes, offset, name):
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
        except Exception:
            self._delete(group)
            raise
        return group

    def render(self, step, offset=None):
        self.clear()
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        if not design:
            return False
        self.last_step = step
        self.last_offset = offset
        if not self.visible:
            return True
        meshes = step.get("geometry", {}).get("meshes", [])
        if meshes:
            self.group = self._create_group(meshes, self._offset(offset), "exCADmple reference (read-only)")
        self._refresh()
        return True

    def render_animation(self, step, offset, progress):
        """Redraw only the transient animation group at a requested progress.

        A live Fusion Python event is required; this cannot be tested with the
        standalone unit tests. Never change the user's native feature state.
        """
        if not step.get("animation"):
            return False
        if not self.visible:
            return True
        meshes = animation_meshes(step["animation"], progress)
        # Hide the completed reference mesh before rendering partial geometry.
        if self.group and self.group.isValid:
            self.group.isVisible = False
        self._delete(self.animation_group)
        self.animation_group = None
        try:
            self.animation_group = self._create_group(
                meshes, self._offset(offset),
                "exCADmple step animation (temporary)"
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
            if self.group and self.group.isValid:
                self.group.isVisible = False
            if self.animation_group and self.animation_group.isValid:
                self.animation_group.isVisible = False
        elif self.animation_group and self.animation_group.isValid:
            self.animation_group.isVisible = True
        elif self.group and self.group.isValid:
            self.group.isVisible = True
        elif self.visible and self.last_step:
            self.render(self.last_step, self.last_offset)
            return
        self._refresh()
