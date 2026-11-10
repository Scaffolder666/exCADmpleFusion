"""exCADmple: play a recorded design tutorial inside Autodesk Fusion.

A tutorial is what was recorded while a designer modeled: the steps, the
3D model as it evolved, the tools used, the pointer, and what the designer
said (think-aloud). The player plays the whole tutorial or one step at a
time, with the recorded voice (or synthetic speech) and the transcript.

Two layouts with the same features (config.json "layout"):
* "overlay"   — version B: the reference model is drawn in the user's own
  canvas (Custom Graphics) and the tutorial floats over it;
* "reference" — version A, as in History in Motion: a copy of the
  designer's .f3d is opened as a separate (never saved) document with its
  own Timeline and played by animating feature parameters; it is drawn in
  the user's own viewport, beside the user's model, which stays the
  active, editable design.
"""
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))
# Fusion keeps imported modules across Stop/Run of an add-in, so after an
# update the new entry file would run against the old ``core`` modules
# (e.g. "render() takes from 2 to 3 positional arguments"). Always import
# this add-in's current ``core`` package from ROOT.
for _name in [n for n in sys.modules if n == "core" or n.startswith("core.")]:
    del sys.modules[_name]

import adsk.core
import adsk.fusion

from core.tutorial.packages import open_package, PackageError
from core.renderer import ReferenceRenderer, active_fusion_command
from core.spatial import SpatialLinkController
from core.tutorial.extract_fusion import extract_with_dialog
from core.playback.him_reference import ReferenceSession
from core.session_recorder import SessionRecorder
from core.playback.tool_guide import ToolGuide
from core.diagnostics import DiagnosticLog

# Shown in the panel at start so it is clear which code Fusion is running.
BUILD = "same-viewport 2026-11-10 · one context look v15"
PALETTE_ID = "excadmple_fusion_player"
TOOL_PALETTE_ID = "excadmple_tool_window"   # version A: "tool in use" window at the left
COMMAND_ID = "excadmple_fusion_open"
RECORD_COMMAND_ID = "excadmple_fusion_record"


def _read_layout():
    try:
        value = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("layout", "overlay")
    except Exception:
        value = "overlay"
    return value if value in ("overlay", "reference") else "overlay"


LAYOUT = _read_layout()
REFERENCE = "reference"
ROLE = "overlay"            # overlay (version B) | reference (version A, decided in run)

_app = None
_ui = None
_palette = None
_tool_palette = None
_tool_payload = {"step": "", "tools": []}
_renderer = None
_spatial = None
_package = None
_step_index = 0
_session = None
_tools = None                # version A: the step's native Fusion tools in the toolbar
_diag = None                 # logs/latest.log: what happened in this run, to send for diagnosis
_last_shown = None           # version A: what the last frame showed (parameter / visual)
_filtering = False
_saving_document = False
_handlers = []
_buttons = []
_recorder = None


# --- helpers ---------------------------------------------------------------------------
def _post(action, payload):
    if _palette and _palette.isValid:
        _palette.sendInfoToHTML(action, json.dumps(payload))


def _post_tool(action, payload):
    if _tool_palette and _tool_palette.isValid:
        _tool_palette.sendInfoToHTML(action, json.dumps(payload))


def _status(message, is_error=False):
    if is_error:
        _note("status", "error shown to the user: " + str(message))
    _post("status", {"message": message, "error": is_error})


def _note(category, message, data=None):
    """Write to logs/latest.log (never raises)."""
    if _diag:
        try:
            _diag.write(category, message, data)
        except Exception:
            pass


def _session_log(message):
    """The reference session's messages: Text Commands and the log file."""
    try:
        _app.log("exCADmple reference: " + message)
    except Exception:
        pass
    _note("playback", message)


def _log_error():
    if _diag:
        try:
            _diag.exception()
        except Exception:
            pass
    if _app:
        try:
            _app.log("exCADmple: " + traceback.format_exc())
        except Exception:
            pass


def _post_links():
    if _package and _spatial:
        _post("links", {"by_step": _spatial.display_links(_package.data["steps"])})


