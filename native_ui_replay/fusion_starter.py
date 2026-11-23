"""exCADmple native Fusion replay: create a *starter* phone-stand .f3d.

Run this file as a Fusion Script (not in system Python).
Only SKETCHES are pre-made. The user watches the macOS UI driver perform
actual EXTRUDE and FILLET commands in the Fusion interface.
Re-run to get a fresh, disposable starter and repeat the replay.
"""
from pathlib import Path
import traceback

import adsk.core
import adsk.fusion


def _rectangle(sketch, x1, y1, x2, y2):
    points = adsk.core.Point3D
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        points.create(x1, y1, 0), points.create(x2, y2, 0))
    sketch.isVisible = True
    return sketch


def _offset_plane(component, source_plane, mm):
    planes = component.constructionPlanes
    definition = planes.createInput()
    definition.setByOffset(
        source_plane, adsk.core.ValueInput.createByString(str(mm) + " mm"))
    result = planes.add(definition)
    result.isVisible = False
    return result


def build_starter(app):
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("Could not create a Fusion design.")
    root = design.rootComponent
    # Units in Fusion API point geometry are CENTIMETERS.
    base = root.sketches.add(root.xYConstructionPlane)
    base.name = "01 BASE profile · extrude 8 mm"
    _rectangle(base, -6, -4, 6, 4)

    rear_plane = _offset_plane(root, root.xZConstructionPlane, 32)
    rear = root.sketches.add(rear_plane)
    rear.name = "02 BACK SUPPORT profile · extrude 6 mm"
    _rectangle(rear, -5, 0, 5, 7.5)

    front_plane = _offset_plane(root, root.xZConstructionPlane, -32)
    front = root.sketches.add(front_plane)
    front.name = "03 FRONT LIP profile · extrude 5 mm"
    _rectangle(front, -5, 0, 5, 1.3)

    for sketch in (base, rear, front):
        sketch.isVisible = True
    app.activeViewport.fit()
    app.activeViewport.refresh()

    folder = Path.home() / "Documents" / "exCADmpleNativeReplay"
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / "PhoneStand_STARTER.f3d"
    options = design.exportManager.createFusionArchiveExportOptions(
        str(output), root)
    if not design.exportManager.execute(options):
        raise RuntimeError("Fusion export returned False.")
    return output


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        result = build_starter(app)
        ui.messageBox(
            "Created a reusable starter with THREE real sketch profiles.\n\n"
            "The solid geometry is deliberately NOT prebuilt: the native UI "
            "driver will create it through Fusion's own Extrude and Fillet "
            "dialogs.\n\n"
            "Starter: " + str(result) + "\n\n"
            "1. Keep this document open, show sketches, and use an isometric view.\n"
            "2. Run mac_replay.py --teach once to learn the click positions.\n"
            "3. Reopen the starter and run mac_replay.py --play.\n\n"
            "Do not save your replay over the starter file.",
            "exCADmple · Native Fusion Replay")
    except Exception:
        ui.messageBox(traceback.format_exc(), "Native replay starter failed")
