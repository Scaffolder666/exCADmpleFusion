"""Assemble a version-2 example package from the three source files.

* extracted draft (from the designer's .f3d, see core/extract_fusion.py),
* annotation (written by the researcher),
* timestamped transcript of the think-aloud recording.

Pure Python. Every step's geometry, operation and parameters come from the
extracted draft; every word of reasoning comes from the annotation and the
transcript. Nothing is inferred about the designer's intent; only feature
input relations are used to *derive* possible dependencies, and those are
labelled as derived.
"""
import json
import zipfile
from pathlib import Path, PurePosixPath

from . import transcript as transcript_mod
from .packages import _validate as validate_package, PackageError

EXTRACT_FORMAT = "excadmple-extract"
ANNOTATION_FORMAT = "excadmple-annotation"
SCOPES = ("general", "goal_specific")
LABELS = {
    "Sketch": "Sketch", "ExtrudeFeature": "Extrude", "RevolveFeature": "Revolve",
    "FilletFeature": "Fillet", "ChamferFeature": "Chamfer", "HoleFeature": "Hole",
    "ShellFeature": "Shell", "MirrorFeature": "Mirror", "CombineFeature": "Combine",
    "CircularPatternFeature": "Circular pattern", "RectangularPatternFeature": "Rectangular pattern",
    "MoveFeature": "Move", "SweepFeature": "Sweep", "LoftFeature": "Loft", "ThreadFeature": "Thread",
    "SplitBodyFeature": "Split body", "ConstructionPlane": "Construction plane",
}
MAX_PARAMETERS = 8


class AuthoringError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise AuthoringError(message)


# --- inputs ----------------------------------------------------------------------------
def check_extract(data):
    _require(isinstance(data, dict) and data.get("format") == EXTRACT_FORMAT and data.get("version") == 1,
             "Not an exCADmple extract (format excadmple-extract, version 1)")
    _require(isinstance(data.get("meshes"), dict), "Extract needs a mesh library")
    features = data.get("features")
    _require(isinstance(features, list) and features, "Extract has no timeline features")
    seen = set()
    for feature in features:
        _require(isinstance(feature, dict) and isinstance(feature.get("index"), int)
                 and isinstance(feature.get("name"), str), "Each feature needs index and name")
        _require(feature["index"] not in seen, "Duplicate feature index")
        seen.add(feature["index"])
        for mesh_id in feature.get("state", []):
            _require(mesh_id in data["meshes"], "Unknown mesh id " + str(mesh_id))
    return data


def check_annotation(data):
    _require(isinstance(data, dict) and data.get("format") == ANNOTATION_FORMAT and data.get("version") == 1,
             "Not an exCADmple annotation (format excadmple-annotation, version 1)")
    for key in ("id", "title", "designer", "date"):
        _require(isinstance(data.get(key), str) and data[key].strip(), "Annotation needs " + key)
    brief = data.get("brief")
    _require(isinstance(brief, dict) and isinstance(brief.get("goal"), str) and brief["goal"].strip(),
             "Annotation needs brief.goal — the designer's own design goal")
    steps = data.get("steps")
    _require(isinstance(steps, list) and steps, "Annotation needs steps")
    ids = set()
    for step in steps:
        _require(isinstance(step, dict) and isinstance(step.get("id"), str) and step["id"], "Step needs an id")
        _require(step["id"] not in ids, "Duplicate step id " + step["id"])
        ids.add(step["id"])
        _require(isinstance(step.get("title"), str) and step["title"].strip(), "Step " + step["id"] + " needs a title")
        _require(isinstance(step.get("summary"), str) and step["summary"].strip(),
                 "Step " + step["id"] + " needs a summary of what the designer said")
        _require(isinstance(step.get("features"), list) and step["features"],
                 "Step " + step["id"] + " needs its timeline features")
        rec = step.get("recording")
        _require(isinstance(rec, dict) and all(isinstance(rec.get(k), (int, float)) for k in ("start_ms", "end_ms"))
                 and 0 <= rec["start_ms"] < rec["end_ms"], "Step " + step["id"] + " needs recording start_ms < end_ms")
        scope = step.get("scope")
        if scope is not None:
            _require(isinstance(scope, dict) and scope.get("kind") in SCOPES,
                     "Step " + step["id"] + ": scope.kind must be general or goal_specific")
    return data


# --- assembly ---------------------------------------------------------------------------
def _resolve(features, refs, step_id):
    by_index = {f["index"]: f for f in features}
    out = []
    for ref in refs:
        if isinstance(ref, int) and not isinstance(ref, bool):
            _require(ref in by_index, "Step %s: no timeline item %d" % (step_id, ref))
            out.append(by_index[ref])
            continue
        matches = [f for f in features if f["name"] == ref]
        _require(matches, "Step %s: no timeline item named %r" % (step_id, ref))
        _require(len(matches) == 1, "Step %s: %r is ambiguous; use its index" % (step_id, ref))
        out.append(matches[0])
    return sorted(out, key=lambda f: f["index"])


def _state(extract, ids):
    return [extract["meshes"][i] for i in ids]


