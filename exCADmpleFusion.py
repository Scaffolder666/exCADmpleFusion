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
from core.spatial import SpatialLinkController
from core.him_fusion import HiMController
from core.library import ExampleLibrary
from core.reuse_fusion import ReuseController
from core.extract_fusion import extract_with_dialog

PALETTE_ID = "excadmple.fusion.player"


def _read_layout():
    """'overlay' (version B: tutorial over the Fusion canvas, reference model
    in the canvas) or 'reference' (version A: History in Motion style, the
    example plays in a separate interactive 3D viewport). Set in config.json."""
    try:
        value = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("layout", "overlay")
    except Exception:
        value = "overlay"
    return value if value in ("overlay", "reference") else "overlay"


LAYOUT = _read_layout()
COMMAND_ID = "excadmple.fusion.open"
HIM_PALETTE_ID = "excadmple.fusion.reuse"
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
_package = None          # active example (kept in sync with _library)
_step_index = 0
_library = ExampleLibrary()
_reuse = None
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
        _him_status("Analysing how this geometry was modeled…")
        if _reuse:
            _reuse.explain(entity)
        else:
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
                if _reuse:
                    _reuse.publish()
                if not (_him and _him.result):
                    entity = _selected_native_entity()
                    if entity:
                        _him_explain(entity)
            elif command == "reuse_watch":
                _reuse.watch(str(body.get("example_id")), str(body.get("step_id")))
            elif command == "reuse_import":
                _open_dialog()
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
    _library.remember_step(index)
    step = _package.step(index)
    if LAYOUT == "reference":
        success = True        # the example plays in its own viewport, not in the canvas
    else:
        success = _renderer.render(step, _package.data.get("reference_offset_cm"))
        _show_hud(index, 0.0)
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


def _show_hud(index, progress):
    """Version B: step title, current caption and the Why, pinned to the
    corner of the Fusion canvas with Custom Graphics."""
    if LAYOUT != "overlay" or not _package or not _renderer:
        return
    step = _package.step(index)
    elapsed = progress * step.get("duration_ms", 8000)
    cue = ""
    for item in step.get("cues", []):
        if item["at_ms"] <= elapsed:
            cue = item["label"]
    lines = ["exCADmple  ·  Step %d / %d  ·  %s" % (index + 1, len(_package.data["steps"]), step["title"])]
    why = (step.get("reasoning") or {}).get("text", "")
    if why:
        lines.append("Why: " + (why if len(why) <= 110 else why[:107].rstrip() + "…"))
    if cue:
        lines.append("“" + cue + "”")
    try:
        _renderer.render_hud(lines)
    except Exception:
        _log_error()      # the HUD is an aid; never block playback


def _post_reference_geometry():
    if LAYOUT == "reference" and _package:
        _post("reference_geometry", _package.reference_geometry())


def _post_library():
    _post("library", {"examples": _library.listing()})
    if _reuse:
        _reuse.publish()


def _activate(example_id, step_index=None, play=False):
    """Make an open example the active one, keeping its own step position."""
    global _package
    if _package and _library.active_id:
        _library.remember_step(_step_index)
    _library.activate(example_id)
    _renderer.clear()
    if _spatial:
        _spatial.reset_example()
    _package = _library.package()
    _post("example", _package.player_data())
    _post_reference_geometry()
    index = _library.step_index() if step_index is None else int(step_index)
    _set_step(index, True)
    if play:
        _post("step", {"index": index, "play": True})
    _post_library()
    if _palette and _palette.isValid:
        _palette.isVisible = True


