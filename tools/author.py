"""Authoring tool: cut a recorded think-aloud session into tutorial steps.

    python tools/author.py draft.extract.json transcript.srt \
        --session tutorial.session.json --video session.mp4 \
        --id phone-stand --title "Phone Stand" -o annotation.json

Claude (claude-opus-5-5) proposes the steps: which timeline features belong
together, where each step starts and ends in the recording, and a short
title in the designer's own words. It writes no reasoning. The proposal is
validated; with --no-ai, without an API key, or if the proposal is invalid,
a rule-based split is used. Review the result in ui/author.html, then run
tools/build_package.py.

Needs `pip install anthropic` and credentials (ANTHROPIC_API_KEY, or an
`ant auth login` profile) for the AI proposal.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import ai_segment, session_log, transcript  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("extract", help="draft exported by 'Extract tutorial draft' in Fusion")
    parser.add_argument("transcript", help="think-aloud transcript (.srt, .vtt or .json)")
    parser.add_argument("--session", help="recorder log (exCADmple: Record tutorial)")
    parser.add_argument("--video", help="screen recording file name")
    parser.add_argument("--audio", help="separate audio file name")
    parser.add_argument("--id", required=True, help="tutorial id, e.g. phone-stand")
    parser.add_argument("--title", required=True, help="tutorial title")
    parser.add_argument("--offset-ms", type=int, default=0,
                        help="recording time when the recorder log started (default 0)")
    parser.add_argument("--no-ai", action="store_true", help="use the rule-based split only")
    parser.add_argument("-o", "--output", default="annotation.json")
    args = parser.parse_args(argv)

    extract = json.loads(Path(args.extract).read_text(encoding="utf-8"))
    segments = transcript.load(args.transcript)
    session = session_log.load(args.session) if args.session else None
    features = ai_segment.modeling_features(extract)
    total = max([s.get("end_ms", s["start_ms"]) for s in segments] +
                [(session or {}).get("duration_ms", 0) + args.offset_ms, 1000])

    steps, how = None, "rule-based split"
    if not args.no_ai:
        try:
            import anthropic
            client = anthropic.Anthropic()
            proposal = ai_segment.propose_with_claude(client, features, session, segments, total)
            steps = ai_segment.validate_steps(proposal, features, total)
            how = "Claude's proposal"
        except ImportError:
            print("note: `pip install anthropic` to get an AI proposal; using the rule-based split")
        except ai_segment.SegmentError as error:
            print("note: AI proposal not usable (%s); using the rule-based split" % error)
        except Exception as error:     # network, credentials, API errors
            if "authentication" in str(error).lower():
                print("note: no Claude credentials (set ANTHROPIC_API_KEY or run `ant auth login`); "
                      "using the rule-based split")
            else:
                print("note: AI proposal failed (%s: %s); using the rule-based split" % (type(error).__name__, error))
    if steps is None:
        steps = ai_segment.validate_steps(
            ai_segment.heuristic_steps(features, session, segments, total), features, total)

    meta = {"id": args.id, "title": args.title, "video": args.video, "audio": args.audio}
    annotation = ai_segment.to_annotation(steps, meta, session, args.offset_ms)
    Path(args.output).write_text(json.dumps(annotation, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote %s: %d steps (%s)" % (args.output, len(steps), how))
    for i, step in enumerate(annotation["steps"], 1):
        print("  %2d. %-45s %6.1fs-%6.1fs  %s" % (i, step["title"][:45], step["recording"]["start_ms"] / 1000,
                                                 step["recording"]["end_ms"] / 1000, ", ".join(step["features"])))
    print("Review it in ui/author.html, then: python tools/build_package.py %s %s %s -o %s.excadmple"
          % (args.extract, args.output, args.transcript, args.id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
