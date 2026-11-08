"""Generate the bundled illustrative design examples (cm, Fusion units).

    python tools/build_examples.py

Writes examples/phone_stand.json (nine steps, ported from the Blender
branch's demo.json) and examples/tablet_stand.json (a contrasting example
whose decisions share topics with the phone stand, so reasoning can be
compared across examples). Geometry, ghost-pointer paths and reasoning are
authored by hand; they are NOT recorded from a real designer's session.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.animation import (extrude_mesh, operation_meshes, rectangular_pattern_meshes,  # noqa: E402
                            transition_meshes)

R = 5  # coordinate rounding


def rnd(points):
    return [[round(c, R) for c in p] for p in points]


def box(x0, x1, y0, y1, z0, z1):
    v = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
         [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]
    t = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
         [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]
    return {"vertices": rnd(v), "triangles": t}


def prism_x(x0, x1, yz):
    """Prism along X with a convex YZ polygon cross-section."""
    n = len(yz)
    v = [[x0, y, z] for y, z in yz] + [[x1, y, z] for y, z in yz]
    t = [[0, i + 1, i] for i in range(1, n - 1)] + [[n, n + i, n + i + 1] for i in range(1, n - 1)]
    for i in range(n):
        j = (i + 1) % n
        t += [[i, j, n + j], [i, n + j, n + i]]
    return {"vertices": rnd(v), "triangles": t}


def rounded_slab(x0, x1, y0, y1, z0, z1, radius, segments=6):
    """Slab with rounded vertical corners; same topology for any radius."""
    r = max(radius, 1e-4)
    corners = [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]
    ring = []
    for cx, cy, start in corners:
        for k in range(segments + 1):
            a = math.radians(start + 90 * k / segments)
            ring.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    n = len(ring)
    v = [[x, y, z0] for x, y in ring] + [[x, y, z1] for x, y in ring]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    v += [[cx, cy, z0], [cx, cy, z1]]
    b, top = 2 * n, 2 * n + 1
    t = []
    for i in range(n):
        j = (i + 1) % n
        t += [[b, j, i], [top, n + i, n + j], [i, j, n + j], [i, n + j, n + i]]
    return {"vertices": rnd(v), "triangles": t}


def rotate_mesh(mesh, degrees, origin=(0, 3.0, 0.7)):
    """Tilt about the X axis through the back-panel hinge (same math as revolve)."""
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    out = []
    for x, y, z in mesh["vertices"]:
        dy, dz = y - origin[1], z - origin[2]
        out.append([x, origin[1] + dy * c - dz * s, origin[2] + dy * s + dz * c])
    return {"vertices": rnd(out), "triangles": mesh["triangles"]}


def panel_part(x0, x1, u0, u1, w0=0.0, w1=0.6, tilt=-25.0, hinge=(3.0, 0.7)):
    """Box in back-panel coordinates: u along the panel, w through it."""
    return rotate_mesh(box(x0, x1, hinge[0] + w0, hinge[0] + w1, hinge[1] + u0, hinge[1] + u1),
                       tilt, (0, hinge[0], hinge[1]))


def snap(meshes):
    return [{"vertices": rnd(m["vertices"]), "triangles": m["triangles"]} for m in meshes]


def decision(topic, question, criteria, options, parameter=None, features=(), tags=()):
    data = {"topic": topic, "question": question, "criteria": list(criteria),
            "options": options, "applies_to": {"features": list(features), "tags": list(tags)}}
    if parameter:
        data["parameter"] = parameter
    return data


def opt(label, value=None, note="", chosen=False):
    item = {"label": label, "note": note}
    if value is not None:
        item["value"] = value
    if chosen:
        item["chosen"] = True
    return item


def step(sid, title, goal, tool, instruction, params, reasoning, cues, meshes, animation, pointer,
         dec, duration=9000):
    return {
        "id": sid, "title": title, "goal": goal, "duration_ms": duration,
        "geometry": {"meshes": snap(meshes)}, "media": {},
        "operation": {"tool": tool, "instruction": instruction,
                      "parameters": [{"name": n, "value": v} for n, v in params]},
        "reasoning": {"text": reasoning, "source": "mockup"},
        "cues": [{"at_ms": at, "label": text} for at, text in cues],
        "animation": animation, "pointer": pointer, "decision": dec,
    }


def ptr(*points):
    return [{"at_ms": at, "xyz": [round(c, 3) for c in xyz], "event": ev} for at, xyz, ev in points]


# ---------------------------------------------------------------------------
def phone_stand():
    steps = []
    base_box = box(0, 10, 0, 8, 0, 0.7)
    # 1 base: extrude
    anim = {"type": "extrude", "profile": [[0, 0, 0], [10, 0, 0], [10, 8, 0], [0, 8, 0]],
            "direction_cm": [0, 0, 0.7], "cap_triangles": [[0, 1, 2], [0, 2, 3]], "context_meshes": []}
    geo = [extrude_mesh(anim, 1.0)]
    steps.append(step(
        "base", "Establish the footprint", "Set a footprint that stays stable when the screen is tapped.",
        "Sketch → Extrude", "Sketch a 100 × 80 mm rectangle on the XY plane and extrude it 7 mm.",
        [("Width", "100 mm"), ("Depth", "80 mm"), ("Thickness", "7 mm")],
        "I choose a wide base first so I can evaluate stability before fixing the viewing angle. "
        "The depth matters more than the width: tapping the screen pushes the phone backwards.",
        [(0, "First, I define a broad footprint for stability."),
         (3400, "Now I extrude it, keeping the plate relatively thin."),
         (7000, "This dimension is a design choice, not a requirement.")],
        geo, anim,
        ptr((0, (-1.5, -1.0, 0), "move"), (1500, (0, 0, 0), "click"), (3000, (10, 8, 0), "drag"),
            (4200, (10, 8, 0.05), "click"), (7500, (10, 8, 0.7), "drag"), (9000, (10.6, 8.4, 0.9), "move")),
        decision("footprint", "How deep should the base be?",
                 ["Resists tipping when the screen is tapped", "Desk space", "Material and print time"],
                 [opt("Compact", "60 mm", "Small, but tips backwards when tapped."),
                  opt("Balanced", "80 mm", "Stable for phones up to ~7 inch.", True),
                  opt("Generous", "100 mm", "Very stable, takes more desk space.")],
                 {"name": "Base depth", "value": "80 mm", "kind": "length"},
                 ["ExtrudeFeature"], ["base", "foot", "plate", "footprint"])))

    # 2 support: tilt the back panel (revolve-style rotation of an upright panel)
    upright = box(0.5, 9.5, 3.0, 3.6, 0.7, 9.7)
    anim = {"type": "revolve", "new_meshes": [upright], "context_meshes": [base_box],
            "axis_origin_cm": [0, 3.0, 0.7], "axis_direction": [1, 0, 0], "angle_deg": -25}
    geo = operation_meshes(anim, 1.0)
    panel = geo[-1]
    steps.append(step(
        "support", "Choose a viewing angle", "Hold the screen at a comfortable angle.",
        "Sketch → Extrude → Rotate", "Extrude a 6 mm back panel and tilt it 25° back from vertical (65° from the desk).",
        [("Angle from desk", "65 deg"), ("Panel thickness", "6 mm")],
        "The back panel is angled for viewing, but I keep the angle as one parameter so I can change "
        "its inclination if the phone or the context changes.",
        [(0, "I introduce a back panel to carry the phone."),
         (3200, "I tilt it instead of assuming the first angle is final."),
         (6800, "The angle depends on how the stand will be used.")],
        geo, anim,
        ptr((0, (5, 2.0, 1.0), "move"), (1800, (5, 3.3, 5.0), "click"), (5000, (5, 4.6, 8.0), "drag"),
            (8000, (5, 5.6, 8.9), "drag"), (9000, (5, 5.8, 9.5), "move")),
        decision("viewing_angle", "How steep should the phone lean?",
                 ["Eye level while sitting at a desk", "Glare from overhead light", "Stability when tapped"],
                 [opt("Shallow", "55 deg", "Easy to tap, but the screen reflects ceiling lights."),
                  opt("Medium", "65 deg", "Readable from a chair; still stable when tapped.", True),
                  opt("Upright", "75 deg", "Good for video calls, tips more easily.")],
                 {"name": "Angle from desk", "value": "65 deg", "kind": "angle"},
                 ["ExtrudeFeature", "RevolveFeature", "MoveFeature"], ["back", "support", "angle", "tilt", "panel"])))

    # 3 lip: extrude a retaining lip
    lip_profile = [[0.5, 0.4, 0.7], [9.5, 0.4, 0.7], [9.5, 1.0, 0.7], [0.5, 1.0, 0.7]]
    anim = {"type": "extrude", "profile": lip_profile, "direction_cm": [0, 0, 1.0],
            "cap_triangles": [[0, 1, 2], [0, 2, 3]], "context_meshes": [base_box, panel]}
    geo = [base_box, panel, extrude_mesh(anim, 1.0)]
    steps.append(step(
        "lip", "Prevent the phone from sliding", "Stop the phone from sliding off the base.",
        "Sketch → Extrude", "Sketch a 6 mm strip near the front edge and extrude it 10 mm up.",
        [("Lip height", "10 mm"), ("Lip thickness", "6 mm")],
        "I add a shallow lip to prevent slipping while leaving room to reach the bottom of the device. "
        "Higher than about a centimeter starts covering the screen.",
        [(0, "A small lip holds the device near the lower edge."),
         (3600, "I extrude only enough to resist sliding."),
         (6700, "The phone size might call for a different lip.")],
        geo, anim,
        ptr((0, (-1.0, 0.7, 0.7), "move"), (1500, (0.5, 0.4, 0.7), "click"), (3000, (9.5, 1.0, 0.7), "drag"),
            (4500, (9.5, 1.0, 0.75), "click"), (7500, (9.5, 1.0, 1.7), "drag"), (9000, (10.2, 1.0, 1.9), "move")),
        decision("retaining_lip", "How tall should the retaining lip be?",
                 ["Holds the phone at the chosen angle", "Does not cover the screen", "Works with a phone case"],
                 [opt("Low", "5 mm", "Covers nothing, but a cased phone can slip over it."),
                  opt("Medium", "10 mm", "Holds a cased phone without covering the screen.", True),
                  opt("High", "15 mm", "Very secure, hides the bottom of the screen.")],
                 {"name": "Lip height", "value": "10 mm", "kind": "length"},
                 ["ExtrudeFeature"], ["lip", "ledge", "stop", "front"])))
    lip_box = geo[2]

    # 4 fillet the base corners: radius grows (same topology)
    anim = {"type": "fillet",
            "before_meshes": [rounded_slab(0, 10, 0, 8, 0, 0.7, 0.0), panel, lip_box],
            "after_meshes": [rounded_slab(0, 10, 0, 8, 0, 0.7, 0.8), panel, lip_box]}
    geo = transition_meshes(anim, 1.0)
    base_round = geo[0]
    steps.append(step(
        "base_round", "Round the base edges", "Make the base pleasant to handle without losing contact area.",
        "Fillet", "Select the four vertical base edges and fillet them with an 8 mm radius.",
        [("Radius", "8 mm"), ("Edges", "4")],
        "Before moving to details, I soften the sharp base corners for handling while keeping enough flat "
        "contact for stability. A large radius would eat into the footprint I chose in step 1.",
        [(0, "A wide base helps stability, but sharp corners feel unfinished."),
         (3400, "I increase the fillet radius a little at a time."),
         (6900, "Too much rounding would take away useful flat contact.")],
        geo, anim,
        ptr((0, (11, -1, 0.35), "move"), (1500, (10, 0, 0.35), "click"), (3000, (10, 8, 0.35), "click"),
            (4500, (0, 8, 0.35), "click"), (6000, (0, 0, 0.35), "click"), (8000, (0.9, 0.9, 0.35), "drag"),
            (9000, (1.2, 1.2, 0.6), "move")),
        decision("edge_rounding", "How much should the base corners be rounded?",
                 ["Comfortable to handle", "Keeps flat contact area", "Matches the product's visual language"],
                 [opt("Break the edge", "2 mm", "Just removes sharpness."),
                  opt("Soft", "8 mm", "Friendly look, contact area barely changes.", True),
                  opt("Pebble", "15 mm", "Very soft, but the footprint shrinks noticeably.")],
                 {"name": "Radius", "value": "8 mm", "kind": "length"},
                 ["FilletFeature", "ChamferFeature"], ["fillet", "round", "corner", "edge"])))

    # 5 cable passage: the lip splits open in the middle
    def lip_parts(gap):
        half = gap / 2
        return [box(0.5, 5 - half, 0.4, 1.0, 0.7, 1.7), box(5 + half, 9.5, 0.4, 1.0, 0.7, 1.7)]
    anim = {"type": "boolean", "before_meshes": [base_round, panel] + lip_parts(0.0),
            "after_meshes": [base_round, panel] + lip_parts(2.0)}
    geo = transition_meshes(anim, 1.0)
    lips = geo[2:]
    steps.append(step(
        "cable", "Leave a charging-cable passage", "Allow charging while the phone is on the stand.",
        "Sketch → Extrude (Cut)", "Sketch a 20 mm wide slot centered on the lip and cut through it.",
        [("Slot width", "20 mm"), ("Operation", "Cut")],
        "The retaining lip should not block charging. I cut a centered cable passage but keep support on "
        "both sides, so the phone still cannot slide.",
        [(0, "The phone still needs to charge while it is on the stand."),
         (3400, "I remove a small section of the front lip."),
         (6900, "Both lip segments remain to prevent sliding.")],
        geo, anim,
        ptr((0, (5, -1.5, 1.8), "move"), (2000, (4.0, 0.7, 1.7), "click"), (4000, (6.0, 0.7, 1.7), "drag"),
            (6500, (6.0, 0.7, 0.8), "drag"), (9000, (5, -0.6, 1.2), "move")),
        decision("cable_access", "How wide should the cable passage be?",
                 ["Fits common charging plugs", "Keeps enough lip on both sides", "Centered on the phone's port"],
                 [opt("Narrow", "10 mm", "Fits a bare cable, not a USB-C plug housing."),
                  opt("Medium", "20 mm", "Fits most plugs; both lip halves still hold.", True),
                  opt("Wide", "30 mm", "Fits any plug, lip halves get short.")],
                 {"name": "Slot width", "value": "20 mm", "kind": "length"},
                 ["ExtrudeFeature", "CombineFeature"], ["cable", "slot", "cut", "passage", "charge"])))

    # 6 ribs: one triangular rib, mirrored across the middle plane
    rib = prism_x(1.0, 1.6, [(3.85, 0.7), (6.6, 0.7), (6.08, 5.89)])
    anim = {"type": "mirror", "new_meshes": [rib], "context_meshes": [base_round, panel] + lips,
            "plane_origin_cm": [5, 0, 0], "plane_normal": [1, 0, 0]}
    geo = operation_meshes(anim, 1.0)
    ribs = geo[-2:]
    steps.append(step(
        "ribs", "Reinforce the back support", "Keep the tilted back from flexing when the screen is tapped.",
        "Sketch → Extrude → Mirror", "Sketch a triangular rib on a side plane, extrude it 6 mm, mirror it across the YZ midplane.",
        [("Rib thickness", "6 mm"), ("Ribs", "2 (mirrored)")],
        "The angled back may flex. I add a pair of narrow ribs near the sides instead of filling the "
        "entire area with material, and mirror one rib so both sides stay identical when I edit it.",
        [(0, "The tilted back panel may need more stiffness."),
         (3400, "I build a narrow triangular rib near one side."),
         (6900, "I mirror the structural idea to keep the support balanced.")],
        geo, anim,
        ptr((0, (1.3, 8.5, 0.8), "move"), (1500, (1.3, 3.85, 0.7), "click"), (3000, (1.3, 6.6, 0.7), "drag"),
            (4500, (1.3, 6.08, 5.89), "drag"), (6500, (5, 5.5, 3.0), "click"), (8500, (8.7, 5.5, 3.0), "drag"),
            (9000, (9.0, 6.0, 3.2), "move")),
        decision("stiffening", "How should the tilted back be stiffened?",
                 ["Stiffness when tapped", "Material use", "Edits stay consistent on both sides"],
                 [opt("Thicker panel", "12 mm", "Simple, but doubles the panel's material."),
                  opt("One central rib", None, "Blocks the cable path behind the phone."),
                  opt("Two mirrored side ribs", "6 mm", "Stiff, light, and one edit updates both.", True)],
                 {"name": "Rib thickness", "value": "6 mm", "kind": "length"},
                 ["ExtrudeFeature", "MirrorFeature", "RibFeature", "WebFeature"],
                 ["rib", "gusset", "brace", "support", "web"])))

    # 7 pads: rectangular pattern of four pads
    pad = box(0.6, 1.8, 0.6, 1.8, -0.25, 0.0)
    anim = {"type": "rectangular_pattern", "new_meshes": [pad],
            "context_meshes": [base_round, panel] + lips + ribs,
            "x_count": 2, "x_offset_cm": [7.6, 0, 0], "y_count": 2, "y_offset_cm": [0, 6.6, 0]}
    geo = rectangular_pattern_meshes(anim, 1.0)
    pads = geo[-4:]
    steps.append(step(
        "pads", "Pattern four anti-slip pads", "Keep the stand from sliding on the desk.",
        "Extrude → Rectangular Pattern", "Extrude one 12 mm pad under a corner, then pattern it 2 × 2.",
        [("Pad size", "12 mm"), ("Pattern", "2 × 2")],
        "Instead of making the base heavier, I use four small contact pads to increase friction and "
        "stabilize the stand on an uneven table. Patterning one pad means I edit all four at once.",
        [(0, "The stand should not slide on the desk."),
         (3400, "I place grip pads near the base corners."),
         (6900, "Four pads give support without extending the footprint.")],
        geo, anim,
        ptr((0, (1.2, -1.0, -0.3), "move"), (1500, (1.2, 1.2, -0.25), "click"), (3500, (8.8, 1.2, -0.25), "drag"),
            (5500, (1.2, 7.8, -0.25), "drag"), (7500, (8.8, 7.8, -0.25), "drag"), (9000, (9.5, 8.6, -0.3), "move")),
        decision("anti_slip", "How should the stand resist sliding?",
                 ["Friction on smooth desks", "Rocking on uneven tables", "Weight and cost"],
                 [opt("Heavier base", None, "Works, but adds material and print time."),
                  opt("Full rubber sheet", None, "Grippy, but rocks on uneven tables."),
                  opt("Four corner pads", "12 mm", "Three-point-like contact, no rocking.", True)],
                 {"name": "Pad size", "value": "12 mm", "kind": "length"},
                 ["RectangularPatternFeature", "CircularPatternFeature", "ExtrudeFeature"],
                 ["pad", "foot", "grip", "rubber", "pattern"])))

    # 8 back window: lighten the back panel (window grows, same topology)
    def panel_pieces(a, b, c, d):
        return [panel_part(0.5, a, 0, 9), panel_part(b, 9.5, 0, 9),
                panel_part(a, b, 0, c), panel_part(a, b, d, 9)]
    anim = {"type": "boolean",
            "before_meshes": [base_round] + panel_pieces(5, 5, 4.5, 4.5) + lips + ribs + pads,
            "after_meshes": [base_round] + panel_pieces(2.0, 8.0, 2.5, 7.0) + lips + ribs + pads}
    geo = transition_meshes(anim, 1.0)
    window_geo = geo
    steps.append(step(
        "back_window", "Lighten the back support", "Use less material without losing the side rails.",
        "Sketch → Extrude (Cut)", "Sketch a 60 × 45 mm window on the back panel and cut through it.",
        [("Window", "60 × 45 mm"), ("Rail width", "15 mm")],
        "A solid back panel uses more material than needed. I explore a central opening while retaining "
        "side rails, accepting that it may reduce stiffness — the ribs from step 6 make that acceptable.",
        [(0, "The solid back support may use unnecessary material."),
         (3400, "I cut an opening through its center."),
         (6900, "The side rails remain, but strength should still be checked.")],
        geo, anim,
        ptr((0, (5, 2.0, 4.0), "move"), (1500, (2.0, 3.6, 3.0), "click"), (4000, (8.0, 5.0, 7.0), "drag"),
            (6500, (5, 4.3, 5.0), "click"), (9000, (5, 2.5, 5.5), "move")),
        decision("material_reduction", "Should the back panel be lightened?",
                 ["Material and print time", "Stiffness of the support", "Cooling and cable routing"],
                 [opt("Keep it solid", None, "Stiffest, most material."),
                  opt("Central window", "60 mm", "Saves ~40% of the panel; ribs keep it stiff.", True),
                  opt("Slots", None, "Looks technical, harder to print without supports.")],
                 {"name": "Window width", "value": "60 mm", "kind": "length"},
                 ["ExtrudeFeature", "CombineFeature", "ShellFeature"],
                 ["window", "lighten", "cut", "hole", "opening", "pocket"])))

    # 9 fit check: a phone proxy slides into place
    phone_final = panel_part(1.25, 8.75, 1.05, 16.0, -0.85, -0.05)
    translation = [0, -3.0, 5.0]
    phone_start = {"vertices": rnd([[x - translation[0], y - translation[1], z - translation[2]]
                                    for x, y, z in phone_final["vertices"]]),
                   "triangles": phone_final["triangles"]}
    anim = {"type": "transform", "new_meshes": [phone_start], "context_meshes": window_geo,
            "translation_cm": translation}
    geo = operation_meshes(anim, 1.0)
    steps.append(step(
        "fit", "Check phone fit and clearance", "Verify angle, lip and charging access with a real phone size.",
        "Insert proxy → Move", "Insert a 75 × 150 × 8 mm phone proxy and move it against the back and lip.",
        [("Proxy", "75 × 150 × 8 mm"), ("Clearance", "≥ 1 mm")],
        "I bring in a simplified phone proxy to check the viewing angle, charging access, and whether the "
        "lip clears the device before committing to dimensions. The proxy is temporary and not printed.",
        [(0, "I want to check the design with a phone-sized object."),
         (3400, "I position a temporary proxy against the angled back."),
         (6900, "I inspect the lip and charging clearance before finalizing.")],
        geo, anim,
        ptr((0, (5, -1.0, 14.0), "move"), (1500, (5, 0.5, 12.0), "click"), (6000, (5, 3.0, 8.0), "drag"),
            (7500, (5, 0.7, 1.8), "click"), (9000, (5, -0.5, 2.5), "move")),
        decision("fit_check", "How do you verify the stand fits the phone?",
                 ["Catches dimension mistakes early", "Cost of a failed print", "Effort"],
                 [opt("Trust the dimensions", None, "Fast; mistakes show up only after printing."),
                  opt("Phone proxy in CAD", None, "Cheap check of angle, lip and port access.", True),
                  opt("Print a test slice", None, "Most reliable, costs a print.")],
                 None, ["MoveFeature", "CombineFeature"], ["phone", "proxy", "fit", "clearance", "check"])))
    return {
        "format": "excadmple", "version": 1, "id": "phone-stand",
        "title": "Phone Stand — Nine Design Decisions",
        "author": "Illustrative example (exCADmple team)",
        "description": "Synthetic nine-step example: geometry, ghost pointer and reasoning are authored, "
                       "not a recording of a real designer's session.",
        "reference_offset_cm": [14, 0, 0], "steps": steps,
    }


def tablet_stand():
    """A contrasting example: heavier device, partly different decisions."""
    steps = []
    base = box(0, 16, 0, 12, 0, 1.0)
    anim = {"type": "extrude", "profile": [[0, 0, 0], [16, 0, 0], [16, 12, 0], [0, 12, 0]],
            "direction_cm": [0, 0, 1.0], "cap_triangles": [[0, 1, 2], [0, 2, 3]], "context_meshes": []}
    base = extrude_mesh(anim, 1.0)
    steps.append(step(
        "base", "Heavy, deep base", "Carry a 700 g tablet without tipping.",
        "Sketch → Extrude", "Sketch a 160 × 120 mm rectangle and extrude it 10 mm.",
        [("Width", "160 mm"), ("Depth", "120 mm"), ("Thickness", "10 mm")],
        "A tablet is several times heavier than a phone and its center of mass sits higher, so I make the "
        "base deeper rather than wider: tipping happens front-to-back.",
        [(0, "The tablet is heavy and tall."), (3500, "I extrude a deep, thick base."),
         (7000, "Depth, not width, prevents tipping.")],
        [base], anim,
        ptr((0, (-1, -1, 0), "move"), (1500, (0, 0, 0), "click"), (3000, (16, 12, 0), "drag"),
            (5000, (16, 12, 0.05), "click"), (8000, (16, 12, 1.0), "drag"), (9000, (17, 12.5, 1.2), "move")),
        decision("footprint", "How deep should the base be?",
                 ["Resists tipping under a heavy device", "Desk space", "Material"],
                 [opt("Phone-like", "80 mm", "Tips over with a 700 g tablet."),
                  opt("Deep", "120 mm", "Stable even when drawing on the screen.", True),
                  opt("Very deep", "150 mm", "Stable but hard to fit on a crowded desk.")],
                 {"name": "Base depth", "value": "120 mm", "kind": "length"},
                 ["ExtrudeFeature"], ["base", "foot", "plate", "footprint"])))
    back = box(1, 15, 4.0, 4.8, 1.0, 13.0)
    anim = {"type": "revolve", "new_meshes": [back], "context_meshes": [base],
            "axis_origin_cm": [0, 4.0, 1.0], "axis_direction": [1, 0, 0], "angle_deg": -30}
    geo = operation_meshes(anim, 1.0)
    steps.append(step(
        "support", "Lower viewing angle", "Support both watching and sketching on the tablet.",
        "Sketch → Extrude → Rotate", "Extrude an 8 mm back and tilt it 30° back (60° from the desk).",
        [("Angle from desk", "60 deg"), ("Panel thickness", "8 mm")],
        "Unlike a phone, the tablet is also used for sketching, so a slightly lower angle is a compromise "
        "between watching video and resting a hand on the screen.",
        [(0, "The tablet is watched and drawn on."), (3500, "I tilt the back a bit lower than for a phone."),
         (7000, "It is a compromise between two uses.")],
        geo, anim,
        ptr((0, (8, 2.5, 2), "move"), (1800, (8, 4.4, 6), "click"), (6000, (8, 6.5, 10.0), "drag"),
            (9000, (8, 7.5, 11.5), "move")),
        decision("viewing_angle", "How steep should the device lean?",
                 ["Watching video", "Drawing on the screen", "Stability under hand pressure"],
                 [opt("Drawing", "30 deg", "Comfortable to draw, too flat for video."),
                  opt("Compromise", "60 deg", "Watchable, still usable for quick sketches.", True),
                  opt("Video", "70 deg", "Best for video, tips when drawn on.")],
                 {"name": "Angle from desk", "value": "60 deg", "kind": "angle"},
                 ["ExtrudeFeature", "RevolveFeature", "MoveFeature"], ["back", "support", "angle", "tilt", "panel"])))
    back_t = geo[-1]
    lip_profile = [[1, 0.5, 1.0], [15, 0.5, 1.0], [15, 1.5, 1.0], [1, 1.5, 1.0]]
    anim = {"type": "extrude", "profile": lip_profile, "direction_cm": [0, 0, 1.5],
            "cap_triangles": [[0, 1, 2], [0, 2, 3]], "context_meshes": [base, back_t]}
    lip = extrude_mesh(anim, 1.0)
    steps.append(step(
        "lip", "Tall lip for thick cases", "Hold tablets in rugged cases.",
        "Sketch → Extrude", "Sketch a 10 mm strip at the front and extrude it 15 mm.",
        [("Lip height", "15 mm"), ("Lip thickness", "10 mm")],
        "Tablet cases are thick, and the bezel is wide, so a taller lip does not cover the screen here — "
        "the opposite trade-off from the phone stand.",
        [(0, "Tablet cases are thick."), (3500, "I extrude a taller lip."),
         (7000, "The wide bezel keeps the screen visible.")],
        [base, back_t, lip], anim,
        ptr((0, (-1, 1, 1), "move"), (1500, (1, 0.5, 1.0), "click"), (3000, (15, 1.5, 1.0), "drag"),
            (5000, (15, 1.5, 1.05), "click"), (8000, (15, 1.5, 2.5), "drag"), (9000, (16, 1.5, 2.8), "move")),
        decision("retaining_lip", "How tall should the retaining lip be?",
                 ["Holds a cased device", "Does not cover the screen", "Charging access"],
                 [opt("Phone-like", "10 mm", "Rugged cases ride over it."),
                  opt("Tall", "15 mm", "Holds rugged cases; the bezel keeps the screen clear.", True)],
                 {"name": "Lip height", "value": "15 mm", "kind": "length"},
                 ["ExtrudeFeature"], ["lip", "ledge", "stop", "front"])))
    sheet = box(0.3, 15.7, 0.3, 11.7, -0.2, 0.0)
    anim = {"type": "reveal", "new_meshes": [sheet], "context_meshes": [base, back_t, lip]}
    steps.append(step(
        "cork", "Full cork sheet underneath", "Stop the heavier stand from sliding.",
        "Extrude", "Extrude a 2 mm sheet covering the whole underside (cut later from cork).",
        [("Sheet thickness", "2 mm")],
        "With a heavy tablet the stand already presses firmly on the desk, so rocking is less of a risk "
        "than for the phone stand; a full cork sheet gives the most friction and protects the desk.",
        [(0, "The heavy stand presses down firmly."), (3500, "I cover the whole underside."),
         (7000, "Cork adds friction and protects the desk.")],
        [base, back_t, lip, sheet], anim,
        ptr((0, (8, -1.5, -0.3), "move"), (1500, (0.3, 0.3, -0.2), "click"), (5000, (15.7, 11.7, -0.2), "drag"),
            (9000, (16.5, 12.5, -0.3), "move")),
        decision("anti_slip", "How should the stand resist sliding?",
                 ["Friction on smooth desks", "Rocking on uneven tables", "Protects the desk"],
                 [opt("Corner pads", None, "Less friction area; fine for light devices."),
                  opt("Full cork sheet", "2 mm", "Most friction; weight prevents rocking.", True)],
                 {"name": "Sheet thickness", "value": "2 mm", "kind": "length"},
                 ["ExtrudeFeature", "RectangularPatternFeature"], ["pad", "foot", "grip", "rubber", "cork", "sheet"])))
    anim = {"type": "reveal", "new_meshes": [back_t], "context_meshes": [base, lip, sheet]}
    steps.append(step(
        "solid_back", "Keep the back solid", "Stay stiff under hand pressure while drawing.",
        "(no operation)", "Decide not to cut a lightening window into the back panel.",
        [("Window", "none")],
        "I considered a window like on a phone stand, but drawing pushes hard on the screen. A solid back is "
        "stiffer, and the extra material is worth it for this use.",
        [(0, "Should the back be lightened?"), (3500, "Drawing pushes hard on the screen."),
         (7000, "I keep it solid on purpose.")],
        [base, lip, sheet, back_t], anim,
        ptr((0, (8, 2, 5), "move"), (3000, (8, 5.6, 7.0), "click"), (6000, (8, 5.6, 7.0), "move"),
            (9000, (8, 3, 8), "move")),
        decision("material_reduction", "Should the back panel be lightened?",
                 ["Stiffness under hand pressure", "Material", "Looks"],
                 [opt("Central window", "90 mm", "Saves material, flexes when drawn on."),
                  opt("Keep it solid", None, "Stiff under pressure; worth the material.", True)],
                 None, ["ExtrudeFeature", "CombineFeature", "ShellFeature"],
                 ["window", "lighten", "cut", "hole", "opening", "pocket"])))
    return {
        "format": "excadmple", "version": 1, "id": "tablet-stand",
        "title": "Tablet Stand — Heavier Device, Different Trade-offs",
        "author": "Illustrative example (exCADmple team)",
        "description": "Synthetic contrasting example: it answers the same design questions as the phone "
                       "stand, sometimes differently. Not a recording of a real session.",
        "reference_offset_cm": [14, -16, 0], "steps": steps,
    }


def main():
    for name, builder in (("phone_stand.json", phone_stand), ("tablet_stand.json", tablet_stand)):
        path = ROOT / "examples" / name
        path.write_text(json.dumps(builder(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
