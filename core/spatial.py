"""Spatial step links and reversible native Fusion Focus Mode.

The blue Custom Graphics overlay is transient. Focus additionally snapshots
native body opacity before dimming background geometry and restores it on
step changes, save, document deactivation, or add-in stop.
Never changes CAD geometry or the feature timeline.
"""
import adsk.core
import adsk.fusion

from .geometry_links import GeometryLinks
from .focus import OpacityFocus, FocusError


def _design(app):
    return adsk.fusion.Design.cast(app.activeProduct)


def _document_key(app, design):
    if not design:
        return ""
    # The root's token refers to this model, unlike a package-local step id.
    # Document name alone is not sufficient for two same-named open models.
    try:
        token = design.rootComponent.entityToken
        if token:
            return str(token)
    except Exception:
        pass
    try:
        data_file = app.activeDocument.dataFile
        if data_file:
            return str(data_file.id)
    except Exception:
        pass
    return ""  # Fail closed: no cross-document linking without identity.


def _describe(entity):
    body = adsk.fusion.BRepBody.cast(entity)
    if body:
        return "body", body.name or "BRep body"
    face = adsk.fusion.BRepFace.cast(entity)
    if face:
        return "face", (face.body.name or "Body") + " · selected face"
    occurrence = adsk.fusion.Occurrence.cast(entity)
    if occurrence:
        return "occurrence", occurrence.fullPathName or occurrence.name
    return None, None


def _entity_for_display(entity):
    """Highlight an actual BRep body. For faces highlight parent body.

    Precise face selection is available separately through Locate; treating
    a full-body overlay as a face-only highlight would be misleading.
    """
    body = adsk.fusion.BRepBody.cast(entity)
    if body:
        return [body], "body"
    face = adsk.fusion.BRepFace.cast(entity)
    if face:
        return [face.body], "parent body"
    occurrence = adsk.fusion.Occurrence.cast(entity)
    if occurrence:
        return [occurrence.bRepBodies.item(i) for i in range(occurrence.bRepBodies.count)], "component"
    return [], ""


def _native_body(body):
    native = getattr(body, "nativeObject", None)
    return native if native is not None else body


def _body_token(body):
    native = _native_body(body)
    try:
        return str(native.entityToken)
    except Exception:
        return None


def _model_bodies(design):
    """Enumerate each *native* body once, even for repeated occurrences."""
    components = design.allComponents
    seen = set()
    for i in range(components.count):
        comp = components.item(i)
        for attr in ("bRepBodies", "meshBodies"):
            bodies = getattr(comp, attr, None)
            if not bodies:
                continue
            for index in range(bodies.count):
                body = _native_body(bodies.item(index))
                token = _body_token(body)
                if not token or token in seen:
                    continue
                seen.add(token)
                yield token, body


def _protected_tokens(entity):
    """Return the native source body set that must retain its original opacity.

    Shared source components can be instantiated multiple times: dimming a
    source body also dims every instance. Protect all those instances rather
    than unintentionally fading the chosen occurrence itself.
    """
    target = adsk.fusion.BRepBody.cast(entity)
    if target:
        token = _body_token(target)
        return {token} if token else set()
    face = adsk.fusion.BRepFace.cast(entity)
    if face:
        token = _body_token(face.body)
        return {token} if token else set()
    occurrence = adsk.fusion.Occurrence.cast(entity)
    if not occurrence:
        return set()
    protected = set()
    queue = [occurrence]
    while queue:
        current = queue.pop()
        bodies = current.bRepBodies
        for i in range(bodies.count):
            token = _body_token(bodies.item(i))
            if token:
                protected.add(token)
        meshes = current.meshBodies
        for i in range(meshes.count):
            token = _body_token(meshes.item(i))
            if token:
                protected.add(token)
        children = current.childOccurrences
        for i in range(children.count):
            queue.append(children.item(i))
    return protected


