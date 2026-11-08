"""Cut a recorded modeling session into tutorial steps (authoring tool).

Inputs: the extracted timeline (draft.extract.json), the recorder's log
(when each feature appeared, which tools were used, what was selected) and
the think-aloud transcript. Output: annotation.json for build_package.py.

Claude proposes the steps (which features belong together, where each step
starts and ends in the recording, a short title in the designer's own
words). It writes no reasoning: what the designer said reaches the tutorial
only through the transcript. The proposal is validated; if it is invalid or
no API key is available, a rule-based split is used instead. Either way the
researcher reviews the result in ui/author.html.
"""
import json
import re

from .session_log import tools_between, pointer_between

MODEL = "claude-opus-5-5"
SKETCH_KINDS = ("Sketch", "ConstructionPlane", "ConstructionAxis", "ConstructionPoint")
TAIL_MS = 1500


class SegmentError(ValueError):
    pass


def modeling_features(extract):
    """Timeline items in order (sketches included; they belong to the step
    of the feature made from them)."""
    return sorted(({"index": f["index"], "name": f["name"], "kind": f.get("kind", "")}
                   for f in extract["features"] if not f.get("suppressed")), key=lambda f: f["index"])


def feature_times(features, session):
    """Recording time (ms) at which each timeline item appeared, by index."""
    times = {}
    logged = (session or {}).get("features", [])
    for f in features:
        match = next((e for e in logged if e["name"] == f["name"] and e["index"] == f["index"]), None) \
            or next((e for e in logged if e["name"] == f["name"]), None)
        if match:
            times[f["index"]] = match["t_ms"]
    return times


def _sentences(segments, start, end):
    return [s["text"] for s in segments if start <= s["start_ms"] < end]


# --- rule-based split ---------------------------------------------------------------------
def heuristic_steps(features, session, segments, total_ms):
    """One step per modeling feature, together with the sketches before it."""
    groups, pending = [], []
    for f in features:
        pending.append(f)
        if f["kind"] not in SKETCH_KINDS:
            groups.append(pending)
            pending = []
    if pending:
        if groups:
            groups[-1].extend(pending)
        else:
            groups.append(pending)
    if not groups:
        raise SegmentError("The design has no timeline features")
    times = feature_times(features, session)
    ends = []
    for i, group in enumerate(groups):
        logged = [times[f["index"]] for f in group if f["index"] in times]
        ends.append(max(logged) + TAIL_MS if logged else None)
    steps, start = [], 0
    for i, group in enumerate(groups):
        if i == len(groups) - 1:
            end = total_ms
        elif ends[i] is not None:
            end = ends[i]
        else:
            end = int(total_ms * (i + 1) / len(groups))
        end = max(start + 500, min(end, total_ms - 500 * (len(groups) - 1 - i)))
        said = _sentences(segments, start, end)
        title = said[0] if said else " + ".join(f["name"] for f in group if f["kind"] not in SKETCH_KINDS)
        steps.append({"title": _short(title), "features": [f["name"] for f in group],
                      "start_ms": int(start), "end_ms": int(end)})
        start = end
    return steps


def _short(text, limit=60):
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


# --- Claude proposal ----------------------------------------------------------------------
SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "features": {"type": "array", "items": {"type": "string"}},
                    "start_ms": {"type": "integer"},
                    "end_ms": {"type": "integer"},
                },
                "required": ["title", "features", "start_ms", "end_ms"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["steps"],
    "additionalProperties": False,
}

SYSTEM = """You help a researcher turn a recorded CAD modeling session into a step-by-step tutorial.
A designer modeled a part in Autodesk Fusion while thinking aloud. You get the design's timeline
(features in order), the time in the recording when each feature appeared, the tools the designer
used, and the timestamped transcript of what they said.

Cut the recording into steps:
- A step is one coherent modeling action the designer carried out and talked about, usually a
  sketch plus the feature made from it, or a few closely related features.
- Use every timeline feature exactly once, keep timeline order, and do not split a sketch from
  the feature built on it.
- start_ms/end_ms bracket what the designer said and did for that step. Steps follow each other
  without overlap, the first starts at 0 and the last ends at the end of the recording.
- The title is a short phrase (at most 8 words) in the language of the transcript, taken from
  the designer's own words where possible. Do not add explanations, reasons or anything the
  designer did not say."""