def _post_source():
    if ROLE == REFERENCE and _session:
        _post("source", {"live": _session.live, "file": _session.source_name,
                         "unmatched": _session.unmatched, "plan": _session.plan})
        timeline = []
        try:
            if _session.live:
                timeline = [[f.index, f.name, f.kind] for f in _session.model.features()]
        except Exception:
            pass
        _note("tutorial", "loaded" if _session.live else "no live reference model", {
            "title": _package.data.get("title") if _package else None,
            "source": str(getattr(_package, "source_path", "")) if _package else None,
            "model": _session.source_name, "steps": len(_package.data["steps"]) if _package else 0,
            "timeline": timeline, "unmatched": _session.unmatched, "plan": _session.plan})


# --- the tutorial ----------------------------------------------------------------------------
def _show_hud(index, progress):
    """Version B: step title and what the designer is saying, pinned to the
    corner of the Fusion canvas with Custom Graphics."""
    if ROLE != "overlay" or not _package or not _renderer:
        return
    step = _package.step(index)
    elapsed = progress * step.get("duration_ms", 8000)
    said = ""
    for cue in step.get("cues", []):
        if cue["at_ms"] <= elapsed:
            said = cue["label"]
    lines = ["exCADmple  ·  Step %d / %d  ·  %s" % (index + 1, len(_package.data["steps"]), step["title"])]
    if said:
        lines.append("“" + (said if len(said) <= 120 else said[:117].rstrip() + "…") + "”")
    try:
        _renderer.render_hud(lines)
    except Exception:
        _log_error()      # the HUD is an aid; never block playback


def _previous_geometry(index):
    """The snapshot before step ``index`` (spatial guidance compares with it)."""
    if not _package or index <= 0:
        return []
    return _package.step(index - 1).get("geometry", {}).get("meshes", [])


def _set_step(index, preview=True, fill_tools=True):
    global _step_index
    if not _package:
        return
    if not isinstance(index, int) or index < 0 or index >= len(_package.data["steps"]):
        raise PackageError("Step out of range")
    _step_index = index
    step = _package.step(index)
    if ROLE == REFERENCE:
        if _session and _session.live:
            # Merely selecting/loading a step is not an animation command.
            # Show the COMPLETE shaded model until Play requests the first
            # native Feature frame. The user can inspect the overall design.
            if preview:
                _session.show_overview()
            else:
                # Continuous playback: clear the prior Feature's temporary
                # parameters and ghost, but do not show a full-model flash.
                _session.stop(restore_timeline=False)
        else:
            _renderer.render(step, [0, 0, 0], _previous_geometry(index))    # recorded geometry only
        # A step selection shows the geometry; the command label appears only
        # when its animation actually starts, not ahead of the operation.
        _renderer.clear_pointer()
        _renderer.clear_command()
    else:
        if not _renderer.render(step, _package.data.get("reference_offset_cm"), _previous_geometry(index)):
            _status("Open or create a Fusion Design to see the reference model.", True)
        _show_hud(index, 0.0)
    if _spatial:
        if _spatial.links.get(step["id"], _spatial.document_key()):
            highlighted, message = _spatial.highlight(step["id"])
            if not highlighted:
                _status(message, True)
        else:
            _spatial.clear_overlay()
        _post_links()
    _update_tools(index, fill=fill_tools)
    _post("step", {"index": index})


def _update_tools(index, fill=True):
    """Show the step's Fusion tools: native buttons in the exCADmple toolbar
    panel, and their menu path in the tutorial panel. ``fill=False`` (a
    tutorial was just loaded) keeps the panel empty."""
    if not _tools or not _package:
        return
    try:
        # The panel starts empty and collects the tools used up to this step.
        _tools.load((str(getattr(_package, "source_path", "")), _package.data.get("id"), _package.data.get("title")))
        labels = _package.step(index).get("tools", [])
        if fill:
            used = [t for step in _package.data["steps"][:index] for t in step.get("tools", [])]
            report = _tools.show(labels, used)
        else:
            _tools.show([], [])
            report = _tools.describe(labels)
    except Exception as error:
        # Tool guidance must never block playback, but a failure is shown.
        report = [{"label": "", "path": [], "found": False, "error": "{}: {}".format(type(error).__name__, error)}]
        _log_error()
    _post("tools", {"index": index, "tools": report, "panel_error": _tools.last_error})
    _note("tools", "step {}".format(index + 1), {"tools": [
        {k: t.get(k) for k in ("label", "path", "found", "error")} for t in report],
        "panel_error": _tools.last_error, "pinned": fill})
    global _tool_payload
    step = _package.step(index)
    _tool_payload = {"step": "Step {} · {}".format(index + 1, step.get("title", "")),
                     "tools": [t for t in report if t.get("label")] if fill else []}
    _post_tool("tool", _tool_payload)


