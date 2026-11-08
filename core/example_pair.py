"""Local exCADmple example: a sidecar JSON and an original Fusion .f3d.

No mesh snapshots or ZIP are necessary. When auto_generate is enabled, the
actual Fusion Timeline is read *after importing a disposable document copy*.
Synthetic text is explicitly identified as hypothetical, not recorded speech.
"""
import hashlib
import json
from pathlib import Path

from .packages import ExamplePackage, PackageError, MAX_STEPS, _validate

KIND_LABELS = {
    "Sketch": "Sketch", "ExtrudeFeature": "Extrude", "RevolveFeature": "Revolve",
    "FilletFeature": "Fillet", "ChamferFeature": "Chamfer", "CombineFeature": "Combine",
    "MirrorFeature": "Mirror", "MirrorPattern": "Mirror", "MirrorPatternFeature": "Mirror",
    "CircularPatternFeature": "Circular Pattern", "RectangularPatternFeature": "Rectangular Pattern",
    "MoveFeature": "Move", "OffsetFacesFeature": "Offset Faces",
    "BaseFeature": "Base Feature", "PasteBodiesFeature": "Paste Bodies",
    "HoleFeature": "Hole", "ShellFeature": "Shell", "SweepFeature": "Sweep",
    "LoftFeature": "Loft", "ThreadFeature": "Thread",
    "ConstructionPlane": "Construction Plane",
}
HYPOTHESES = {
    "Sketch": "This sketch may establish editable profiles or geometric constraints for a later operation.",
    "ExtrudeFeature": "This extrusion may control material thickness, reach, or clearance.",
    "RevolveFeature": "This revolve may help form a rotationally symmetric part around an axis.",
    "FilletFeature": "The rounded transition may affect edge treatment or manufacturing.",
    "ChamferFeature": "The chamfer may provide an edge transition or assembly lead-in.",
    "CombineFeature": "This combine may consolidate or remove overlapping volumes.",
    "MirrorFeature": "A mirrored feature may help maintain symmetry.",
    "MirrorPattern": "Mirroring may help maintain symmetry between related forms.",
    "MirrorPatternFeature": "Mirroring may help maintain symmetry between related forms.",
    "CircularPatternFeature": "The repeated geometry may maintain regular angular spacing.",
    "RectangularPatternFeature": "The repeated geometry may maintain consistent linear spacing.",
    "MoveFeature": "This move may adjust alignment or placement relative to other parts.",
    "OffsetFacesFeature": "The offset may adjust local fit, thickness, or clearance.",
    "BaseFeature": "This feature establishes geometry; the specific design goal is not known.",
    "PasteBodiesFeature": "This operation may reuse previously modeled geometry.",
    "HoleFeature": "This hole may provide a passage, fastener seat, or clearance.",
    "ShellFeature": "The shell may create an enclosure or reduce material.",
}

def hypothetical_transcript(name, kind):
    """Hypothesis only; CAD history cannot identify the actual human rationale."""
    message = HYPOTHESES.get(kind, "The purpose of this modeling operation is not known.")
    return "SIMULATED DESIGN EXPLANATION (not the original designer's words). " + name + ": " + message

def _local_filename(raw, label):
    if not isinstance(raw, str) or not raw or raw in (".", ".."):
        raise PackageError(label + " must be a filename in the JSON folder")
    if Path(raw).name != raw or "/" in raw or "\\" in raw or ":" in raw:
        raise PackageError(label + " must not include paths")
    return raw

def _feature_ref(ref, by_index, by_name):
    if isinstance(ref, dict):
        idx = ref.get("index")
        required_name = ref.get("name")
        required_kind = ref.get("kind")
    elif isinstance(ref, int) and not isinstance(ref, bool):
        idx, required_name, required_kind = ref, None, None
    elif isinstance(ref, str):
        matches = by_name.get(ref, [])
        if len(matches) != 1:
            raise PackageError("Feature name " + repr(ref) + " is missing or ambiguous; use timeline index")
        idx, required_name, required_kind = matches[0].index, ref, None
    else:
        raise PackageError("Feature references must have an index or an unambiguous name")
    if isinstance(idx, bool) or not isinstance(idx, int) or idx not in by_index:
        raise PackageError("Timeline feature index " + repr(idx) + " is missing")
    actual = by_index[idx]
    if required_name is not None and required_name != actual.name:
        raise PackageError("Timeline changed at index {}: expected {}, got {}".format(
            idx, required_name, actual.name))
    if required_kind is not None and required_kind != actual.kind:
        raise PackageError("Feature type changed at index " + str(idx))
    return actual

