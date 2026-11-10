"""Fusion side of tutorial recording (see core/session_log.py).

While the designer models and thinks aloud, this logs the tools they start,
the timeline features that appear, and the 3D points they select. Start it
together with the screen recording; the log is saved as session.json and
used by tools/author.py to cut the recording into steps.
Nothing in the design is changed.
"""
import json

import adsk.core
import adsk.fusion

from .session_log import SessionLog
from .playback.him_fusion import _items
from .playback.him_motion import short_kind


def timeline_items(design):
    out = []

    def walk(collection):
        for obj in _items(collection):
            try:
                if obj.isGroup:
                    walk(adsk.fusion.TimelineGroup.cast(obj))
                    continue
                entity = obj.entity
                if entity is None:
                    continue
                out.append((obj.index, getattr(entity, "name", "") or "",
                            short_kind(getattr(entity, "objectType", ""))))
            except Exception:
                continue
    if design:
        walk(design.timeline)
    return out


def selection_point(entity):
    """A representative 3D point (cm) for a selected entity, or None."""
    try:
        face = adsk.fusion.BRepFace.cast(entity)
        if face:
            p = face.pointOnFace
            return (p.x, p.y, p.z), "face"
        edge = adsk.fusion.BRepEdge.cast(entity)
        if edge:
            p = edge.pointOnEdge
            return (p.x, p.y, p.z), "edge"
        vertex = adsk.fusion.BRepVertex.cast(entity)
        if vertex:
            p = vertex.geometry
            return (p.x, p.y, p.z), "vertex"
        body = adsk.fusion.BRepBody.cast(entity)
        if body:
            box = body.boundingBox
            return tuple((getattr(box.minPoint, a) + getattr(box.maxPoint, a)) / 2 for a in "xyz"), "body"
        point = adsk.fusion.SketchPoint.cast(entity)
        if point:
            p = point.worldGeometry
            return (p.x, p.y, p.z), "sketch point"
        curve = adsk.fusion.SketchCurve.cast(entity)
        if curve:
            box = curve.boundingBox
            return tuple((getattr(box.minPoint, a) + getattr(box.maxPoint, a)) / 2 for a in "xyz"), "sketch curve"
    except Exception:
        pass
    return None, None


class _CommandStarting(adsk.core.ApplicationCommandEventHandler):
    def __init__(self, recorder):
        super().__init__()
        self.recorder = recorder

    def notify(self, args):
        try:
            definition = args.commandDefinition
            self.recorder.log.command(args.commandId, definition.name if definition else args.commandId)
        except Exception:
            pass


class _CommandTerminated(adsk.core.ApplicationCommandEventHandler):
    def __init__(self, recorder):
        super().__init__()
        self.recorder = recorder

    def notify(self, args):
        try:
            self.recorder.check_timeline()
        except Exception:
            pass


class _SelectionChanged(adsk.core.ActiveSelectionEventHandler):
    def __init__(self, recorder):
        super().__init__()
        self.recorder = recorder

    def notify(self, args):
        try:
            selections = args.currentSelection
            if selections.count:
                xyz, kind = selection_point(selections.item(selections.count - 1).entity)
                self.recorder.log.selection(xyz, kind)
        except Exception:
            pass


class SessionRecorder:
    def __init__(self, app, ui):
        self.app, self.ui = app, ui
        self.log = None
        self._handlers = []

    @property
    def recording(self):
        return self.log is not None

    def design(self):
        return adsk.fusion.Design.cast(self.app.activeProduct)

    def start(self):
        if self.recording:
            return "Already recording."
        design = self.design()
        if not design:
            raise ValueError("Open the design you are going to model first")
        ok = self.ui.messageBox(
            "Start your screen recording now (with your microphone on), then press OK.\n\n"
            "exCADmple starts its log at the same moment: the tools you use, the features you "
            "create and what you select. Think aloud while you model.",
            "Record a tutorial", adsk.core.MessageBoxButtonTypes.OKCancelButtonType)
        if ok != adsk.core.DialogResults.DialogOK:
            return "Recording not started."
        self.log = SessionLog()
        self.log.baseline(timeline_items(design))
        for event, handler in ((self.ui.commandStarting, _CommandStarting(self)),
                               (self.ui.commandTerminated, _CommandTerminated(self)),
                               (self.ui.activeSelectionChanged, _SelectionChanged(self))):
            event.add(handler)
            self._handlers.append((event, handler))
        return "Recording. Stop it when you stop the screen recording."

    def check_timeline(self):
        if self.log is not None:
            self.log.timeline(timeline_items(self.design()))

    def _detach(self):
        for event, handler in self._handlers:
            try:
                event.remove(handler)
            except Exception:
                pass
        self._handlers.clear()

    def stop(self):
        if not self.recording:
            return "Not recording."
        self.check_timeline()
        data = self.log.to_dict()
        self.log = None
        self._detach()
        dialog = self.ui.createFileDialog()
        dialog.title = "Save the recording log"
        dialog.filter = "exCADmple session (*.session.json)"
        dialog.initialFilename = "tutorial.session.json"
        if dialog.showSave() != adsk.core.DialogResults.DialogOK:
            return "Recording stopped; the log was not saved."
        with open(dialog.filename, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=1)
        return "Saved %d tools, %d features, %d selections to %s" % (
            len(data["commands"]), len(data["features"]), len(data["selections"]), dialog.filename)

    def cancel(self):
        self.log = None
        self._detach()