def _open_reference_session():
    """Version A: open a copy of the tutorial's .f3d in this (reference) instance."""
    if ROLE != REFERENCE or not _session or not _package:
        return
    try:
        live = _session.open(_package)
    except Exception as error:
        live = False
        _status("Could not open the designer's model: " + str(error), True)
        _log_error()
    if not live and not adsk.fusion.Design.cast(_app.activeProduct):
        _app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    _post_source()


def _load(filename):
    """Open a tutorial (replacing the current one)."""
    _note("tutorial", "open " + str(filename))
    global _package
    package = open_package(filename)
    if getattr(package, "needs_populate", False):
        if ROLE != REFERENCE or not _session:
            package.close()
            raise PackageError("JSON + .f3d pairs require the History in Motion layout")
        # Native feature names and indices do not exist in the sidecar until
        # Fusion imports the original .f3d and reads its real Timeline.
        try:
            _session.open(package)
            data = package.player_data()
        except Exception:
            package.close()
            _post_source()       # the previous reference copy is closed now
            raise
        _renderer.clear()
        if _spatial:
            _spatial.reset_example()
        old, _package = _package, package
        if old:
            old.close()
        _post("example", data)
        _post_source()
        _set_step(0, fill_tools=False)     # the tool panel starts empty
        if package.generated_path:
            _status("Editable steps saved to " + str(package.generated_path))
        if _palette and _palette.isValid:
            _palette.isVisible = True
        return
    try:
        data = package.player_data()
    except Exception:
        package.close()
        raise
    _renderer.clear()
    if _spatial:
        _spatial.reset_example()
    old, _package = _package, package
    if old:
        old.close()
    _post("example", data)
    _open_reference_session()
    _set_step(0, fill_tools=False)         # the tool panel starts empty
    if _palette and _palette.isValid:
        _palette.isVisible = True


def _open_dialog():
    dialog = _ui.createFileDialog()
    dialog.title = "Load Example (JSON + matching Fusion .f3d, or .excadmple)"
    dialog.filter = "exCADmple tutorials (*.excadmple;*.json)"
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


class ActiveGeometrySelection(adsk.core.ActiveSelectionEventHandler):
    """Version A: selecting the reference model plays the steps that made it (HiM)."""

    def notify(self, args):
        global _filtering
        if ROLE != REFERENCE or _filtering or not (_session and _session.live):
            return
        try:
            entity = _selected_native_entity()
            if entity is None:
                return
            _filtering = True
            try:
                result = _session.filter(entity)
            finally:
                _filtering = False
            if result:
                _post("filter", result)
        except Exception:
            _log_error()


