#!/usr/bin/env python3
"""Attach *cuts* from one real CAD screen recording to exCADmple HiM steps.

No re-encoding needed: the player seeks into the original movie. The user can
supply the timestamp of each feature operation; tool/how/geometry/why moments
inside the step further cut out the relevant subrange.

Command:
  python tools/walkthrough/attach_clips.py \
    --tutorial /path/model.json --recording /path/session.mp4 \
    --cuts /path/cuts.json

Writes sibling model.walkthrough.json. Neither the input tutorial nor video
is modified. Supported tutorials: excadmple v2, excadmple-pair v1.
"""
import argparse
import json
from pathlib import Path


class CutError(ValueError):
    pass


def _nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1000000000:
        raise CutError(name + " must be a non-negative number in milliseconds")
    return value


def attach(tutorial, recording, cuts, output):
    tutorial, recording, cuts, output = [Path(p).expanduser().resolve()
                                        for p in (tutorial, recording, cuts, output)]
    if not (tutorial.is_file() and recording.is_file() and cuts.is_file()):
        raise CutError("Tutorial, recording, and cut list must exist")
    if recording.parent != output.parent or tutorial.parent != output.parent:
        raise CutError("Put tutorial, recording and output in the SAME directory for safe relative media paths")
    if output == tutorial:
        raise CutError("Output cannot overwrite the original tutorial")
    if recording.suffix.lower() not in (".mp4", ".webm", ".mov"):
        raise CutError("Use a browser-playable MP4/WebM/MOV recording")
    data = json.loads(tutorial.read_text(encoding="utf-8"))
    if data.get("format") not in ("excadmple", "excadmple-pair"):
        raise CutError("Expected excadmple or excadmple-pair tutorial JSON")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise CutError("Tutorial needs authored steps")
    config = json.loads(cuts.read_text(encoding="utf-8"))
    matches = config.get("cuts")
    if not isinstance(matches, list):
        raise CutError("cuts.json must have an array called cuts")
    ids = {s.get("id", "step-" + str(i+1)): s for i,s in enumerate(steps)}
    used = set()
    for cut in matches:
        if not isinstance(cut, dict):
            raise CutError("Each cut must be an object")
        sid = cut.get("step_id")
        if sid not in ids:
            raise CutError("No step id " + repr(sid))
        if sid in used:
            raise CutError("Duplicate cut for " + repr(sid))
        used.add(sid)
        start = _nonnegative(cut.get("video_offset_ms"), "video_offset_ms")
        end = _nonnegative(cut.get("video_end_ms"), "video_end_ms")
        if end <= start:
            raise CutError("End must follow start for " + sid)
        step = ids[sid]
        duration = _nonnegative(step.get("duration_ms", 8000), "step duration")
        moments = cut.get("walkthrough")
        if moments is not None:
            if not isinstance(moments, list) or not moments:
                raise CutError("walkthrough must be a nonempty list")
            for m in moments:
                at = _nonnegative(m.get("at_ms"), "moment.at_ms")
                if at > duration:
                    raise CutError("Moment exceeds step duration")
                for key in ("video_start_ms", "video_end_ms"):
                    if key in m and _nonnegative(m[key], key) > end - start:
                        raise CutError(key + " exceeds the source video segment")
            step["walkthrough"] = moments
        focus = cut.get("video_focus")
        if data["format"] == "excadmple-pair":
            step["video"] = recording.name
            step["video_offset_ms"] = start
            step["video_duration_ms"] = end - start
            if focus is not None:
                step["video_focus"] = focus
        else:
            step.setdefault("media", {})
            step["media"]["video"] = recording.name
            step["media"]["video_offset_ms"] = start
            step["media"]["video_duration_ms"] = end - start
            if focus is not None:
                step["media"]["video_focus"] = focus
    if data["format"] == "excadmple":
        # Validate all asset-relative links, clip metadata and authored moments.
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from core.tutorial.packages import _validate
        _validate(data)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    return len(used), output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tutorial",type=Path,required=True)
    p.add_argument("--recording",type=Path,required=True)
    p.add_argument("--cuts",type=Path,required=True)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    dst=args.output or args.tutorial.with_name(args.tutorial.stem+".walkthrough.json")
    count,path=attach(args.tutorial,args.recording,args.cuts,dst)
    print("Added operation video cuts for",count,"steps:",path)


if __name__=="__main__":
    main()
