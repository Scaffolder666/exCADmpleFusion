"""exCADmple MVP: design-process player in Autodesk Fusion.

Start by running this Add-In from Utilities > Scripts and Add-Ins.
Only Custom Graphics are changed; no native feature history is replayed.
"""
import json
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
from core.fusion_history import scan_candidate_features, trace_direct_creators
from core.spatial import SpatialLinkController

PALETTE_ID = "excadmple.fusion.player"
COMMAND_ID = "excadmple.fusion.open"
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
            _post("geometry_selection", selected)
            if selected["selected"]:
                design = adsk.fusion.Design.cast(_app.activeProduct)
                candidates = scan_candidate_features(design, _selected_native_entity())
                _post("native_history", {"features": candidates, "complete": False})
                _post("native_provenance", trace_direct_creators(design, _selected_native_entity()))
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


class BeforeSave(adsk.core.DocumentEventHandler):
    def notify(self, args):
        global _saving_document
        try:
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

        # A deterministic, clearly labeled illustrative example.
        _load(str(ROOT / "examples" / "phone_stand.json"))
    except Exception:
        _log_error()
        if _ui:
            _ui.messageBox("Could not start exCADmple:\n" + traceback.format_exc())


def stop(_context):
    global _palette, _renderer, _package, _command_control, _command_def
    try:
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
