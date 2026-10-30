"""Transient reference meshes: does not create/roll back native Fusion features."""
import adsk.core
import adsk.fusion


class ReferenceRenderer:
    def __init__(self, app):
        self.app = app
        self.group = None
        self.visible = True
        self.last_step = None

    def clear(self):
        try:
            if self.group and self.group.isValid:
                self.group.deleteMe()
        except Exception:
            pass
        self.group = None
        self._refresh()

    def _refresh(self):
        try:
            self.app.activeViewport.refresh()
        except Exception:
            pass

    def render(self, step, offset=None):
        """All geometry operations happen on Fusion's main thread.

        Only transient Custom Graphics are changed. The design's feature
        timeline and marker position are never touched.
        """
        self.clear()
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        if not design:
            return False
        meshes = step.get("geometry", {}).get("meshes", [])
        self.last_step = step
        if not self.visible or not meshes:
            return True
        offset = offset or [15.0, 0.0, 0.0]
        if not isinstance(offset, list) or len(offset) != 3:
            offset = [15.0, 0.0, 0.0]
        group = design.rootComponent.customGraphicsGroups.add()
        group.name = "exCADmple reference (read-only)"
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
                    raise RuntimeError("Fusion refused to create the reference mesh")
                entity.isSelectable = False
            self.group = group
            self._refresh()
            return True
        except Exception:
            try:
                group.deleteMe()
            except Exception:
                pass
            self.group = None
            raise

    def set_visible(self, visible):
        self.visible = bool(visible)
        if self.group and self.group.isValid:
            self.group.isVisible = self.visible
        self._refresh()