class LocalPairPackage(ExamplePackage):
    """An ExamplePackage-compatible adapter that resolves real Fusion history."""

    needs_populate = True

    def __init__(self, raw, json_path):
        if not isinstance(raw, dict) or raw.get("format") != "excadmple-pair" or raw.get("version") != 1:
            raise PackageError("Expected excadmple-pair JSON version 1")
        self.json_path = Path(json_path).resolve()
        self.asset_root = self.json_path.parent
        self.source_path = self.json_path
        self.temporary = None
        self.generated_path = None
        self.raw = raw
        model = _local_filename(raw.get("model"), "model")
        if not model.lower().endswith(".f3d"):
            raise PackageError("The model must be a Fusion .f3d archive")
        self.model_path = (self.asset_root / model).resolve()
        if not self.model_path.is_file() or not self.model_path.is_relative_to(self.asset_root):
            raise PackageError("Put the named .f3d alongside the JSON")
        digest = raw.get("model_sha256")
        if digest:
            if not isinstance(digest, str) or len(digest) != 64 or any(
                    c not in "0123456789abcdefABCDEF" for c in digest):
                raise PackageError("Invalid model_sha256")
            actual_digest = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
            if actual_digest.lower() != digest.lower():
                raise PackageError("This JSON references a different .f3d; its SHA-256 does not match")
        self.data = {
            "format": "excadmple", "version": 2,
            "title": raw.get("title") or self.model_path.stem,
            "id": raw.get("id") or self.model_path.stem,
            "description": raw.get("description") or "",
            "source_model": model,
            "steps": [],
        }

    def source_model_path(self):
        return self.model_path

    def populate_from_features(self, features):
        """Build player steps from the imported, real .f3d Feature Timeline."""
        features = sorted(features, key=lambda f: f.index)
        if not features:
            raise PackageError("This .f3d has no accessible parametric Feature Timeline")
        if len(features) > MAX_STEPS:
            raise PackageError("This Fusion design has {} features; maximum {}. "
                               "Do not silently truncate the Timeline.".format(len(features), MAX_STEPS))
        duration = self.raw.get("step_duration_ms", 8000)
        if isinstance(duration, bool) or not isinstance(duration, int) or not 500 <= duration <= 60000:
            raise PackageError("step_duration_ms must be an integer from 500 to 60000")
        by_index = {f.index: f for f in features}
        by_name = {}
        for feature in features:
            by_name.setdefault(feature.name, []).append(feature)
        auto = bool(self.raw.get("auto_generate", False))
        supplied = self.raw.get("steps", [])
        if not isinstance(supplied, list):
            raise PackageError("steps must be a list")
        if auto:
            supplied = [{
                "id": "feature-" + str(feature.index),
                "title": feature.name,
                "features": [{"index": feature.index, "name": feature.name, "kind": feature.kind}],
                "transcript": hypothetical_transcript(feature.name, feature.kind),
                "reasoning_source": "simulated",
            } for feature in features]
        if not supplied:
            raise PackageError("Provide steps or enable auto_generate")
        if len(supplied) > MAX_STEPS:
            raise PackageError("Too many tutorial steps")
        constructed = []
        last_index = -1
        persisted = []
        used_ids = set()
        for i, item in enumerate(supplied):
            if not isinstance(item, dict):
                raise PackageError("A step must be an object")
            refs = item.get("features") or []
            if not isinstance(refs, list) or not refs:
                raise PackageError("Step {} needs at least one feature".format(i+1))
            matched = [_feature_ref(ref, by_index, by_name) for ref in refs]
            matched.sort(key=lambda f: f.index)
            if matched[0].index <= last_index or len({f.index for f in matched}) != len(matched):
                raise PackageError("Feature references must be unique and in Timeline order")
            last_index = matched[-1].index
            step_id = str(item.get("id") or ("step-" + str(i + 1)))
            if step_id in used_ids:
                raise PackageError("Duplicate step ID " + step_id)
            used_ids.add(step_id)
            title = str(item.get("title") or matched[-1].name)
            step_duration = item.get("duration_ms", duration)
            if isinstance(step_duration, bool) or not isinstance(step_duration, int) or not 500 <= step_duration <= 60000:
                raise PackageError("Step duration_ms must be 500–60000")
            cues = item.get("cues")
            narration = item.get("transcript", "")
            if cues is None:
                cues = [{"at_ms": 250, "label": narration}] if isinstance(narration, str) and narration else []
            if not isinstance(cues, list):
                raise PackageError("cues must be a list")
            clean_cues = []
            for cue in cues:
                if not isinstance(cue, dict):
                    raise PackageError("Cue must be an object")
                when = cue.get("at_ms", 0)
                label = cue.get("label", cue.get("text"))
                if isinstance(when, bool) or not isinstance(when, (int, float)) or not 0 <= when <= step_duration or not isinstance(label, str):
                    raise PackageError("Invalid timed transcript cue")
                clean_cues.append({"at_ms": when, "label": label})
            media = {}
            audio = item.get("audio", self.raw.get("audio"))
            if audio:
                filename = _local_filename(audio, "audio")
                if (self.asset_root / filename).is_file():
                    media["audio"] = filename
                    media["offset_ms"] = int(item.get("audio_offset_ms", 0))
                else:
                    raise PackageError("Audio file not found: " + filename)
            constructed.append({
                "id": step_id, "title": title, "duration_ms": step_duration,
                "source_features": [{"index": f.index, "name": f.name, "kind": f.kind} for f in matched],
                "tools": [KIND_LABELS.get(f.kind, f.kind.replace("Feature", "")) for f in matched],
                "geometry": {"meshes": []}, "cues": clean_cues, "media": media,
            })
            persisted.append({
                "id": step_id, "title": title,
                "features": [{"index": f.index, "name": f.name, "kind": f.kind} for f in matched],
                "duration_ms": step_duration,
                "transcript": narration if isinstance(narration, str) else "",
                "reasoning_source": item.get("reasoning_source", "user"),
            })
            # A generated file should have ONE editable transcript field.
            # Preserve explicit timed cues only when authored by the user.
            if not auto and item.get("cues") is not None:
                persisted[-1]["cues"] = clean_cues
        self.data["steps"] = constructed
        _validate(self.data)
        self.needs_populate = False
        # A concrete editable JSON is generated once; subsequent loads can use
        # this file directly, with no re-generation of synthetic explanations.
        if auto:
            output = dict(self.raw)
            output["auto_generate"] = False
            output["steps"] = persisted
            target = self.json_path.with_name(self.json_path.stem + ".generated.json")
            if target.is_file():
                # Never overwrite a researcher's hand-edited transcript.
                self.generated_path = target
            else:
                try:
                    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    self.generated_path = target
                except OSError:
                    pass  # read-only folders may still play the example
        return self.data["steps"]