class SpatialLinkController:
    def __init__(self, app, ui):
        self.app = app
        self.ui = ui
        self.links = GeometryLinks()
        self.group = None
        self.last_step_id = None
        self.focus_enabled = True
        self.focus = OpacityFocus(self._resolve_body_token, self.document_key)

    def _resolve_body_token(self, token):
        design = _design(self.app)
        if not design:
            return None
        try:
            for candidate in design.findEntityByToken(token) or []:
                native = _native_body(candidate)
                if _body_token(native) == token:
                    return native
        except Exception:
            pass
        return None

    def document_key(self):
        design = _design(self.app)
        return _document_key(self.app, design)

    def clear_overlay(self):
        # Restore user-owned appearance before discarding a focus session.
        # Do not silently swallow a failed restore.
        self.focus.restore()
        try:
            if self.group and self.group.isValid:
                self.group.deleteMe()
        except Exception:
            pass
        self.group = None
        try:
            self.app.activeViewport.refresh()
        except Exception:
            pass

    def reset_example(self):
        self.clear_overlay()
        self.links.clear()
        self.last_step_id = None

    def bind_selected(self, step_id):
        design = _design(self.app)
        doc_key = self.document_key()
        if not design or not doc_key:
            raise ValueError("Open the source Fusion design before linking a step.")
        selections = self.ui.activeSelections
        if selections.count != 1:
            raise ValueError("Select exactly one body, face, or component in the Fusion canvas, then click Link selected.")
        entity = selections.item(0).entity
        kind, label = _describe(entity)
        if not kind:
            raise ValueError("Select a BRep body, BRep face or assembly occurrence; other objects are not supported yet.")
        token = entity.entityToken
        if not token:
            raise ValueError("Fusion did not provide a persistent token for this selected entity.")
        link = self.links.bind(step_id, doc_key, token, label, kind)
        return link.for_ui(True)

    def display_links(self, steps):
        return self.links.display(steps, self.document_key())

    def unbind(self, step_id):
        self.links.remove(step_id)
        self.clear_overlay()

    def resolve(self, step_id):
        design = _design(self.app)
        if not design:
            return None, "No Fusion design is active"
        link = self.links.get(step_id, self.document_key())
        if link is None:
            return None, "No linked geometry for this step in the active design"
        try:
            results = design.findEntityByToken(link.token) or []
        except Exception:
            results = []
        if not results:
            return None, "The linked entity no longer exists; its topology may have changed"
        # A split face can resolve to multiple faces. Never silently pick one
        # and call it the original without informing the user.
        if len(results) > 1:
            return None, "This entity now resolves to multiple geometric entities; rebind the step"
        kind, _ = _describe(results[0])
        if kind != link.kind:
            return None, "The bound entity changed type; rebind the step"
        return results[0], ""

    def highlight(self, step_id):
        self.last_step_id = step_id
        self.clear_overlay()
        entity, message = self.resolve(step_id)
        if not entity:
            return False, message
        bodies, scope = _entity_for_display(entity)
        if not bodies:
            return False, "This occurrence has no BRep bodies to highlight"
        design = _design(self.app)
        group = design.rootComponent.customGraphicsGroups.add()
        group.name = "exCADmple step-linked geometry (temporary)"
        group.isChildrenSelectable = False
        group.isSelectable = False
        effect = adsk.fusion.CustomGraphicsSolidColorEffect.create(
            adsk.core.Color.create(83, 127, 191, 255)
        )
        added = 0
        try:
            for body in bodies:
                if not body or not body.isValid:
                    continue
                overlay = group.addBRepBody(body)
                if not overlay:
                    continue
                overlay.color = effect
                overlay.setOpacity(0.28, True)
                overlay.isSelectable = False
                added += 1
            if not added:
                group.deleteMe()
                return False, "Fusion could not draw the geometry overlay"
            self.group = group
            focus_count = 0
            focus_warning = ""
            if self.focus_enabled:
                try:
                    protected = _protected_tokens(entity)
                    focus_count = self.focus.apply(
                        self.document_key(), _model_bodies(design), protected, dim_opacity=0.24
                    )
                except FocusError as error:
                    focus_warning = str(error)
            self.app.activeViewport.refresh()
            suffix = ("; {} background bodies dimmed".format(focus_count)
                      if focus_count else "")
            if focus_warning:
                suffix += "; Focus unavailable: " + focus_warning
            if scope == "parent body":
                return True, "Linked face: parent body highlighted" + suffix + ". Use Locate to select the exact face."
            return True, "Linked " + scope + " highlighted in Fusion" + suffix
        except Exception:
            try:
                group.deleteMe()
            except Exception:
                pass
            self.group = None
            raise

    def set_focus_enabled(self, enabled):
        self.focus_enabled = bool(enabled)
        if self.last_step_id is not None:
            return self.highlight(self.last_step_id)
        self.clear_overlay()
        return True, "Focus Mode " + ("enabled" if enabled else "disabled")

    def locate(self, step_id):
        entity, message = self.resolve(step_id)
        if not entity:
            return False, message
        # Explicit user request only: selection can replace existing selection,
        # so never do this automatically when merely browsing example steps.
        self.ui.activeSelections.clear()
        if not self.ui.activeSelections.add(entity):
            return False, "Fusion could not select the linked entity"
        return True, "Selected linked geometry in Fusion (press Esc to clear)"

    def restore(self):
        if self.last_step_id is not None:
            return self.highlight(self.last_step_id)
        return False, ""
