"""exCADmple MVP: design-process player in Autodesk Fusion.

Start by running this Add-In from Utilities > Scripts and Add-Ins.
Only Custom Graphics are changed; no native feature history is replayed.
"""
import json
import threading
import traceback
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import adsk.core
import adsk.fusion

from core.packages import open_package, PackageError
from core.renderer import ReferenceRenderer
from core.history import history_step_indices, HistoryError
from core.fusion_history import scan_candidate_features, trace_direct_creators, trace_feature_inputs
from core.spatial import SpatialLinkController
from core.him_fusion import HiMController

PALETTE_ID = "excadmple.fusion.player"
COMMAND_ID = "excadmple.fusion.open"
HIM_PALETTE_ID = "excadmple.fusion.him"
HIM_COMMAND_ID = "excadmple.fusion.him.open"
HIM_TICK_EVENT = "excadmple.fusion.him.tick"
_him = None
_him_palette = None
_him_event = None
_him_ticker = None
_him_command_def = None
_him_command_control = None
_app = None
_ui = None
_palette = None
_renderer = None
_spatial = None
_package = None
_step_index = 0
_handlers = []
_command_def = None
_command_control = None
_saving_document = False


def _post(action, payload):
    if _palette and _palette.isValid:
        _palette.sendInfoToHTML(action, json.dumps(payload))


def _post_him(action, payload):
    if _him_palette and _him_palette.isValid:
        _him_palette.sendInfoToHTML(action, json.dumps(payload))


def _him_status(message, is_error=False):
    _post_him("status", {"message": message, "error": is_error})


