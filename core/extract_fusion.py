"""Extract a tutorial draft from the designer's .f3d (run inside Fusion).

For every timeline item the marker is rolled to just after it and the meshes
of all visible bodies are recorded. For features with parameters, the
History in Motion animation is recorded as well: the parameters grow from
~0 to their value (extrude distance, revolve angle, fillet radius, pattern
spacing...) and Fusion recomputes the model at each frame. These frames let
version B and the Blender player show the same animation as HiM without
the source model. Every parameter is restored; the marker too.
Output follows docs/EXAMPLE_FORMAT.md (excadmple-extract).
"""
import hashlib
import json
import time

import adsk.core
import adsk.fusion

from .him_fusion import FusionTimelineModel, all_feature_parameters, _items, _model_parameters
from .him_motion import PARAMETRIC, RestoreJournal, animation_mode, interpolate

DIGITS = 4
FRAMES_PER_FEATURE = 8      # HiM parameter-animation frames recorded per feature


def _visible_bodies(design):
    root = design.rootComponent
    bodies = list(_items(root.bRepBodies))
    for occurrence in _items(root.allOccurrences):
        bodies.extend(_items(occurrence.bRepBodies))      # assembly-context proxies
    out = []
    for body in bodies:
        try:
            if body.isVisible:
                out.append(body)
        except Exception:
            continue
    return out


def body_mesh(body):
    calculator = body.meshManager.createMeshCalculator()
    calculator.setQuality(adsk.fusion.TriangleMeshQualityOptions.LowQualityTriangleMesh)
    mesh = calculator.calculate()
    coords = list(mesh.nodeCoordinatesAsDouble)
    indices = list(mesh.nodeIndices)
    vertices = [[round(coords[i], DIGITS), round(coords[i + 1], DIGITS), round(coords[i + 2], DIGITS)]
                for i in range(0, len(coords) - 2, 3)]
    triangles = [indices[i:i + 3] for i in range(0, len(indices) - 2, 3)]
    return {"vertices": vertices, "triangles": triangles}


def _mesh_id(mesh):
    return hashlib.sha1(json.dumps(mesh, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def _capture(design, meshes):
    """Mesh ids of every visible body, adding new meshes to the library."""
    state = []
    for body in _visible_bodies(design):
        mesh = body_mesh(body)
        key = _mesh_id(mesh)
        meshes.setdefault(key, mesh)
        state.append(key)
    return state


def _parameter_frames(design, entity, info, meshes, count=FRAMES_PER_FEATURE):
    """HiM animation of one feature: its parameters from ~0 towards their
    value, recomputed by Fusion, captured as model states (the final state
    is recorded separately). Empty for features without parameters."""
    if animation_mode(info.kind) != PARAMETRIC:
        return []
    params = _model_parameters(design, entity, info.kind)
    if not params:
        return []
    journal = RestoreJournal()
    targets = []
    for param in params:
        journal.capture(param.name, param)
        targets.append((param, param.value))
    frames = []
    try:
        for k in range(count):
            t = k / count                     # 0, 1/8, ... 7/8; 1.0 is the final state
            try:
                for param, target in targets:
                    param.value = interpolate(target, t)
            except Exception:
                continue                      # Fusion rejected this value; skip the frame
            state = _capture(design, meshes)
            if not frames or frames[-1] != state:
                frames.append(state)
    finally:
        journal.restore()
    return frames


def extract(design, source_name="", progress=None):
    """Return the excadmple-extract dict for a parametric design."""
    model = FusionTimelineModel(design)
    meshes, features = {}, []
    items = model.features()
    try:
        for count, info in enumerate(items):
            if progress and progress(count, len(items), info.name):
                raise RuntimeError("Extraction canceled")
            entity = model.entity(info)
            inputs = {"sketches": [], "features": []}
            if not info.is_sketch:
                for ref in model.input_geometries(info):        # marker before the item
                    if ref.kind in ("sketch", "feature") and ref.feature is not None:
                        bucket = inputs["sketches" if ref.kind == "sketch" else "features"]
                        if ref.feature.index not in bucket:
                            bucket.append(ref.feature.index)
            model.go(info.index + 1)                             # marker after the item
            frames = _parameter_frames(design, entity, info, meshes) if entity is not None else []
            state = _capture(design, meshes)
            parameters = []
            for param in all_feature_parameters(design, entity) if entity is not None else []:
                parameters.append({"name": param.name, "expression": param.expression,
                                   "value": param.value, "unit": param.unit})
            try:
                suppressed = bool(entity.isSuppressed)
            except Exception:
                suppressed = False
            features.append({"index": info.index, "name": info.name, "kind": info.kind,
                             "suppressed": suppressed, "parameters": parameters,
                             "inputs": inputs, "frames": frames, "state": state})
    finally:
        model.restore()
    return {
        "format": "excadmple-extract", "version": 1,
        "source": {"file": source_name, "units": "cm",
                   "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "timeline_count": len(items)},
        "meshes": meshes, "features": features,
    }


def extract_with_dialog(app, ui):
    """Palette command: choose where to save, extract with a progress bar."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise ValueError("Open the designer's .f3d first")
    name = app.activeDocument.name if app.activeDocument else "design"
    dialog = ui.createFileDialog()
    dialog.title = "Save example draft"
    dialog.filter = "exCADmple extract (*.extract.json)"
    dialog.initialFilename = name + ".extract.json"
    if dialog.showSave() != adsk.core.DialogResults.DialogOK:
        return "Extraction canceled."
    bar = ui.createProgressDialog()
    bar.isCancelButtonShown = True
    bar.show("Extracting example draft", "%v of %m timeline items", 0, max(1, design.timeline.count))

    def progress(done, total, label):
        bar.progressValue = done
        bar.message = label + " (%v of %m)"
        adsk.doEvents()
        return bar.wasCancelled

    try:
        data = extract(design, name + ".f3d", progress)
    finally:
        bar.hide()
    with open(dialog.filename, "w", encoding="utf-8") as handle:
        json.dump(data, handle, separators=(",", ":"))
    return "Draft saved: %d timeline items, %d distinct meshes → %s" % (
        len(data["features"]), len(data["meshes"]), dialog.filename)
