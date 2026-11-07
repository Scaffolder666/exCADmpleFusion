"""Pure, Blender-independent playback data model. No claims about CAD history."""
import json
import math
from pathlib import Path

class ExampleError(ValueError): pass

SHOWCASE_OPERATIONS = (
    "extrude", "revolve", "fillet", "chamfer", "circular_pattern",
    "rectangular_pattern", "mirror", "copy", "move", "scale", "combine",
    "split", "import", "export", "shell", "draft", "sweep", "loft",
    "thread", "hole"
)

def load_example(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    validate_example(data)
    return data

def validate_example(data):
    if not isinstance(data,dict) or data.get("format")!="excadmple-blender-v1":
        raise ExampleError("Incorrect demo data format")
    preset=data.get("geometry_preset")
    if preset not in ("phone_stand_v1", "him_feature_showcase_v1"):
        raise ExampleError("Unknown reference-animation geometry preset")
    steps=data.get("steps")
    if not isinstance(steps,list) or not 1<=len(steps)<=100:
        raise ExampleError("Expected 1–100 steps")
    prev_end=0
    for step in steps:
        if not isinstance(step.get("id"),str) or not isinstance(step.get("tool"),str):
            raise ExampleError("Each step needs a string ID and tool")
        start,end=step.get("start"),step.get("end")
        if not isinstance(start,int) or not isinstance(end,int) or start<=prev_end or end<=start:
            raise ExampleError("Steps must be ordered, distinct, non-overlapping frame intervals")
        prev_end=end
        points=step.get("pointer",[])
        if not isinstance(points,list) or not 2<=len(points)<=100:
            raise ExampleError("Each step needs 2–100 cursor samples")
        prev_t=-1
        for p in points:
            if not isinstance(p,dict): raise ExampleError("Invalid pointer sample")
            vals=[p.get("at"),p.get("x"),p.get("y")]
            if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in vals):
                raise ExampleError("Pointer coordinates/time must be finite numbers")
            t,x,y=vals
            if t<prev_t or not 0<=t<=end-start or not(0<=x<=1 and 0<=y<=1):
                raise ExampleError("Pointer path outside step")
            prev_t=t
        if preset == "him_feature_showcase_v1":
            feature=step.get("operation")
            if not isinstance(feature,dict) or feature.get("type") not in SHOWCASE_OPERATIONS:
                raise ExampleError("Each showcase step requires a supported operation type")
            if feature["type"] == "extrude" and not step.get("animation"):
                raise ExampleError("Extrude showcase steps require an explicit profile")
        if step.get("animation") is not None:
            validate_extrude_animation(step["animation"])
        for cue in step.get("captions",[]):
            if not isinstance(cue.get("at"),(int,float)) or not 0<=cue["at"]<=end-start:
                raise ExampleError("Caption time outside step")
            if not isinstance(cue.get("text"),str):
                raise ExampleError("Caption text required")
    return data


def validate_extrude_animation(animation):
    """Check explicit profile and parameter data before extrusion replay."""
    if not isinstance(animation, dict) or animation.get("type") != "extrude":
        raise ExampleError("Only explicit extrude previews are supported in the HiM-style spike")
    profile = animation.get("profile_xy")
    origin = animation.get("origin_xyz")
    distance = animation.get("distance")
    if not isinstance(profile, list) or not 3 <= len(profile) <= 64:
        raise ExampleError("Extrude requires a polygon with 3–64 vertices")
    if not isinstance(origin, list) or len(origin) != 3:
        raise ExampleError("Extrude needs a 3D origin")
    for item in profile + [origin]:
        if not isinstance(item, list) or any(
            not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)
            for v in item
        ):
            raise ExampleError("Nonfinite or nonnumeric extrusion coordinate")
    if any(len(item) != 2 for item in profile):
        raise ExampleError("Each profile point must be [x,y]")
    if isinstance(distance, bool) or not isinstance(distance, (int,float)) or not math.isfinite(distance) or not 0.001 <= distance <= 100:
        raise ExampleError("Extrude distance must be positive and finite")
    area2 = sum(
        profile[i][0] * profile[(i + 1) % len(profile)][1] -
        profile[(i + 1) % len(profile)][0] * profile[i][1]
        for i in range(len(profile))
    )
    if abs(area2) < 1e-8:
        raise ExampleError("Extrude polygon must have nonzero area")
    return animation

def operation_phase(step, frame):
    """Narrative replay phases, not recovered native Blender UI events."""
    anim = step.get("animation") or {}
    if anim.get("type") != "extrude":
        return step.get("tool", "TRANSFORM")
    t = progress_in_step(step, frame)
    if t < .17: return "SKETCH PROFILE"
    if t < .31: return "EXTRUDE TOOL"
    return "DRAG EXTRUDE HANDLE"

def step_at_frame(data,frame):
    for step in data["steps"]:
        if step["start"]<=frame<=step["end"]:
            return step
    return data["steps"][0] if frame<data["steps"][0]["start"] else data["steps"][-1]

def caption_at_frame(step,frame):
    t=max(0,frame-step["start"])
    text=step.get("reasoning","")
    for cue in step.get("captions",[]):
        if cue["at"]<=t: text=cue["text"]
        else: break
    return text

def pointer_at_frame(step,frame):
    t=max(0,frame-step["start"])
    points=step["pointer"]
    if t<=points[0]["at"]: return points[0]["x"],points[0]["y"]
    for a,b in zip(points,points[1:]):
        if a["at"]<=t<=b["at"]:
            f=(t-a["at"])/max(0.000001,b["at"]-a["at"])
            return a["x"]+(b["x"]-a["x"])*f, a["y"]+(b["y"]-a["y"])*f
    return points[-1]["x"],points[-1]["y"]

def progress_in_step(step,frame):
    return max(0.0,min(1.0,(frame-step["start"])/(step["end"]-step["start"])))