class _HiMTicker(threading.Thread):
    """Requests animation frames on Fusion's main thread via a custom event.
    A new frame is only requested after the previous one was rendered, so the
    frame rate adapts to how long Fusion needs to recompute the model."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stopped = threading.Event()
        self.idle = threading.Event()
        self.idle.set()

    def run(self):
        while not self.stopped.wait(0.01):
            if _him and _him.playback.playing and self.idle.is_set():
                self.idle.clear()
                try:
                    _app.fireCustomEvent(HIM_TICK_EVENT, "")
                except Exception:
                    self.idle.set()


class HiMTickHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            if _him:
                _him.tick()
        except Exception as error:
            try:
                _him.stop()
            except Exception:
                pass
            _him_status("Animation stopped: " + str(error), True)
            _log_error()
        finally:
            if _him_ticker:
                _him_ticker.idle.set()


def _him_explain(entity):
    if not _him or _him.busy:
        return
    if not (_him_palette and _him_palette.isValid and _him_palette.isVisible):
        return
    try:
        _him_status("Analysing the modeling history…")
        _him.explain(entity)
    except Exception as error:
        _him_status(str(error), True)
        _log_error()


class HiMPaletteHandler(adsk.core.HTMLEventHandler):
    def notify(self, args):
        try:
            command = args.action
            body = json.loads(args.data or "{}")
            if command == "him_ready":
                if _him and _him.result:
                    _post_him("him_result", _him.describe())
                else:
                    entity = _selected_native_entity()
                    if entity:
                        _him_explain(entity)
            elif command == "him_command":
                _him.command(body.get("name"), body.get("value"))
            elif command == "him_show_more":
                _him.show_more()
            elif command == "him_edit":
                _him_status(_him.edit_feature(int(body["position"])))
            elif command == "him_set_parameter":
                _him_status(_him.set_parameter(int(body["position"]), str(body["name"]),
                                               str(body["expression"])))
            else:
                raise ValueError("Unknown action: " + str(command))
            args.returnData = json.dumps({"ok": True})
        except Exception as error:
            _him_status(str(error), True)
            args.returnData = json.dumps({"ok": False, "error": str(error)})
            _log_error()


def _status(message, is_error=False):
    _post("status", {"message": message, "error": is_error})


def _post_links():
    if _package and _spatial:
        _post("links", {"by_step": _spatial.display_links(_package.data["steps"])})


def _set_step(index, announce=False):
    global _step_index
    if not _package:
        return
    if not isinstance(index, int) or index < 0 or index >= len(_package.data["steps"]):
        raise PackageError("Step out of range")
    _step_index = index
    step = _package.step(index)
    success = _renderer.render(step, _package.data.get("reference_offset_cm"))
    if _spatial:
        linked = _spatial.links.get(step["id"], _spatial.document_key())
        if linked:
            highlighted, message = _spatial.highlight(step["id"])
            if not highlighted:
                _status(message, True)
        else:
            _spatial.clear_overlay()
        _post_links()
    if not success:
        _status("Open or create a Fusion Design to see the reference geometry.", True)
    elif announce:
        if step.get("geometry", {}).get("meshes"):
            _status("Reference geometry displayed beside your design.")
        else:
            _status("No per-step 3D snapshots in this example; the source CAD model and final preview are available.")
    _post("step", {"index": index})


def _load(filename):
    global _package
    new_package = open_package(filename)
    try:
        data = new_package.player_data()
    except Exception:
        new_package.close()
        raise
    _renderer.clear()
    if _spatial:
        _spatial.reset_example()
    old = _package
    _package = new_package
    if old:
        old.close()
    _post("example", data)
    _set_step(0, True)


def _open_dialog():
    dialog = _ui.createFileDialog()
    dialog.title = "Open exCADmple design example"
    dialog.filter = "exCADmple packages (*.excadmple;*.json)"
    if dialog.showOpen() == adsk.core.DialogResults.DialogOK:
        _load(dialog.filename)



def _selected_native_entity():
    selections = _ui.activeSelections
    for i in range(selections.count - 1, -1, -1):
        entity = selections.item(i).entity
        if (adsk.fusion.BRepFace.cast(entity) or adsk.fusion.BRepEdge.cast(entity)
                or adsk.fusion.BRepVertex.cast(entity)):
            return entity
    return None


def _selected_geometry_from_ui():
    class CurrentSelection:
        currentSelection = _ui.activeSelections
    return _selected_geometry(CurrentSelection())


def _selected_geometry(args):
    """Report the most recently selected native BRep face, edge or vertex."""
    selections = args.currentSelection
    for i in range(selections.count - 1, -1, -1):
        entity = selections.item(i).entity
        for kind, cls in (("Face", adsk.fusion.BRepFace),
                          ("Edge", adsk.fusion.BRepEdge),
                          ("Vertex", adsk.fusion.BRepVertex)):
            if cls.cast(entity):
                token = getattr(entity, "entityToken", "") or ""
                return {"kind": kind, "token": token,
                        "entity_id": token, "selected": True}
    return {"selected": False}


class ActiveGeometrySelection(adsk.core.ActiveSelectionEventHandler):
    def notify(self, args):
        try:
            selected = _selected_geometry(args)
            if _him and _him.busy:
                return
            _post("geometry_selection", selected)
            if selected["selected"]:
                _him_explain(_selected_native_entity())
            if selected["selected"]:
                design = adsk.fusion.Design.cast(_app.activeProduct)
                candidates = scan_candidate_features(design, _selected_native_entity())
                _post("native_history", {"features": candidates, "complete": False})
                _post("native_provenance", trace_feature_inputs(design, _selected_native_entity()))
            else:
                _post("native_history", {"features": [], "complete": False})
                _post("native_provenance", {"features": [], "complete": False})
        except Exception:
            _log_error()


class PaletteHandler(adsk.core.HTMLEventHandler):
    def notify(self, args):
        try:
            command = args.action
            body = json.loads(args.data or "{}")
            if command == "ready":
                if _package:
                    _post("example", _package.player_data())
                    _post("step", {"index": _step_index})
                    _post_links()
                _post("geometry_selection", _selected_geometry_from_ui())
                design = adsk.fusion.Design.cast(_app.activeProduct)
                _post("native_history", {"features": scan_candidate_features(design, _selected_native_entity()), "complete": False})
                _post("native_provenance", trace_direct_creators(design, _selected_native_entity()))
            elif command == "filter_history":
                if not _package:
                    raise ValueError("Load a model history example first")
                entity = body.get("entity_id")
                if not isinstance(entity, str) or not entity.strip():
                    raise ValueError("Choose an entity id from the example")
                features = _package.data.get("feature_history", [])
                if not features:
                    raise ValueError("This example does not contain feature provenance")
                indices = history_step_indices(features, _package.data["steps"], entity, body.get("expand", False))
                _post("history_filter", {"indices": indices, "entity_id": entity})
                _status(str(len(indices)) + " related history steps (authored provenance).")
            elif command == "load_demo":
                _load(str(ROOT / "examples" / "phone_stand.json"))
            elif command == "open_package":
                _open_dialog()
            elif command == "set_step":
                _set_step(int(body["index"]))
            elif command == "animation_frame":
                if _package:
                    step = _package.step(_step_index)
                    # Ignore stale asynchronous HTML frames after a step switch.
                    if step["id"] == body.get("step_id") and step.get("animation"):
                        value = body.get("progress")
                        if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 1:
                            raise ValueError("Animation progress must be in [0,1]")
                        _renderer.render_animation(step, _package.data.get("reference_offset_cm"), value)
            elif command == "animation_end":
                if _package and _package.step(_step_index)["id"] == body.get("step_id"):
                    _renderer.finish_animation()
            elif command == "link_selected":
                if not _package or not _spatial:
                    raise ValueError("Load an example before linking geometry")
                step = _package.step(_step_index)
                link = _spatial.bind_selected(step["id"])
                _, message = _spatial.highlight(step["id"])
                _post_links()
                _status("Linked " + link["label"] + " to this step. " + message)
            elif command == "locate_linked":
                if not _package or not _spatial:
                    raise ValueError("No active example")
                ok, message = _spatial.locate(_package.step(_step_index)["id"])
                _status(message, not ok)
            elif command == "unlink_step":
                if not _package or not _spatial:
                    raise ValueError("No active example")
                _spatial.unbind(_package.step(_step_index)["id"])
                _post_links()
                _status("Step link removed; source CAD geometry unchanged.")
            elif command == "set_focus":
                if not _spatial:
                    raise ValueError("Geometry focus is not ready")
                enabled = body.get("enabled", True)
                if not isinstance(enabled, bool):
                    raise ValueError("Focus setting must be boolean")
                ok, message = _spatial.set_focus_enabled(enabled)
                _status(message, not ok)
            elif command == "set_visible":
                visible = body.get("visible", True)
                _renderer.set_visible(visible)
            elif command == "clear_reference":
                _renderer.clear()
                _status("Reference geometry hidden. Your model is unchanged.")
            else:
                raise ValueError("Unknown action: " + str(command))
            args.returnData = json.dumps({"ok": True})
        except Exception as error:
            _status(str(error), True)
            args.returnData = json.dumps({"ok": False, "error": str(error)})
            _log_error()


class ShowCommandCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        handler = ShowCommandExecute()
        args.command.execute.add(handler)
        _handlers.append(handler)


class ShowCommandExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        if _palette:
            _palette.isVisible = True


class ShowHiMCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        handler = ShowHiMExecute()
        args.command.execute.add(handler)
        _handlers.append(handler)


class ShowHiMExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        if _him_palette:
            _him_palette.isVisible = True


class BeforeSave(adsk.core.DocumentEventHandler):
    def notify(self, args):
        global _saving_document
        try:
            # Never save a temporarily animated parameter or opacity.
            if _him:
                _him.stop()
            # Restore the exact user-authored opacities before Fusion serializes.
            if _spatial:
                _spatial.clear_overlay()
            if _renderer:
                _renderer.clear()
            _saving_document = True
        except Exception as error:
            _saving_document = False
            # A failed restoration must never be saved silently.
            try:
                args.isSaveCanceled = True
            except Exception:
                pass
            _status("Save canceled: could not restore original appearance. " + str(error), True)
            _log_error()


class BeforeDeactivate(adsk.core.DocumentEventHandler):
    def notify(self, args):
        try:
            if _him:
                _him.stop()
            if _spatial:
                _spatial.clear_overlay()
            if _renderer:
                _renderer.clear()
        except Exception as error:
            _status("Focus could not be cleared before changing documents: " + str(error), True)
            _log_error()


class AfterSave(adsk.core.DocumentEventHandler):
    def notify(self, args):
        global _saving_document
        if not _saving_document:
            return
        _saving_document = False
        if _package and _renderer:
            try:
                _set_step(_step_index)
            except Exception:
                _log_error()


def _log_error():
    if _app:
        try:
            _app.log("exCADmple: " + traceback.format_exc())
        except Exception:
            pass


def _start_him():
    global _him, _him_palette, _him_event, _him_ticker, _him_command_def, _him_command_control
    _him = HiMController(_app, _ui, _post_him, lambda message: _app.log("exCADmple HiM: " + message))
    _him_palette = _ui.palettes.itemById(HIM_PALETTE_ID)
    if not _him_palette:
        _him_palette = _ui.palettes.add2(
            HIM_PALETTE_ID, "History in Motion", str(ROOT / "ui" / "him.html"),
            True, True, True, 340, 760)
    _him_palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
    handler = HiMPaletteHandler()
    _him_palette.incomingFromHTML.add(handler)
    _handlers.append(handler)
    _him_palette.isVisible = True
    try:
        _app.unregisterCustomEvent(HIM_TICK_EVENT)
    except Exception:
        pass
    _him_event = _app.registerCustomEvent(HIM_TICK_EVENT)
    tick = HiMTickHandler()
    _him_event.add(tick)
    _handlers.append(tick)
    _him_ticker = _HiMTicker()
    _him_ticker.start()
    _him_command_def = _ui.commandDefinitions.itemById(HIM_COMMAND_ID)
    if not _him_command_def:
        _him_command_def = _ui.commandDefinitions.addButtonDefinition(
            HIM_COMMAND_ID, "History in Motion",
            "Explain how the selected face, edge or vertex was modeled")
    created = ShowHiMCreated()
    _him_command_def.commandCreated.add(created)
    _handlers.append(created)
    for panel_id in ("SolidScriptsAddinsPanel", "ToolsScriptsAddinsPanel"):
        panel = _ui.allToolbarPanels.itemById(panel_id)
        if panel:
            _him_command_control = panel.controls.itemById(HIM_COMMAND_ID) or panel.controls.addCommand(_him_command_def)
            break


def _stop_him():
    global _him, _him_palette, _him_ticker, _him_event
    if _him_ticker:
        _him_ticker.stopped.set()
        _him_ticker = None
    if _him:
        try:
            _him.stop()
        except Exception:
            _log_error()
        _him = None
    if _him_event:
        for handler in _handlers:
            if isinstance(handler, HiMTickHandler):
                try:
                    _him_event.remove(handler)
                except Exception:
                    pass
        try:
            _app.unregisterCustomEvent(HIM_TICK_EVENT)
        except Exception:
            pass
        _him_event = None
    if _him_palette and _him_palette.isValid:
        _him_palette.deleteMe()
    _him_palette = None
    for control in (_him_command_control, _him_command_def):
        try:
            if control and control.isValid:
                control.deleteMe()
        except Exception:
            pass


def run(_context):
    global _app, _ui, _palette, _renderer, _spatial, _command_def, _command_control
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        _renderer = ReferenceRenderer(_app)
        _spatial = SpatialLinkController(_app, _ui)

        _palette = _ui.palettes.itemById(PALETTE_ID)
        if not _palette:
            _palette = _ui.palettes.add2(
                PALETTE_ID, "exCADmple · HiM Explorer", str(ROOT / "ui" / "index.html"),
                True, True, True, 390, 800
            )
        _palette.isDockedInCanvas = False
        _palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateLeft
        handler = PaletteHandler()
        _palette.incomingFromHTML.add(handler)
        _handlers.append(handler)
        _palette.isVisible = True

        _command_def = _ui.commandDefinitions.itemById(COMMAND_ID)
        if not _command_def:
            _command_def = _ui.commandDefinitions.addButtonDefinition(
                COMMAND_ID, "exCADmple Player", "Open the explorable design example player"
            )
        created = ShowCommandCreated()
        _command_def.commandCreated.add(created)
        _handlers.append(created)
        for panel_id in ("SolidScriptsAddinsPanel", "ToolsScriptsAddinsPanel"):
            panel = _ui.allToolbarPanels.itemById(panel_id)
            if panel:
                _command_control = panel.controls.itemById(COMMAND_ID)
                if not _command_control:
                    _command_control = panel.controls.addCommand(_command_def)
                break

        before = BeforeSave()
        after = AfterSave()
        deactivating = BeforeDeactivate()
        _app.documentSaving.add(before)
        _app.documentSaved.add(after)
        _app.documentDeactivating.add(deactivating)
        _handlers.extend((before, after, deactivating))
        selection_handler = ActiveGeometrySelection()
        _ui.activeSelectionChanged.add(selection_handler)
        _handlers.append(selection_handler)
        _post("geometry_selection", _selected_geometry_from_ui())
        _start_him()

        # A deterministic, clearly labeled illustrative example.
        _load(str(ROOT / "examples" / "phone_stand.json"))
    except Exception:
        _log_error()
        if _ui:
            _ui.messageBox("Could not start exCADmple:\n" + traceback.format_exc())


def stop(_context):
    global _palette, _renderer, _package, _command_control, _command_def
    try:
        _stop_him()
        if _renderer:
            _renderer.clear()
        if _spatial:
            _spatial.clear_overlay()
        if _ui:
            for handler in _handlers:
                if isinstance(handler, ActiveGeometrySelection):
                    try:
                        _ui.activeSelectionChanged.remove(handler)
                    except Exception:
                        pass
        if _app:
            for event_name, handler_type in (("documentSaving", BeforeSave), ("documentSaved", AfterSave), ("documentDeactivating", BeforeDeactivate)):
                for handler in _handlers:
                    if isinstance(handler, handler_type):
                        try:
                            getattr(_app, event_name).remove(handler)
                        except Exception:
                            pass
        if _package:
            _package.close()
            _package = None
        if _palette and _palette.isValid:
            _palette.deleteMe()
        _palette = None
        if _command_control and _command_control.isValid:
            _command_control.deleteMe()
        if _command_def and _command_def.isValid:
            _command_def.deleteMe()
        _handlers.clear()
    except Exception:
        _log_error()
