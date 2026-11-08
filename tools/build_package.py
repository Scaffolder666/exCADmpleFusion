"""Assemble an .excadmple package (version 2) from the three source files.

    python tools/build_package.py draft.extract.json annotation.json transcript.srt \
        --media session.m4a --media session.mp4 -o phone-stand.excadmple

See docs/EXAMPLE_FORMAT.md.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.authoring import build_manifest, write_package, AuthoringError  # noqa: E402
from core import transcript  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("extract", help="draft exported by 'Extract example draft' in Fusion")
    parser.add_argument("annotation", help="researcher's annotation.json")
    parser.add_argument("transcript", help="think-aloud transcript (.srt, .vtt or .json)")
    parser.add_argument("--media", action="append", default=[], help="recording file referenced by the annotation")
    parser.add_argument("-o", "--output", required=True, help="output .excadmple (or .json for no media)")
    args = parser.parse_args(argv)
    try:
        extract = json.loads(Path(args.extract).read_text(encoding="utf-8"))
        annotation = json.loads(Path(args.annotation).read_text(encoding="utf-8"))
        manifest = build_manifest(extract, annotation, transcript.load(args.transcript))
        out = Path(args.output)
        if out.suffix.lower() == ".json":
            out.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        else:
            write_package(manifest, out, args.media)
    except (AuthoringError, transcript.TranscriptError, ValueError, OSError) as error:
        print("error:", error, file=sys.stderr)
        return 1
    steps = manifest["steps"]
    print("wrote %s: %d steps, %d features, %d transcript cues" % (
        out, len(steps), sum(len(s["source_features"]) for s in steps), sum(len(s["cues"]) for s in steps)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