class PaletteHandler(adsk.core.HTMLEventHandler):
    def notify(self, args):
        global _step_index, _filtering, _last_shown
        try:
            command = args.action
            if command == "response":
                # Fusion echoes the panel's reply to sendInfoToHTML back as a
                # "response" event. It is an acknowledgement, not a request.
                return
            if command == "client_log":
                _note("panel", str(json.loads(args.data or "{}").get("message", ""))[:4000])
                args.returnData = json.dumps({"ok": True})
                return
            body = json.loads(args.data or "{}")
            if command == "ready":
                if _package:
                    _post("example", _package.player_data())
                    _post_source()
                    _post("step", {"index": _step_index})
                    _post_links()
            elif command == "load_demo":
                _load(str(ROOT / "examples" / "phone_stand.json"))
            elif command == "open_package":
                _open_dialog()
            elif command == "extract_draft":
                _status(extract_with_dialog(_app, _ui))
            elif command == "set_step":
                _set_step(int(body["index"]), preview=body.get("preview", True) is not False)
            elif command == "animation_frame":
                # Version B: one frame of the recorded geometry in the user's canvas.
                if _package:
                    step = _package.step(_step_index)
                    if step["id"] == body.get("step_id"):      # ignore stale frames
                        value = body.get("progress")
                        if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 1:
                            raise ValueError("Animation progress must be in [0,1]")
                        offset = _package.data.get("reference_offset_cm")
                        if step.get("animation"):
                            _renderer.render_animation(step, offset, value, _previous_geometry(_step_index))
                        if step.get("pointer"):
                            _renderer.render_pointer(step, offset, value)
                        _show_hud(_step_index, value)
            elif command == "animation_end":
                if _package and _package.step(_step_index)["id"] == body.get("step_id"):
                    _renderer.finish_animation()
                    _renderer.clear_pointer()
            elif command == "ref_frame":
                # Version A: one HiM frame on the designer's model. The panel
                # asks for the next frame only when this one is computed.
                index, value = body.get("index"), body.get("progress")
                if (_package and isinstance(index, int) and 0 <= index < len(_package.data["steps"])
                        and isinstance(value, (int, float)) and not isinstance(value, bool)):
                    _step_index = index
                    value = max(0.0, min(1.0, float(value)))
                    step = _package.step(index)
                    shown = None
                    if _session and _session.live:
                        if isinstance(body.get("auto_focus"), bool):
                            _session.set_auto_focus(body["auto_focus"])
                        shown = _session.frame(index, value, settle=body.get("settle") is True)
                        if shown and shown != _last_shown:
                            _last_shown = shown
                            _post("animation", shown)
                            _note("frame", "step {} at {:.0%}".format(index + 1, value), shown)
                            if shown.get("kind"):
                                _post_tool("active", {"label": active_fusion_command(step, shown.get("kind")) or ""})
                        if shown is None:
                            raise RuntimeError("The reference model is not open any more; load the tutorial again"
                                               if _session.presenter.attached else
                                               "Activate the reference document to continue playback")
                        if shown.get("mode") == "error":
                            raise RuntimeError(shown.get("fallback") or "Native frame failed")
                    elif step.get("animation"):
                        _renderer.render_animation(step, [0, 0, 0], value, _previous_geometry(index))
                    # Show exactly the operation being animated; tutorial tool
                    # lists have no individual activation timestamps.
                    if value < 1.0 and ((shown and shown.get("mode") in ("parameter", "visual", "instant", "timeline"))
                                        or (not (_session and _session.live) and step.get("animation"))):
                        _renderer.render_command(step, (shown or {}).get("kind"))
                    else:
                        _renderer.clear_command()
                    # The precise target arrow replaces the unrecorded ghost
                    # mouse path in reference playback.
            elif command == "ref_auto_focus":
                enabled = body.get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError("Auto-focus setting must be boolean")
                if _session:
                    _session.set_auto_focus(enabled)
            elif command == "ref_overview":
                # A filtered / partial tutorial still ends with a full
                # model, even when its last example step is not the final
                # source Timeline feature.
                if _session and _session.live:
                    _session.show_overview()
                _renderer.clear_command()
                _renderer.clear_pointer()
            elif command == "show_more":
                if _session:
                    _filtering = True
                    try:
                        result = _session.show_more()
                    finally:
                        _filtering = False
                    if result:
                        _post("filter", result)
            elif command == "clear_filter":
                _ui.activeSelections.clear()
            elif command == "fit_view":
                _app.activeViewport.fit()
            elif command == "use_tool":
                if not _tools:
                    raise ValueError("Tool guidance is not available in this layout")
                path = _tools.use(body.get("label"))
                _status("Started " + path + " in your design")
            elif command == "him_dim":
                if _session:
                    _session.set_dim(bool(body.get("enabled", True)))
            elif command == "link_selected":
                if not _package or not _spatial:
                    raise ValueError("Open a tutorial before linking geometry")
                step = _package.step(_step_index)
                link = _spatial.bind_selected(step["id"])
                _, message = _spatial.highlight(step["id"])
                _post_links()
                _status("Linked " + link["label"] + " to this step. " + message)
            elif command == "locate_linked":
                ok, message = _spatial.locate(_package.step(_step_index)["id"])
                _status(message, not ok)
            elif command == "unlink_step":
                _spatial.unbind(_package.step(_step_index)["id"])
                _post_links()
                _status("Step link removed; your geometry is unchanged.")
            elif command == "set_focus":
                enabled = body.get("enabled", True)
                if not isinstance(enabled, bool):
                    raise ValueError("Focus setting must be boolean")
                ok, message = _spatial.set_focus_enabled(enabled)
                _status(message, not ok)
            elif command == "set_visible":
                _renderer.set_visible(body.get("visible", True))
            else:
                raise ValueError("Unknown action: " + str(command))
            args.returnData = json.dumps({"ok": True})
        except Exception as error:
            _status(str(error), True)
            args.returnData = json.dumps({"ok": False, "error": str(error)})
            _log_error()


