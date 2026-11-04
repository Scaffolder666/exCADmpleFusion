"""Pure, Blender-independent playback data model. No claims about CAD history."""
import json
import math
from pathlib import Path

class ExampleError(ValueError): pass

def load_example(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    validate_example(data)
    return data

def validate_example(data):
    if not isinstance(data,dict) or data.get("format")!="excadmple-blender-v1":
        raise ExampleError("Incorrect demo data format")
    if data.get("geometry_preset")!="phone_stand_v1":
        raise ExampleError("This spike supports the illustrative phone_stand_v1 preset only")
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
        for cue in step.get("captions",[]):
            if not isinstance(cue.get("at"),(int,float)) or not 0<=cue["at"]<=end-start:
                raise ExampleError("Caption time outside step")
            if not isinstance(cue.get("text"),str):
                raise ExampleError("Caption text required")
    return data

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