def _tool(features):
    labels = []
    for feature in features:
        label = LABELS.get(feature.get("kind", ""), feature.get("kind", "Operation").replace("Feature", ""))
        if not labels or labels[-1] != label:
            labels.append(label)
    return " → ".join(labels)


def _parameters(features):
    params = []
    for feature in features:
        for param in feature.get("parameters", []):
            params.append({"name": feature["name"] + " · " + param["name"],
                           "value": param.get("expression") or str(param.get("value", ""))})
    return params[:MAX_PARAMETERS]


def _media_name(path):
    return str(PurePosixPath("media") / Path(path).name)


def build_manifest(extract, annotation, segments, offset_cm=None, source_model=None):
    check_extract(extract)
    check_annotation(annotation)
    transcript_mod.validate(segments)
    features = sorted(extract["features"], key=lambda f: f["index"])
    recording = annotation.get("recording") or {}
    owner = {}             # feature index -> step id
    steps, last_index, last_end = [], -1, -1
    for item in annotation["steps"]:
        feats = _resolve(features, item["features"], item["id"])
        _require(feats[0]["index"] > last_index,
                 "Step %s overlaps or precedes the previous step's features" % item["id"])
        rec = item["recording"]
        _require(rec["start_ms"] >= last_end, "Step %s starts before the previous step ends" % item["id"])
        earlier = [f for f in features if f["index"] < feats[0]["index"]]
        before = _state(extract, earlier[-1].get("state", [])) if earlier else []
        states = [before]
        for feature in feats:
            state = _state(extract, feature.get("state", []))
            if state != states[-1]:
                states.append(state)
        if len(states) == 1:
            states.append(states[0])        # e.g. a sketch-only step
        duration = int(rec["end_ms"] - rec["start_ms"])
        step = {
            "id": item["id"], "title": item["title"], "duration_ms": max(500, duration),
            "geometry": {"meshes": states[-1]},
            "animation": {"type": "snapshots", "states": states},
            "operation": {"tool": _tool(feats), "parameters": _parameters(feats),
                          "instruction": ", ".join(f["name"] for f in feats)},
            "source_features": [{"index": f["index"], "name": f["name"], "kind": f.get("kind", "")} for f in feats],
            "reasoning": {"text": item["summary"], "source": "think_aloud"},
            "cues": transcript_mod.within(segments, rec["start_ms"], rec["end_ms"]),
            "media": {},
        }
        if item.get("goal"):
            step["goal"] = item["goal"]
        for kind in ("audio", "video"):
            if recording.get(kind):
                step["media"][kind] = _media_name(recording[kind])
        if step["media"]:
            step["media"]["offset_ms"] = int(rec["start_ms"])
        for key in ("decision", "scope", "depends_on"):
            if item.get(key) is not None:
                step[key] = item[key]
        derived = []
        for feature in feats:
            for source in list(feature.get("inputs", {}).get("features", [])) + \
                    list(feature.get("inputs", {}).get("sketches", [])):
                sid = owner.get(source)
                if sid and sid not in derived:
                    derived.append(sid)
        if derived:
            step["depends_on_derived"] = derived
        for feature in feats:
            owner[feature["index"]] = item["id"]
        steps.append(step)
        last_index, last_end = feats[-1]["index"], rec["end_ms"]
    known = [s["id"] for s in steps]
    for i, step in enumerate(steps):
        for dep in step.get("depends_on", []):
            _require(dep in known[:i], "Step %s depends on unknown or later step %r" % (step["id"], dep))
    if offset_cm is None:
        xs = [v[0] for m in steps[-1]["geometry"]["meshes"] for v in m["vertices"]]
        offset_cm = [round(14 - min(xs), 3) if xs else 14, 0, 0]
    manifest = {
        "format": "excadmple", "version": 2,
        "id": annotation["id"], "title": annotation["title"],
        "designer": annotation["designer"], "date": annotation["date"],
        "brief": annotation["brief"],
        "description": annotation.get("description", annotation["brief"]["goal"]),
        "provenance": {"geometry": "extracted", "reasoning": "think_aloud",
                       "source_file": (extract.get("source") or {}).get("file", "")},
        "reference_offset_cm": offset_cm,
        "steps": steps,
    }
    if source_model:
        # Version A plays the tutorial on a copy of this model (HiM style).
        manifest["source_model"] = str(PurePosixPath("source") / Path(source_model).name)
    try:
        validate_package(manifest)
    except PackageError as error:
        raise AuthoringError("Assembled package is invalid: " + str(error)) from error
    return manifest


def write_package(manifest, out_path, media_paths=(), source_model=None):
    """ZIP: manifest.json + media/<file> for the recordings + source/<.f3d>."""
    wanted = {m.get(k) for s in manifest["steps"] for m in [s.get("media", {})] for k in ("audio", "video")}
    wanted.discard(None)
    provided = {_media_name(p): Path(p) for p in media_paths}
    missing = sorted(wanted - set(provided))
    _require(not missing, "Missing media files: " + ", ".join(missing))
    out_path = Path(out_path)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        for name in sorted(wanted):
            archive.write(provided[name], name)
        if manifest.get("source_model"):
            _require(source_model and Path(source_model).is_file(), "Missing source model " + manifest["source_model"])
            archive.write(source_model, manifest["source_model"])
    return out_path
