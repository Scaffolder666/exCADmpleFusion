"""Pure HiM-style player overlay geometry.

Coordinates use Blender's 3D-viewport WINDOW region (origin at bottom-left).
This module deliberately imports no bpy/gpu: placement and hit testing can
be regression-tested without launching Blender.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    def contains(self, x, y):
        return self.x <= x <= self.x + self.w and self.y <= y <= self.y + self.h


def panel_layout(region_width, region_height, active_index, step_count):
    """Compute a compact right-side overlay, never a second Blender viewport."""
    rw, rh = int(region_width), int(region_height)
    if rw < 430 or rh < 435:
        return None
    width = min(302, rw - 36)
    height = min(612, rh - 28)
    left, top = rw - width - 16, rh - 14
    bottom = top - height
    outer = Rect(left, bottom, width, height)
    buttons = {
        "close": Rect(left + width - 36, top - 40, 25, 25),
        "previous": Rect(left + 27, top - 104, 48, 36),
        "play_pause": Rect(left + 81, top - 104, 104, 36),
        "next": Rect(left + 191, top - 104, 48, 36),
        "progress": Rect(left + 18, top - 146, width - 36, 14),
    }
    total = max(0, int(step_count))
    current = min(max(0, int(active_index)), max(0, total - 1))
    why_h = 76 if height >= 565 else 64
    # Leave at least 12 px between the rationale/transcript and the speed
    # buttons. The old height threshold produced overlapping controls at
    # around 435–510 px and 593–610 px viewport heights.
    speed_top = bottom + 42
    usable_floor = speed_top + 12
    capacity = 1
    for n in range(min(4, max(1, total)), 0, -1):
        last_bottom = top - 236 - (n - 1) * 57
        if last_bottom - why_h - 14 >= usable_floor:
            capacity = n
            break
    first = max(0, min(current - 1, total - capacity))
    cards = [
        (i, Rect(left + 19, top - 236 - (i - first) * 57, width - 38, 52))
        for i in range(first, min(first + capacity, total))
    ]
    last_bottom = min((r.y for _, r in cards), default=top - 236)
    why = Rect(left + 18, last_bottom - why_h - 14, width - 36, why_h)
    transcript_y = why.y - 56
    transcript = (
        Rect(left + 18, transcript_y, width - 36, 48)
        if height >= 565 and transcript_y >= usable_floor else None
    )
    buttons["speed_minus"] = Rect(left + 130, bottom + 15, 29, 27)
    buttons["speed_plus"] = Rect(left + width - 42, bottom + 15, 29, 27)
    return {
        "bounds": outer, "buttons": buttons, "cards": cards,
        "why": why, "transcript": transcript, "active_index": current,
        "top": top, "bottom": bottom, "capacity": capacity,
        "steps_start": first,
    }


def hit_test(layout, x, y):
    """Resolve input only inside the player; outside returns None.

    An unassigned part of the panel returns 'panel' so clicks there never
    select/edit 3D objects behind the overlay.
    """
    if layout is None or not layout["bounds"].contains(x, y):
        return None
    for action, rect in layout["buttons"].items():
        if rect.contains(x, y):
            return action
    for index, rect in layout["cards"]:
        if rect.contains(x, y):
            return "step:" + str(index)
    return "panel"
