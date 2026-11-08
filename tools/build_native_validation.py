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
from core.authoring import build_manifest, check_extract, write_package  # noqa: E402


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


def make_package(extract, source, output, title="Native Fusion validation"):
    source = Path(source)
    output = Path(output)
    if source.suffix.lower() != ".f3d" or not source.is_file():
        raise ValueError("Provide the existing original .f3d file")
    if output.suffix.lower() != ".excadmple":
        raise ValueError("Output must be an .excadmple file")
    if source.resolve() == output.resolve():
        raise ValueError("Never overwrite the source model")
    annotation = make_annotation(extract, title)
    manifest = build_manifest(extract, annotation, [], source_model=str(source))
    output.parent.mkdir(parents=True, exist_ok=True)
    write_package(manifest, output, (), str(source))
    return output, len(annotation["steps"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("extract", help="Timeline JSON exported inside Fusion Desktop")
    parser.add_argument("source", help="Original .f3d archive; embedded as a read-only reference")
    parser.add_argument("-o", "--output", required=True, help="Output .excadmple test package")
    parser.add_argument("--title", default="Native Fusion validation")
    args = parser.parse_args(argv)
    try:
        draft = json.loads(Path(args.extract).read_text(encoding="utf-8"))
        output, steps = make_package(draft, args.source, args.output, args.title)
    except (OSError, ValueError) as exc:
        parser.exit(1, "error: %s\n" % exc)
    print("Wrote %s with %d exact-indexed timeline steps and the original .f3d." % (output, steps))
    print("No recorded think-aloud, pointers or per-tool timestamps were generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