def _load(filename):
    """Open an example package and add it to the library of open examples."""
    new_package = open_package(filename)
    try:
        new_package.player_data()
    except Exception:
        new_package.close()
        raise
    if _package and _library.active_id:
        _library.remember_step(_step_index)
    example_id = _library.add(new_package)
    _activate(example_id, 0)


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
                    _post_reference_geometry()
                    _post("step", {"index": _step_index})
                    _post_links()
                _post_library()
                _post("geometry_selection", _selected_geometry_from_ui())
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
            elif command == "switch_example":
                _activate(str(body.get("id")))
            elif command == "close_example":
                example_id = str(body.get("id"))
                if len(_library) <= 1:
                    raise ValueError("Keep at least one example open")
                was_active = example_id == _library.active_id
                _library.remove(example_id)
                if was_active:
                    _activate(_library.active_id)
                else:
                    _post_library()
            elif command == "compare_decision":
                if _him_palette and _him_palette.isValid:
                    _him_palette.isVisible = True
                step = _package.step(_step_index)
                if _reuse:
                    _reuse.publish({"focus": {"example_id": _library.active_id, "step_id": step["id"],
                                              "topic": (step.get("decision") or {}).get("topic")}})
            elif command == "extract_draft":
                _status(extract_with_dialog(_app, _ui))
            elif command == "open_package":
                _open_dialog()
            elif command == "set_step":
                _set_step(int(body["index"]))
            elif command == "animation_frame":
                if _package:
                    step = _package.step(_step_index)
                    # Ignore stale asynchronous HTML frames after a step switch.
                    if step["id"] == body.get("step_id") and (step.get("animation") or step.get("pointer")):
                        value = body.get("progress")
                        if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 1:
                            raise ValueError("Animation progress must be in [0,1]")
                        offset = _package.data.get("reference_offset_cm")
                        if step.get("animation"):
                            _renderer.render_animation(step, offset, value)
                        if step.get("pointer"):
                            _renderer.render_pointer(step, offset, value)
                        _show_hud(_step_index, value)
            elif command == "animation_end":
                if _package and _package.step(_step_index)["id"] == body.get("step_id"):
                    _renderer.finish_animation()
                    _renderer.clear_pointer()
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


class AfterActivate(adsk.core.DocumentEventHandler):
    def notify(self, args):
        try:
            if _reuse:
                _reuse.document_changed()
        except Exception:
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
    global _reuse
    _him = HiMController(_app, _ui, _post_him, lambda message: _app.log("exCADmple HiM: " + message))
    _reuse = ReuseController(_app, _ui, _him, _library, _post_him,
                             lambda example_id, index: _activate(example_id, index, play=True))
    _him_palette = _ui.palettes.itemById(HIM_PALETTE_ID)
    if not _him_palette:
        _him_palette = _ui.palettes.add2(
            HIM_PALETTE_ID, "exCADmple · Reasoning Reuse", str(ROOT / "ui" / "him.html"),
            True, True, True, 380, 800)
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
            HIM_COMMAND_ID, "Reasoning Reuse",
            "Find example design reasoning for the selected face, edge or vertex of your model")
    created = ShowHiMCreated()
    _him_command_def.commandCreated.add(created)
    _handlers.append(created)
    for panel_id in ("SolidScriptsAddinsPanel", "ToolsScriptsAddinsPanel"):
        panel = _ui.allToolbarPanels.itemById(panel_id)
        if panel:
            _him_command_control = panel.controls.itemById(HIM_COMMAND_ID) or panel.controls.addCommand(_him_command_def)
            break


def _stop_him():
    global _him, _him_palette, _him_ticker, _him_event, _reuse
    _reuse = None
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
        if _palette:
            _palette.deleteMe()          # the layout may have changed
        if LAYOUT == "reference":
            # Version A: a separate window with the interactive reference viewport.
            _palette = _ui.palettes.add2(
                PALETTE_ID, "exCADmple · Reference example", str(ROOT / "ui" / "reference.html"),
                True, True, True, 1180, 760)
        else:
            # Version B: a compact tutorial floating over the Fusion canvas.
            _palette = _ui.palettes.add2(
                PALETTE_ID, "exCADmple · Tutorial", str(ROOT / "ui" / "index.html"),
                True, True, True, 340, 640)
        _palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
        try:
            if LAYOUT == "reference":
                _palette.setPosition(60, 80)
            else:
                _palette.setPosition(80, 160)   # over the left part of the canvas
        except Exception:
            pass
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
        activated = AfterActivate()
        _app.documentActivated.add(activated)
        _handlers.extend((before, after, deactivating, activated))
        selection_handler = ActiveGeometrySelection()
        _ui.activeSelectionChanged.add(selection_handler)
        _handlers.append(selection_handler)
        _post("geometry_selection", _selected_geometry_from_ui())
        _start_him()

        # Deterministic, clearly labeled illustrative examples.
        _load(str(ROOT / "examples" / "tablet_stand.json"))
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
            for event_name, handler_type in (("documentSaving", BeforeSave), ("documentSaved", AfterSave), ("documentDeactivating", BeforeDeactivate), ("documentActivated", AfterActivate)):
                for handler in _handlers:
                    if isinstance(handler, handler_type):
                        try:
                            getattr(_app, event_name).remove(handler)
                        except Exception:
                            pass
        _library.close()
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
