"""Fusion Desktop script: build the HiM validation model and its tutorial.

Run from Fusion: Utilities > Scripts and Add-Ins > Scripts > + > choose this
folder (tools/fusion_demo) > Run. It
1. creates a new parametric design: Sketch1 rectangle, Extrude1 (1 cm),
   Fillet1 on the four vertical edges (0.5 cm), Sketch2 circle on the top
   face, Extrude2 (2 cm, join), a construction plane and Mirror1 of Extrude2;
2. saves it as HiMValidation.f3d;
3. extracts the tutorial draft (one model state per feature);
4. writes him-validation.excadmple (with the .f3d as source model).
Output folder: ~/exCADmple-validation. Then follow docs/FUSION_DESKTOP_TEST.md.

This script has not been run in Fusion Desktop by its author: it is written
against the documented Fusion API and is part of what needs validating.
"""
import json
import os
import sys
import traceback

import adsk.core
import adsk.fusion

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(os.path.expanduser("~"), "exCADmple-validation")


def _cm(text):
    return adsk.core.ValueInput.createByString(text)


def _point(x, y, z=0.0):
    return adsk.core.Point3D.create(x, y, z)


def _vertical_edges(body):
    edges = adsk.core.ObjectCollection.create()
    for i in range(body.edges.count):
        edge = body.edges.item(i)
        start, end = edge.startVertex.geometry, edge.endVertex.geometry
        if abs(start.z - end.z) > 0.5 and abs(start.x - end.x) < 1e-6 and abs(start.y - end.y) < 1e-6:
            edges.add(edge)
    return edges


def _top_face(body, z):
    best = None
    for i in range(body.faces.count):
        face = body.faces.item(i)
        plane = adsk.core.Plane.cast(face.geometry)
        if plane and plane.normal.z > 0.99 and abs(face.pointOnFace.z - z) < 1e-6:
            if best is None or face.area > best.area:
                best = face
    if best is None:
        raise RuntimeError("Top face not found")
    return best


def build(design):
    root = design.rootComponent
    features = root.features
    new_body = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    join = adsk.fusion.FeatureOperations.JoinFeatureOperation

    sketch1 = root.sketches.add(root.xYConstructionPlane)
    sketch1.sketchCurves.sketchLines.addTwoPointRectangle(_point(0, 0), _point(8, 6))
    extrude1 = features.extrudeFeatures.addSimple(sketch1.profiles.item(0), _cm("1 cm"), new_body)
    body = extrude1.bodies.item(0)

    fillet_input = features.filletFeatures.createInput()
    edges = _vertical_edges(body)
    try:
        fillet_input.edgeSetInputs.addConstantRadiusEdgeSet(edges, _cm("0.5 cm"), True)
    except AttributeError:          # older API
        fillet_input.addConstantRadiusEdgeSet(edges, _cm("0.5 cm"), True)
    features.filletFeatures.add(fillet_input)

    sketch2 = root.sketches.add(_top_face(body, 1.0))
    center = sketch2.modelToSketchSpace(_point(2, 3, 1))
    sketch2.sketchCurves.sketchCircles.addByCenterRadius(center, 0.8)
    circle = min((sketch2.profiles.item(i) for i in range(sketch2.profiles.count)),
                 key=lambda p: p.areaProperties().area)
    extrude2 = features.extrudeFeatures.addSimple(circle, _cm("2 cm"), join)

    plane_input = root.constructionPlanes.createInput()
    plane_input.setByOffset(root.yZConstructionPlane, _cm("4 cm"))
    plane = root.constructionPlanes.add(plane_input)
    entities = adsk.core.ObjectCollection.create()
    entities.add(extrude2)
    features.mirrorFeatures.add(features.mirrorFeatures.createInput(entities, plane))


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from core.tutorial.extract_fusion import extract
        from core.authoring import build_manifest, write_package
        from tools.demo_tutorial import annotation_and_transcript

        os.makedirs(OUT, exist_ok=True)
        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        build(design)

        f3d = os.path.join(OUT, "HiMValidation.f3d")
        manager = design.exportManager
        manager.execute(manager.createFusionArchiveExportOptions(f3d, design.rootComponent))

        draft = extract(design, "HiMValidation.f3d")
        annotation, segments = annotation_and_transcript(draft)
        for name, data in (("draft.extract.json", draft), ("annotation.json", annotation),
                           ("transcript.json", segments)):
            with open(os.path.join(OUT, name), "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=1)
        manifest = build_manifest(draft, annotation, segments, source_model=f3d)
        package = write_package(manifest, os.path.join(OUT, "him-validation.excadmple"), (), f3d)
        timeline = ", ".join("{} ({})".format(f["name"], f["kind"]) for f in draft["features"])
        ui.messageBox("Wrote {}\n\nTimeline: {}".format(package, timeline), "exCADmple validation model")
    except Exception:
        ui.messageBox("Failed:\n" + traceback.format_exc(), "exCADmple validation model")
