"""exCADmple MVP: design-process player in Autodesk Fusion.

Start by running this Add-In from Utilities > Scripts and Add-Ins.
Only Custom Graphics are changed; no native feature history is replayed.
"""
import json
import traceback
from pathlib import Path

import adsk.core
import adsk.fusion

from core.packages import open_package, PackageError
from core.renderer import ReferenceRenderer

ROOT = Path(__file__).resolve().parent
PALETTE_ID = "excadmple.fusion.player"
COMMAND_ID = "excadmple.fusion.open"
_app = None
_ui = None
_palette = None
_renderer = None
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


def _set_step(index, announce=False):
    global _step_index
    if not _package:
        return
    if not isinstance(index, int) or index < 0 or index >= len(_package.data["steps"]):
        raise PackageError("Step out of range")
    _step_index = index
    step = _package.step(index)
    success = _renderer.render(step, _package.data.get("reference_offset_cm"))
    if not success:
        _status("Open or create a Fusion Design to see the reference geometry.", True)
    elif announce:
        _status("Reference step displayed in the Fusion canvas.")
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


class PaletteHandler(adsk.core.HTMLEventHandler):
    def notify(self, args):
        try:
            command = args.action
            body = json.loads(args.data or "{}")
            if command == "ready":
                if _package:
                    _post("example", _package.player_data())
                    _post("step", {"index": _step_index})
            elif command == "load_demo":
                _load(str(ROOT / "examples" / "phone_stand.json"))
            elif command == "open_package":
                _open_dialog()
            elif command == "set_step":
                _set_step(int(body["index"]))
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
        # Explicitly keep transient reference graphics out of saved CAD files.
        global _saving_document
        _saving_document = True
        if _renderer:
            _renderer.clear()


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
    global _app, _ui, _palette, _renderer, _command_def, _command_control
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        _renderer = ReferenceRenderer(_app)

        _palette = _ui.palettes.itemById(PALETTE_ID)
        if not _palette:
            _palette = _ui.palettes.add2(
                PALETTE_ID, "exCADmple", str(ROOT / "ui" / "index.html"),
                True, True, True, 420, 720
            )
        _palette.isDockedInCanvas = False
        _palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
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
        _app.documentSaving.add(before)
        _app.documentSaved.add(after)
        _handlers.extend((before, after))

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