class RecordExecute(adsk.core.CommandEventHandler):
    """Authoring: log tools, features and selections while the designer
    records a tutorial (start it together with the screen recording)."""

    def notify(self, args):
        try:
            message = _recorder.stop() if _recorder.recording else _recorder.start()
            definition = _ui.commandDefinitions.itemById(RECORD_COMMAND_ID)
            if definition:
                definition.name = "exCADmple: Stop recording" if _recorder.recording else "exCADmple: Record tutorial"
            _ui.messageBox(message, "exCADmple")
        except Exception as error:
            _ui.messageBox(str(error), "exCADmple")
            _log_error()


class ShowPaletteExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        if _palette:
            _palette.isVisible = True


class CommandCreated(adsk.core.CommandCreatedEventHandler):
    def __init__(self, execute_type):
        super().__init__()
        self.execute_type = execute_type

    def notify(self, args):
        handler = self.execute_type()
        args.command.execute.add(handler)
        _handlers.append(handler)


def _add_button(command_id, name, tooltip, execute_type):
    definition = _ui.commandDefinitions.itemById(command_id)
    if not definition:
        definition = _ui.commandDefinitions.addButtonDefinition(command_id, name, tooltip)
    created = CommandCreated(execute_type)
    definition.commandCreated.add(created)
    _handlers.append(created)
    _buttons.append(definition)
    for panel_id in ("SolidScriptsAddinsPanel", "ToolsScriptsAddinsPanel"):
        panel = _ui.allToolbarPanels.itemById(panel_id)
        if panel:
            _buttons.append(panel.controls.itemById(command_id) or panel.controls.addCommand(definition))
            break


def _panel_url(folder):
    """The panel page, with a version taken from its files' modification
    times: Fusion's browser otherwise keeps running a cached old player.js
    after the add-in is updated."""
    base = ROOT / "ui" / folder
    try:
        stamp = int(max(p.stat().st_mtime for p in base.iterdir() if p.is_file()))
    except (OSError, ValueError):
        stamp = 0
    return (base / "index.html").resolve().as_uri() + "?v={}".format(stamp)


def _create_palette():
    global _palette
    _palette = _ui.palettes.itemById(PALETTE_ID)
    if _palette:
        _palette.deleteMe()          # the layout may have changed
    if ROLE == REFERENCE:
        # Version A: HiM control panel beside the reference instance's canvas.
        _palette = _ui.palettes.add2(PALETTE_ID, "exCADmple ", _panel_url("reference"),
                                     True, True, True, 340, 740)
        _palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
    else:
        # Version B: a compact tutorial floating over the Fusion canvas.
        _palette = _ui.palettes.add2(PALETTE_ID, "exCADmple · Tutorial", _panel_url("overlay"),
                                     True, True, True, 340, 640)
        _palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
        try:
            _palette.setPosition(80, 160)   # over the left part of the canvas
        except Exception:
            pass
    handler = PaletteHandler()
    _palette.incomingFromHTML.add(handler)
    _handlers.append(handler)
    _palette.isVisible = True


class ToolPaletteHandler(adsk.core.HTMLEventHandler):
    """The left "tool in use" window: shows the step's tool, starts it."""

    def notify(self, args):
        try:
            command = args.action
            if command == "response":
                return                        # Fusion's acknowledgement of sendInfoToHTML
            body = json.loads(args.data or "{}")
            if command == "ready":
                _post_tool("tool", _tool_payload)
            elif command == "client_log":
                _note("tool window", str(body.get("message", ""))[:4000])
            elif command == "use_tool":
                if not _tools:
                    raise ValueError("Tool guidance is not available in this layout")
                path = _tools.use(body.get("label"))
                _post("pause", {})            # stop the tutorial while the user models
                _status("Started " + path + " in your design")
            args.returnData = json.dumps({"ok": True})
        except Exception as error:
            _status(str(error), True)
            args.returnData = json.dumps({"ok": False, "error": str(error)})
            _log_error()