def build_prompt(features, session, segments, total_ms):
    times = feature_times(features, session)
    lines = ["Recording length: %d ms" % total_ms, "", "Timeline features (in order):"]
    for f in features:
        t = times.get(f["index"])
        lines.append("- %s (%s)%s" % (f["name"], f["kind"], "" if t is None else " appeared at %d ms" % t))
    commands = (session or {}).get("commands", [])
    if commands:
        lines += ["", "Tools used:"] + ["- %d ms %s" % (c["t_ms"], c["name"]) for c in commands[:600]]
    lines += ["", "Transcript:"] + ["- %d-%d ms: %s" % (s["start_ms"], s.get("end_ms", s["start_ms"]), s["text"])
                                     for s in segments]
    return "\n".join(lines)


def validate_steps(steps, features, total_ms):
    """Check a proposal; returns cleaned steps or raises SegmentError."""
    if not isinstance(steps, list) or not steps:
        raise SegmentError("No steps proposed")
    names = [f["name"] for f in features]
    used, last_end, last_pos = [], 0, -1
    cleaned = []
    for i, step in enumerate(steps):
        title = str(step.get("title", "")).strip()
        if not title:
            raise SegmentError("Step %d has no title" % (i + 1))
        group = step.get("features") or []
        if not group:
            raise SegmentError("Step %d has no features" % (i + 1))
        for name in group:
            if name not in names:
                raise SegmentError("Unknown feature %r" % name)
            if name in used:
                raise SegmentError("Feature %r is used twice" % name)
            pos = names.index(name)
            if pos <= last_pos:
                raise SegmentError("Features are out of timeline order at %r" % name)
            last_pos = pos
            used.append(name)
        start, end = int(step.get("start_ms", -1)), int(step.get("end_ms", -1))
        if start < last_end or end <= start or end > total_ms:
            raise SegmentError("Step %d has an invalid time range" % (i + 1))
        cleaned.append({"title": _short(title), "features": list(group), "start_ms": start, "end_ms": end})
        last_end = end
    missing = [n for n in names if n not in used]
    if missing:
        raise SegmentError("Features not assigned to a step: " + ", ".join(missing))
    return cleaned


def propose_with_claude(client, features, session, segments, total_ms):
    """Ask Claude for a segmentation (structured output); validated by the caller."""
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(features, session, segments, total_ms)}],
    )
    if response.stop_reason == "refusal":
        raise SegmentError("Claude declined the request")
    if response.stop_reason == "max_tokens":
        raise SegmentError("Claude's answer was cut off")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)["steps"]
    except (ValueError, KeyError) as error:
        raise SegmentError("Claude returned no usable steps") from error


# --- annotation ---------------------------------------------------------------------------
def to_annotation(steps, meta, session, offset_ms=0):
    """Steps -> annotation.json, adding the tools used and the designer's
    selections (as the pointer) from the recorder's log."""
    out = []
    for i, step in enumerate(steps):
        item = {"id": "step-%02d" % (i + 1), "title": step["title"], "features": step["features"],
                "recording": {"start_ms": step["start_ms"], "end_ms": step["end_ms"]}}
        if session:
            tools = tools_between(session, step["start_ms"] - offset_ms, step["end_ms"] - offset_ms)
            if tools:
                item["tools"] = tools
            pointer = pointer_between(session, step["start_ms"], step["end_ms"], offset_ms)
            if pointer:
                item["pointer"] = pointer
        out.append(item)
    annotation = {"format": "excadmple-annotation", "version": 1,
                  "id": meta["id"], "title": meta["title"], "steps": out}
    recording = {k: meta[k] for k in ("video", "audio") if meta.get(k)}
    if recording:
        annotation["recording"] = recording
    return annotation
