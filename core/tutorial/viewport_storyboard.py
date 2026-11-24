"""Convert source CAD steps into visual, in-viewport HOW demonstrations.

This pure-Python planner has no Fusion dependency. It NEVER guesses the actual
author's clicks from an .f3d: without operation footage its phases are marked
"reconstructed" and use the live HiM geometry as the visual demonstration.
With authored screen-video cuts, the exact original CAD interaction plays in
the floating viewport overlay.

Playback controls remain in the separate right-hand panel.
"""
import math

PHASES = ("tool", "how", "geometry", "why")

HOW = {
    "sketch": "Start a sketch, choose Line or Rectangle, place successive points, close and constrain the profile.",
    "line": "Pick the first point, drag to the next point and click; repeat for connected segments.",
    "extrude": "Select a profile, choose an extrusion direction and enter the distance.",
    "fillet": "Select the correct edges, set the radius and confirm the preview.",
    "chamfer": "Select the intended edges, set the chamfer distance and confirm.",
    "revolve": "Select the profile and axis, set the rotation angle and confirm.",
    "pattern": "Select the source feature, direction, count and spacing.",
    "hole": "Select the hole center and configure type, depth and diameter.",
    "mirror": "Select the geometry and the mirror plane.",
    "move": "Select the object, manipulate it, and confirm placement.",
    "combine": "Choose target and tool bodies, then set the Boolean operation.",
    "shell": "Choose the openings, then set the wall thickness.",
    "sweep": "Select a profile and a path; adjust the operation options.",
}


def _finite(value, minimum=0):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= minimum)


def _kind(step):
    kinds = [str(x.get("kind", "")).lower()
             for x in step.get("source_features", []) if isinstance(x, dict)]
    if kinds:
        return kinds[-1]
    tools = [str(x).lower() for x in step.get("tools", [])]
    return tools[-1] if tools else ""


def _verb(step):
    kind = _kind(step)
    for token, description in HOW.items():
        if token in kind:
            return description
    return "Inspect the source inputs, use the matching CAD tool and confirm its parameters."


def _reason(step, elapsed):
    if step.get("reasoning_source") in ("simulated", "hypothetical"):
        return ""
    cues = step.get("cues", [])
    if not isinstance(cues, list):
        return ""
    matching = [str(c.get("label", "")).strip() for c in cues
                if isinstance(c, dict) and _finite(c.get("at_ms"))
                and c["at_ms"] <= elapsed and str(c.get("label", "")).strip()]
    return matching[-1][:320] if matching else ""


def _params(step):
    values = []
    for item in step.get("parameters", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("label") or "").strip()
        value = str(item.get("expression") or item.get("value") or "").strip()
        if name or value:
            values.append((name + "  " + value).strip()[:95])
    return values[:5]


def storyboard(step):
    """Return time-ordered presentation moments with stable stage identities."""
    duration = max(500, int(step.get("duration_ms", 8000)))
    authored = step.get("walkthrough") or []
    if authored:
        result = []
        for i, m in enumerate(authored[:32]):
            if not isinstance(m, dict):
                continue
            phase = str(m.get("kind") or "how")
            if phase not in PHASES:
                continue
            at = m.get("at_ms", 0)
            if not _finite(at) or at > duration:
                continue
            result.append({
                "phase": phase, "at_ms": int(at),
                "title": str(m.get("title") or phase.title())[:100],
                "hint": str(m.get("description") or "")[:320],
                "source": "authored",
                "video_start_ms": m.get("video_start_ms"),
                "video_end_ms": m.get("video_end_ms"),
                "video_focus": m.get("video_focus"),
                "operation": str(m.get("tool") or "")[:100],
            })
        if result:
            return sorted(result, key=lambda e: e["at_ms"])
    tools = [str(t) for t in step.get("tools", []) if t]
    title = tools[-1] if tools else (_kind(step).replace("feature", "").title() or "CAD Tool")
    stages = [
        {"phase":"tool","at_ms":0,
         "title":"Use " + title,
         "hint":"Find the native Fusion tool used in this modeling step."},
        {"phase":"how","at_ms":int(duration*.20),
         "title":"Watch the operation",
         "hint":_verb(step)},
        {"phase":"geometry","at_ms":int(duration*.73),
         "title":"Look at the affected geometry",
         "hint":"Follow the blue input highlights and the evolving reference geometry in this viewport."},
    ]
    if step.get("cues") and step.get("reasoning_source") not in ("simulated","hypothetical"):
        stages.append({"phase":"why","at_ms":int(duration*.87),
                       "title":"Design reasoning",
                       "hint":"Listen to the author's explanation at this decision."})
    for stage in stages:
        stage.update(source="reconstructed",video_start_ms=None,
                     video_end_ms=None,video_focus=None,operation=title)
    return stages


def frame(step, index, elapsed, playing, tool_descriptions=None):
    """Small, JSON-serializable viewport payload; the right panel never renders it."""
    duration=max(500,int(step.get("duration_ms",8000)))
    elapsed=max(0,min(float(elapsed),duration)) if _finite(elapsed) else 0.
    scenes=storyboard(step)
    chosen=0
    for i,m in enumerate(scenes):
        if elapsed >= m["at_ms"]:
            chosen=i
    moment=scenes[chosen]
    tool_descriptions=tool_descriptions or []
    actual=next((t for t in tool_descriptions if t.get("found")),None)
    if actual is None and tool_descriptions:
        actual=tool_descriptions[0]
    actual=actual or {}
    source_tools=[str(v) for v in step.get("tools",[]) if v]
    label=moment.get("operation") or actual.get("label") or (source_tools[-1] if source_tools else "CAD tool")
    media=step.get("media") or {}
    video=str(media.get("video",""))
    # A clip's offset is in the ORIGINAL uncut recording. Subclips can
    # address their own local intervals within that source recording.
    base=media.get("video_offset_ms",0)
    base=base if _finite(base) else 0
    relative_start=moment.get("video_start_ms")
    relative_end=moment.get("video_end_ms")
    if not _finite(relative_start):
        relative_start=0
    if not _finite(relative_end):
        next_at=scenes[chosen+1]["at_ms"] if chosen+1<len(scenes) else duration
        relative_end=max(relative_start+50,next_at-moment["at_ms"])
    video_length=media.get("video_duration_ms")
    if _finite(video_length,1):
        relative_start=min(relative_start,video_length)
        relative_end=min(relative_end,video_length)
    return {
        "format":"excadmple.viewport.walkthrough.v1",
        "index":int(index),
        "step_id":str(step.get("id","")),
        "step_title":str(step.get("title",""))[:120],
        "elapsed_ms":elapsed, "duration_ms":duration, "playing":bool(playing),
        "moment":chosen, "count":len(scenes), "phase":moment["phase"],
        "title":moment["title"], "hint":moment["hint"],
        "source":moment["source"],
        "tool":label,
        "tool_path":actual.get("path") or [],
        "tool_found":bool(actual.get("found")),
        "tool_icon":actual.get("icon") or "",
        "parameters":_params(step),
        "reason":_reason(step,elapsed) if moment["phase"]=="why" else "",
        "video":video,
        "video_offset_ms":base,
        "video_start_ms":relative_start,
        "video_end_ms":relative_end,
        "moment_start_ms":moment["at_ms"],
        "video_focus":moment.get("video_focus") or media.get("video_focus") or {},
        "has_operation_footage":bool(video),
        "camera_moves_only_when_opted_in":True,
    }
