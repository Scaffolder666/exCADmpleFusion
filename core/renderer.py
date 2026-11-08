"""Read-only transient reference geometry and non-destructive animated previews.

The feature animation uses a bounded number of frame updates from the HTML
palette. The model's native history marker and feature parameters are untouched.
"""
import adsk.core
import adsk.fusion

from .animation import extrude_mesh, reveal_meshes, operation_meshes


class ReferenceRenderer:
    def __init__(self, app):
        self.app = app
        self.group = None
        self.animation_group = None
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

    def clear(self):
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
        animation = step["animation"]
        if animation["type"] == "reveal":
            meshes = reveal_meshes(animation, progress)
        elif animation["type"] == "extrude":
            meshes = list(animation.get("context_meshes", [])) + [extrude_mesh(animation, progress)]
        else:
            meshes = operation_meshes(animation, progress)
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

    def finish_animation(self):
        """Return to the original complete step reference mesh."""
        self.clear_animation()

    def set_visible(self, visible):
        self.visible = bool(visible)
        if not self.visible:
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
