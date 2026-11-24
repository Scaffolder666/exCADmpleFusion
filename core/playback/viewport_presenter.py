"""Fusion-native in-viewport walkthrough presentation.

Not a second Viewport. A floating Palette is placed over the learner's
single existing Fusion CAD canvas; Custom Graphics from HiM continue to draw
the read-only source model there. The Palette contains the real operation
video crop and contextual callouts. The *right-side* Palette remains playback
controls only.

This module NEVER runs modeling commands, changes selection or changes the
learner's Timeline. The learner can continue modeling behind the movable
teaching card.
"""
import json

import adsk.core


class ViewportPresentation:
    PALETTE_ID = "excadmple_viewport_walkthrough"

    def __init__(self, app, ui, url, log=None):
        self.app = app
        self.ui = ui
        self.url = url
        self.log = log or (lambda *_: None)
        self.palette = None
        self.ready = False
        self.last_payload = None
        self.last_anchor = None
        self.last_phase = ""
        self.last_index = -1
        self.visible = False
        self.last_position = None
        self.last_size = None
        self.manually_positioned = False

    def open(self):
        prior = self.ui.palettes.itemById(self.PALETTE_ID)
        if prior and prior.isValid:
            prior.deleteMe()
        # Autodesk added transparent API palettes in March 2024. This
        # presents tutorial video/callouts directly over the existing
        # graphics viewport, instead of a conventional opaque side window.
        try:
            self.palette = self.ui.palettes.addTransparent(
                self.PALETTE_ID, "exCADmple · In-viewport demonstration",
                self.url, False, False, False, False, 400, 330)
        except Exception as error:
            self.log("Transparent viewport palette unavailable; using floating fallback: " + str(error))
            self.palette = self.ui.palettes.add2(
                self.PALETTE_ID, "exCADmple · In-viewport demonstration",
                self.url, False, False, True, 400, 330)
        self.palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
        try:
            self.palette.setPosition(520, 190)
            self.last_position = (520, 190)
        except Exception as error:
            self.log("Viewport walkthrough initial position: " + str(error))
        self.palette.isVisible = False
        self.ready = False

    def acknowledge_ready(self):
        self.ready = True
        if self.visible and self.last_payload:
            self._send("frame", self.last_payload)

    def _send(self, action, payload):
        if not self.ready or not self.palette or not self.palette.isValid:
            return
        try:
            self.palette.sendInfoToHTML(action, json.dumps(payload, ensure_ascii=False))
        except Exception as error:
            self.log("Viewport walkthrough HTML: " + str(error))

    def _position(self, session, index, phase):
        anchor = projected_reference_anchor(self.app, session, index)
        # Place the visual tutorial near the relevant *3D feature*, not in
        # the right playback panel. Avoid camera movements entirely.
        if anchor is not None:
            x, y = anchor
            width = self.last_size[0] if self.last_size else 400
            if x > 1070:
                x -= (width + 50)
            else:
                x += 75
            y = y - 105
            x = max(45, int(x))
            y = max(105, int(y))
        else:
            # The floating teaching card remains over the existing viewport
            # and is movable by the designer if a feature can't be projected.
            x, y = (500, 175)
        target = (x, y)
        # Let the learner orbit/zoom without a teaching card chasing their camera.
        should_move = not self.manually_positioned and (
            self.last_position is None or
            index != self.last_index or phase != self.last_phase)
        if should_move and self.palette and self.palette.isValid:
            try:
                self.palette.setPosition(*target)
                self.last_position = target
            except Exception as error:
                self.log("Viewport walkthrough position: " + str(error))
        self.last_index = index
        self.last_phase = phase

    def shift(self, dx, dy):
        """Drag teaching callout from its in-canvas handle, not the OS mouse."""
        if not self.palette or not self.palette.isValid:
            return
        dx = max(-120, min(120, int(dx)))
        dy = max(-120, min(120, int(dy)))
        x, y = self.last_position or (520, 190)
        target = (max(20, x + dx), max(70, y + dy))
        try:
            self.palette.setPosition(*target)
            self.last_position = target
            self.manually_positioned = True
        except Exception as error:
            self.log("Viewport callout drag: " + str(error))

    def follow(self):
        """Return to automatic reference-Feature anchoring after manual drag."""
        self.manually_positioned = False
        self.last_position = None

    def _resize(self, payload):
        # Avoid obscuring the modeling canvas when no actual video is shown.
        size = ((400, 415) if payload.get("show_video") else
                (400, 324) if payload.get("phase") == "why" else
                (400, 292))
        if size != self.last_size and self.palette and self.palette.isValid:
            try:
                self.palette.setSize(*size)
                self.last_size = size
            except Exception as error:
                self.log("Viewport callout resize: " + str(error))

    def present(self, payload, session=None):
        self.last_payload = payload
        self.visible = bool(payload and payload.get("visible"))
        if not self.palette or not self.palette.isValid:
            return
        if not self.visible:
            self.palette.isVisible = False
            self._send("reset", {})
            return
        if not self.palette.isVisible:
            self.palette.isVisible = True
        index, phase = payload["index"], payload["phase"]
        self._resize(payload)
        self._position(session, index, phase)
        self._send("frame", payload)

    def hide(self):
        self.visible = False
        self.last_payload = None
        self.last_index = -1
        self.last_phase = ""
        if self.palette and self.palette.isValid:
            self._send("reset", {})
            self.palette.isVisible = False

    def close(self):
        self.hide()
        if self.palette and self.palette.isValid:
            try:
                self.palette.deleteMe()
            except Exception:
                pass
        self.palette = None
        self.ready = False


def _bbox_center(entity):
    bounds = getattr(entity, "boundingBox", None)
    if bounds is None:
        for key in ("bodies", "faces", "edges"):
            group = getattr(entity, key, None)
            try:
                if group and group.count:
                    bounds = getattr(group.item(0), "boundingBox", None)
                    if bounds:
                        break
            except Exception:
                continue
    if bounds is None:
        return None
    a, b = bounds.minPoint, bounds.maxPoint
    return ((a.x+b.x)*.5, (a.y+b.y)*.5, (a.z+b.z)*.5)


def projected_reference_anchor(app, session, step_index):
    """Actual source feature's 3D bbox center projected into screen pixels.

    The source Design remains in its independent .f3d document. Its geometry
    appears in the user's one Viewport through an offset CustomGraphics copy.
    No viewport camera or user geometry is touched.
    """
    try:
        if (not session or not session.live or not session.presenter.attached or
                not 0 <= step_index < len(session.mapped)):
            return None
        for feature in reversed(session.mapped[step_index]):
            obj = session.model.entity(feature)
            xyz = _bbox_center(obj)
            if xyz is None:
                continue
            offset = session.presenter.offset
            world = adsk.core.Point3D.create(
                xyz[0] + offset[0], xyz[1] + offset[1], xyz[2] + offset[2])
            viewport = app.activeViewport
            screen = viewport.viewToScreen(viewport.modelToViewSpace(world))
            if screen is not None and screen.x >= 0 and screen.y >= 0:
                return (float(screen.x), float(screen.y))
    except Exception:
        return None
    return None