def _create_tool_palette():
    """A small window docked at the left of the canvas: the tool in use."""
    global _tool_palette
    old = _ui.palettes.itemById(TOOL_PALETTE_ID)
    if old:
        old.deleteMe()
    _tool_palette = _ui.palettes.add2(TOOL_PALETTE_ID, "exCADmple · Tool", _panel_url("tool"),
                                      True, True, True, 260, 300)
    try:
        _tool_palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateLeft
    except Exception:
        pass
    handler = ToolPaletteHandler()
    _tool_palette.incomingFromHTML.add(handler)
    _handlers.append(handler)
    _tool_palette.isVisible = True


# --- document safety ----------------------------------------------------------------------------
class BeforeSave(adsk.core.DocumentEventHandler):
    def notify(self, args):
        global _saving_document
        try:
            if _session:
                _session.stop()           # never save an animated parameter
                _session.hide()           # no reference graphics in the user's saved design
            if _spatial:
                _spatial.clear_overlay()  # restore the user's opacities
            if _renderer:
                _renderer.clear()
            _saving_document = True
        except Exception as error:
            _saving_document = False
            try:
                args.isSaveCanceled = True    # never save a failed restore silently
            except Exception:
                pass
            _status("Save canceled: could not restore the original appearance. " + str(error), True)
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


class BeforeDeactivate(adsk.core.DocumentEventHandler):
    def notify(self, args):
        try:
            if _session and _session.live:
                _session.stop()
            if _spatial:
                _spatial.clear_overlay()
            if _renderer and ROLE != REFERENCE:
                _renderer.clear()
        except Exception as error:
            _status("Could not clear the display before changing documents: " + str(error), True)
            _log_error()


# --- add-in lifecycle ---------------------------------------------------------------------------
def run(_context):
    global _app, _ui, _renderer, _spatial, _recorder, _diag
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        _diag = DiagnosticLog(ROOT / "logs", BUILD)
        try:
            fusion_version = _app.version
        except Exception:
            fusion_version = "unknown"
        _diag.header(fusion=fusion_version, layout=LAYOUT, folder=str(ROOT))
        _renderer = ReferenceRenderer(_app)
        _spatial = SpatialLinkController(_app, _ui)
        if LAYOUT == "reference":
            # HiM-first: display history beside the native Fusion canvas.
            # A second Fusion process is not needed for example playback.
            global ROLE, _session
            ROLE = REFERENCE
            _session = ReferenceSession(_app, _ui, _session_log)
            global _tools
            _tools = ToolGuide(_ui, lambda message: (_app.log(message), _note("tools", message)))

        for event, handler in ((_app.documentSaving, BeforeSave()), (_app.documentSaved, AfterSave()),
                               (_app.documentDeactivating, BeforeDeactivate())):
            event.add(handler)
            _handlers.append(handler)

        if ROLE != REFERENCE:
            # Authoring: record a tutorial while modeling in this window.
            _recorder = SessionRecorder(_app, _ui)
            _add_button(RECORD_COMMAND_ID, "exCADmple: Record tutorial",
                        "Log the tools, features and selections while you record a tutorial", RecordExecute)

        _create_palette()
        if ROLE == REFERENCE:
            try:
                _create_tool_palette()
            except Exception:
                _log_error()          # the tool window is an aid; never block the tutorial
        _add_button(COMMAND_ID, "exCADmple Tutorial", "Show the tutorial player", ShowPaletteExecute)
        if ROLE == REFERENCE:
            selection = ActiveGeometrySelection()
            _ui.activeSelectionChanged.add(selection)
            _handlers.append(selection)
        _load(str(ROOT / "examples" / "phone_stand.json"))     # illustrative sample tutorial
        _status("exCADmple " + BUILD)
    except Exception:
        _log_error()
        if _ui:
            _ui.messageBox("Could not start exCADmple:\n" + traceback.format_exc())


def stop(_context):
    global _palette, _package, _session
    try:
        if _recorder:
            _recorder.cancel()
        if _session:
            _session.close()
            _session = None
        if _tools:
            _tools.close()
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
            for event_name, handler_type in (("documentSaving", BeforeSave), ("documentSaved", AfterSave),
                                             ("documentDeactivating", BeforeDeactivate)):
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
        if _tool_palette and _tool_palette.isValid:
            _tool_palette.deleteMe()
        for item in reversed(_buttons):
            try:
                if item and item.isValid:
                    item.deleteMe()
            except Exception:
                pass
        _buttons.clear()
        _handlers.clear()
    except Exception:
        _log_error()

