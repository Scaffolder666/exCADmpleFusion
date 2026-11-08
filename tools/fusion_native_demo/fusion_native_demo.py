"""One-click native HiM test using the real Fusion design that is open.

Open the supplied fusion.f3d in Fusion Desktop FIRST. Then run this script
from Utilities > Scripts and Add-Ins > Scripts > +. It creates a private
copy and an .excadmple with one step per actual timeline item. Reasoning
cues are explicitly hypothetical and are NOT the original designer's words.

This script does NOT write to or save the original .f3d document.
"""
import json
import os
import sys
import traceback
from pathlib import Path

import adsk.core
import adsk.fusion

ROOT = Path(__file__).resolve().parents[2]
OUT = Path.home() / "exCADmple-validation" / "real-fusion"


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    progress = None
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from core.extract_fusion import extract
        from tools.build_native_validation import (
            make_annotation, make_package, synthetic_reasoning_segments)

        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            raise RuntimeError("Open the actual fusion.f3d design first.")
        if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
            raise RuntimeError("This model does not expose a parametric design history.")
        feature_count = design.timeline.count
        if feature_count < 1:
            raise RuntimeError("This model has no Fusion Feature Timeline.")
        if feature_count > 150:
            raise RuntimeError(
                "This model has {} timeline items; the tutorial format supports at most 150. "
                "Use smaller test subsets instead of dropping history silently."
                .format(feature_count))

        OUT.mkdir(parents=True, exist_ok=True)
        source_copy = OUT / "fusion-validation-copy.f3d"
        package_path = OUT / "fusion-native-reasoning.excadmple"

        # Export a separate copy BEFORE rolling through the actual timeline.
        manager = design.exportManager
        export = manager.createFusionArchiveExportOptions(str(source_copy), design.rootComponent)
        if not manager.execute(export) or not source_copy.is_file():
            raise RuntimeError("Could not export a private .f3d reference copy.")

        progress = ui.createProgressDialog()
        progress.isCancelButtonShown = True
        progress.show("exCADmple: read real Feature Timeline",
                      "Extracting %v / %m features", 0, max(1, feature_count))

        def report(index, total, name):
            progress.progressValue = index
            progress.message = "Feature {} of {}: {}".format(index + 1, total, name)
            adsk.doEvents()
            return progress.wasCancelled

        title = (app.activeDocument.name if app.activeDocument else "Fusion model")
        draft = extract(design, title, progress=report, include_meshes=False)
        progress.hide()
        progress = None

        # Keep the source-based evidence separate from synthetic captions.
        (OUT / "fusion.extract.json").write_text(
            json.dumps(draft, ensure_ascii=False, indent=1), encoding="utf-8")
        annotation = make_annotation(draft, title + " · native HiM test")
        (OUT / "fusion.annotation.json").write_text(
            json.dumps(annotation, ensure_ascii=False, indent=1), encoding="utf-8")
        segments = synthetic_reasoning_segments(draft)
        (OUT / "fusion.synthetic_reasoning.json").write_text(
            json.dumps(segments, ensure_ascii=False, indent=1), encoding="utf-8")

        output, steps = make_package(
            draft, source_copy, package_path,
            title=title + " · native HiM test",
            synthetic_reasoning=True, native_only=True)
        ui.messageBox(
            "Created {} test steps from REAL Fusion Timeline entries.\n\n"
            "Package: {}\n\n"
            "Use + Import in exCADmple to open this .excadmple file.\n\n"
            "The explanations are hypothetical TEST text, not recorded designer reasoning.\nNo mesh snapshots were generated. "
            "The original design was not saved."
            .format(steps, output), "exCADmple — native HiM test")
    except Exception:
        ui.messageBox("Could not generate native test package:\n" +
                      traceback.format_exc(), "exCADmple test")
    finally:
        if progress:
            try:
                progress.hide()
            except Exception:
                pass


def stop(context):
    pass
