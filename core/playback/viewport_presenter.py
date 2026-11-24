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

    def open(self):
        prior = self.ui.palettes.itemById(self.PALETTE_ID)
        if prior and prior.isValid:
            prior.deleteMe()
        self.palette = self.ui.palettes.add2(
            self.PALETTE_ID, "exCADmple · In-viewport demonstration",
            self.url, True, True, True, 390, 355)
        self.palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
        self.palette.setPosition(520, 190)
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
            if x > 1070:
                x -= 440
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
        should_move = (
            self.last_position is None or
            index != self.last_index or phase != self.last_phase or
            (self.last_position and
             abs(x-self.last_position[0])+abs(y-self.last_position[1]) > 110))
        if should_move and self.palette and self.palette.isValid:
            try:
                self.palette.setPosition(*target)
                self.last_position = target
            except Exception as error:
                self.log("Viewport walkthrough position: " + str(error))
        self.last_index = index
        self.last_phase = phase

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
