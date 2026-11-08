"""Tutorial for the Fusion Desktop validation model (tools/fusion_demo).

Pure Python: turns the extract of the demo model into annotation.json and a
transcript, so the package can be assembled with core.authoring. The
narration is written for this test, NOT a recorded think-aloud, and the
package carries no pointer data: nothing was recorded.

Timeline of the demo model: Sketch, Extrude (distance), Fillet (radius),
Sketch on the top face, Extrude (join, distance), Construction plane,
Mirror (no parameter -> visual fallback).
"""
SKETCH_KINDS = ("Sketch", "ConstructionPlane", "ConstructionAxis", "ConstructionPoint")

STEPS = [
    ("base", "Block out the base", 0, 18000,
     "I start with a rectangle on the ground plane and pull it up one centimetre."),
    ("round", "Round the vertical corners", 18000, 30000,
     "The corners are sharp, so I round the four vertical edges."),
    ("post", "Add a post on top", 30000, 46000,
     "On the top face I sketch a circle and extrude it as a post, joined to the base."),
    ("mirror", "Mirror the post", 46000, 60000,
     "I want the same post on the other side, so I mirror it across the middle plane."),
]
NOTE = "Illustrative narration written for the validation model; not a recorded think-aloud."


def groups(extract):
    """Timeline items grouped as: sketches/planes + the feature made from them."""
    out, pending = [], []
    for f in sorted(extract["features"], key=lambda f: f["index"]):
        if f.get("suppressed"):
            continue
        pending.append(f)
        if f.get("kind", "") not in SKETCH_KINDS:
            out.append(pending)
            pending = []
    if pending and out:
        out[-1].extend(pending)
    return out


def annotation_and_transcript(extract):
    found = groups(extract)
    kinds = [[f["kind"] for f in g if f["kind"] not in SKETCH_KINDS] for g in found]
    expected = [["ExtrudeFeature"], ["FilletFeature"], ["ExtrudeFeature"], ["MirrorFeature"]]
    if kinds != expected:
        raise ValueError("Unexpected demo timeline: %r" % kinds)
    steps, segments = [], []
    for (step_id, title, start, end, said), group in zip(STEPS, found):
        steps.append({"id": step_id, "title": title,
                      "features": [f["index"] for f in group],
                      "recording": {"start_ms": start, "end_ms": end}})
        segments.append({"start_ms": start + 1000, "end_ms": start + 6000, "text": said})
    annotation = {"format": "excadmple-annotation", "version": 1,
                  "id": "him-validation", "title": "HiM validation part",
                  "description": NOTE, "steps": steps}
    return annotation, segments
