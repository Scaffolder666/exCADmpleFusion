"""Build a native-HiM validation package from a real Fusion .f3d archive.

First open the .f3d in Fusion Desktop and run "Extract tutorial draft..."
to save its timeline to a .extract.json file. Then, OUTSIDE Fusion:

  python tools/build_native_validation.py my.extract.json my.f3d \
      -o my-validation.excadmple

This is strictly a structural test fixture. It has one step per real
timeline item, no invented design intent, no fabricated tool timestamps,
and no audio, transcript, or pointer events. The .f3d is embedded so
the HiM player can animate genuine feature parameters instead of relying
on precomputed mesh transitions. NEVER overwrite the source .f3d.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.authoring import build_manifest, check_extract, write_package, LABELS  # noqa: E402
from core.tutorial.packages import _validate as validate_package, MAX_STEPS  # noqa: E402



# These explanations are HYPOTHETICAL study stimuli, not the original
# designer's reasoning. CAD history does not reveal human intent.
HYPOTHETICAL_PURPOSES = {
    "Sketch": "This sketch defines profiles or references for later operations. A possible consideration is keeping those references editable.",
    "ExtrudeFeature": "This extrusion changes material along a direction. A possible consideration is controlling height, depth, thickness, or clearance.",
    "RevolveFeature": "This revolve forms geometry around an axis. A possible consideration is a rotationally symmetric form.",
    "FilletFeature": "This fillet rounds existing edges. A possible consideration is an edge transition, but fabrication or ergonomic intent is not knowable from CAD history alone.",
    "ChamferFeature": "This chamfer bevels edges. A possible consideration is edge transition or assembly clearance.",
    "CombineFeature": "This combine feature changes the interaction of bodies. A possible consideration is how separate solid volumes fit together.",
    "MirrorFeature": "This mirror reuses geometry across a plane. A possible consideration is keeping matching features symmetrical.",
    "MirrorPatternFeature": "This mirror pattern reuses geometry across a plane. A possible consideration is symmetry.",
    "CircularPatternFeature": "This pattern repeats geometry around an axis. A possible consideration is uniform repetition.",
    "RectangularPatternFeature": "This pattern repeats geometry in linear directions. A possible consideration is consistent spacing.",
    "MoveFeature": "This operation changes geometry's location or orientation. A possible consideration is part alignment.",
    "OffsetFacesFeature": "This offset adjusts faces. A possible consideration is local size or clearance.",
    "ShellFeature": "This shell changes wall structure. A possible consideration is a hollow enclosure or material reduction.",
    "BaseFeature": "This feature introduces or establishes geometry. The purpose requires confirmation.",
    "PasteBodiesFeature": "This operation introduces existing bodies. A possible consideration is reusing model elements.",
}


def hypothetical_reasoning(feature):
    """A clearly labeled speculation grounded only in extracted feature data."""
    kind = str(feature.get("kind") or "Feature")
    name = str(feature.get("name") or kind)
    interpretation = HYPOTHETICAL_PURPOSES.get(
        kind, "This changes the modeling history. The design intention is unknown.")
    parameters = []
    for param in (feature.get("parameters") or [])[:3]:
        label, expression = str(param.get("name") or ""), str(param.get("expression") or "")
        if label and expression:
            parameters.append(label + " = " + expression)
    details = " Recorded parameters: " + "; ".join(parameters) + "." if parameters else ""
    inputs = feature.get("inputs") or {}
    dependencies = list(inputs.get("sketches") or []) + list(inputs.get("features") or [])
    relations = (" Earlier timeline references: " +
                 ", ".join(str(i) for i in dependencies[:4]) + ".") if dependencies else ""
    return ("SIMULATED TEST REASONING (not the designer's words). " +
            name + ": " + interpretation + details + relations)


def synthetic_reasoning_segments(extract, duration_ms=4000):
    """One hypothesis cue for each true timeline feature, at synthetic times."""
    check_extract(extract)
    features = sorted(extract["features"], key=lambda f: f["index"])
    pad = min(250, duration_ms // 8)
    return [{"start_ms": i * duration_ms + pad,
             "end_ms": (i + 1) * duration_ms - pad,
             "text": hypothetical_reasoning(feature)}
            for i, feature in enumerate(features)]


def make_annotation(extract, title="Native Fusion validation", duration_ms=4000):
    """One exact-indexed step per timeline item, preserving all feature order."""
    check_extract(extract)
    if not isinstance(duration_ms, int) or duration_ms < 500:
        raise ValueError("duration_ms must be an integer >= 500")
    features = sorted(extract["features"], key=lambda item: item["index"])
    steps = []
    for ordinal, feature in enumerate(features):
        start = ordinal * duration_ms
        steps.append({
            "id": "feature-%04d" % ordinal,
            "title": feature["name"],
            "features": [feature["index"]],  # exact ID, even with duplicate names
            "recording": {"start_ms": start, "end_ms": start + duration_ms},
        })
    return {
        "format": "excadmple-annotation",
        "version": 1,
        "id": "native-fusion-validation",
        "title": title,
        "description": "Timeline validation only; no recorded narration or mouse movements.",
        "steps": steps,
    }


def native_only_manifest(extract, source, title, synthetic_reasoning=False):
    """Native real-model test: no snapshots, only genuine timeline references.

    Its replay MUST come from the embedded .f3d and Fusion's native
    parameter/timeline engine. No precomputed meshes are packaged.
    """
    check_extract(extract)
    features = sorted(extract["features"], key=lambda item: item["index"])
    if len(features) > MAX_STEPS:
        raise ValueError("Native validation has {} timeline items, but packages "
                         "support at most {}; do not silently truncate."
                         .format(len(features), MAX_STEPS))
    steps = []
    for i, feature in enumerate(features):
        kind = str(feature.get("kind") or "Feature")
        label = LABELS.get(kind, kind.removesuffix("Feature"))
        steps.append({
            "id": "feature-%04d" % i,
            "title": feature["name"],
            "duration_ms": 4000,      # synthetic test duration, NOT authoring time
            "tools": [label],
            "source_features": [{
                "index": feature["index"], "name": feature["name"], "kind": kind
            }],
            "geometry": {"meshes": []},   # never substitute snapshots for native HiM
            "cues": ([{"at_ms": 250, "label": hypothetical_reasoning(feature)}]
                     if synthetic_reasoning else []),
            "media": {},
        })
    manifest = {
        "format": "excadmple", "version": 2,
        "id": "native-fusion-validation",
        "title": title,
        "description": (
            "SIMULATED teaching hypotheses; NOT original designer think-aloud."
            if synthetic_reasoning else "Native feature history only; no recording."),
        "source_model": "source/" + source.name,
        "steps": steps,
    }
    validate_package(manifest)
    return manifest


def make_package(extract, source, output, title="Native Fusion validation",
                 synthetic_reasoning=False, native_only=False):
    source = Path(source)
    output = Path(output)
    if source.suffix.lower() != ".f3d" or not source.is_file():
        raise ValueError("Provide the existing original .f3d file")
    if output.suffix.lower() != ".excadmple":
        raise ValueError("Output must be an .excadmple file")
    if source.resolve() == output.resolve():
        raise ValueError("Never overwrite the source model")
    if native_only:
        manifest = native_only_manifest(extract, source, title, synthetic_reasoning)
        step_count = len(manifest["steps"])
    else:
        annotation = make_annotation(extract, title)
        segments = synthetic_reasoning_segments(extract) if synthetic_reasoning else []
        manifest = build_manifest(extract, annotation, segments, source_model=str(source))
        if synthetic_reasoning:
            manifest["description"] = (
                "SIMULATED, hypothesis-only explanations based on extracted feature "
                "kinds, parameters, and dependencies; NOT the original designer's words.")
        step_count = len(annotation["steps"])
    output.parent.mkdir(parents=True, exist_ok=True)
    write_package(manifest, output, (), str(source))
    return output, step_count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("extract", help="Timeline JSON exported inside Fusion Desktop")
    parser.add_argument("source", help="Original .f3d archive; embedded as a read-only reference")
    parser.add_argument("-o", "--output", required=True, help="Output .excadmple test package")
    parser.add_argument("--title", default="Native Fusion validation")
    parser.add_argument("--native-only", action="store_true",
                        help="Omit mesh snapshots; animate only original Fusion Feature Timeline")
    parser.add_argument("--synthetic-reasoning", action="store_true",
                        help="Attach explicitly hypothetical explanations to every feature (testing only)")
    args = parser.parse_args(argv)
    try:
        draft = json.loads(Path(args.extract).read_text(encoding="utf-8"))
        output, steps = make_package(draft, args.source, args.output, args.title,
                                           synthetic_reasoning=args.synthetic_reasoning,
                                           native_only=args.native_only)
    except (OSError, ValueError) as exc:
        parser.exit(1, "error: %s\n" % exc)
    print("Wrote %s with %d exact-indexed timeline steps and the original .f3d." % (output, steps))
    if args.synthetic_reasoning:
        print("Added hypothetical reasoning cues, labeled NOT the designer\'s words.")
    else:
        print("No recorded think-aloud, pointers or per-tool timestamps were generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
