"""Ghost Pointer: an authored, model-anchored virtual pointer.

Shows where the example's designer selected, clicked and dragged. It is drawn
as transient Custom Graphics next to the reference model and never moves the
user's real mouse. Positions are in centimeters in the example's local frame
(the renderer adds ``reference_offset_cm``).
"""
import math

EVENTS = ("move", "click", "drag")
MAX_POINTS = 200
CLICK_MS = 450


class PointerError(ValueError):
    pass


def validate_pointer(points, duration_ms):
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
        raise PointerError("Pointer path needs 1–200 points")
    last = -1
    for point in points:
        if not isinstance(point, dict):
            raise PointerError("Pointer point must be an object")
        at = point.get("at_ms")
        if isinstance(at, bool) or not isinstance(at, (int, float)) or not 0 <= at <= duration_ms:
            raise PointerError("Pointer at_ms must lie within the step")
        if at < last:
            raise PointerError("Pointer points must be in time order")
        last = at
        xyz = point.get("xyz")
        if (not isinstance(xyz, list) or len(xyz) != 3 or
                not all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in xyz)):
            raise PointerError("Pointer xyz must be three finite numbers")
        if point.get("event", "move") not in EVENTS:
            raise PointerError("Pointer event must be move, click or drag")
    return points


def sample(points, at_ms, trail_ms=1500):
    """Pointer state at a time: position, current gesture, recent trail and
    whether a click ring should be shown."""
    if not points:
        return None
    if at_ms <= points[0]["at_ms"]:
        pos, segment = list(points[0]["xyz"]), 0
    elif at_ms >= points[-1]["at_ms"]:
        pos, segment = list(points[-1]["xyz"]), len(points) - 1
    else:
        segment = max(i for i, p in enumerate(points) if p["at_ms"] <= at_ms)
        a, b = points[segment], points[segment + 1]
        span = max(1e-6, b["at_ms"] - a["at_ms"])
        t = (at_ms - a["at_ms"]) / span
        t = t * t * (3 - 2 * t)          # ease in/out like a hand movement
        pos = [a["xyz"][i] + (b["xyz"][i] - a["xyz"][i]) * t for i in range(3)]
    nxt = points[segment + 1] if segment + 1 < len(points) else None
    gesture = nxt.get("event", "move") if nxt and nxt.get("event") == "drag" else "move"
    pressed = any(p.get("event") in ("click", "drag") and 0 <= at_ms - p["at_ms"] <= CLICK_MS for p in points)
    trail = [list(p["xyz"]) for p in points if at_ms - trail_ms <= p["at_ms"] <= at_ms]
    trail.append(pos)
    return {"xyz": pos, "gesture": gesture, "pressed": pressed, "trail": trail}
