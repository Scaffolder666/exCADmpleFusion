"""History in Motion animation model (paper Sections 4.2, 4.3 and 6.2).

Pure Python: no Fusion import. Covers
* which parameters animate which feature (20 supported features, Figure 7),
* the clip plan: filtered features played newest first (reverse order),
* adaptive frame stepping (15 frames for 2 s ... 75 frames for 10 s, then
  tuned from the execution time of the previous frame),
* the playback state machine (play, pause, replay, speed, step forward,
  step backward which reverses playback),
* a restore journal so every temporarily changed parameter is put back.
"""
from dataclasses import dataclass

MIN_SECONDS = 2.0
MAX_SECONDS = 10.0
MIN_FRAMES = 15
MAX_FRAMES = 75
START_FRACTION = 0.02      # many Fusion parameters reject exactly zero

PARAMETRIC = "parameter"
FADE = "fade"
NONE = "none"

# Feature kind -> attribute paths of the ModelParameters to animate from ~0 to
# their actual value. Paths are evaluated by the Fusion adapter; a missing
# path, or one that is not a ModelParameter (e.g. an extrude "to object"
# extent has no distance), is skipped. Only these paths are animated: a
# parametric feature with none of them falls back to the visual effect. "*" means "every edge/extent set". Features without
# parameters use a custom fade/scale effect, like the paper does for import,
# export, split, mirror and combine.
FEATURES = {
    "ExtrudeFeature":            (PARAMETRIC, ("extentOne.distance", "extentTwo.distance")),
    "RevolveFeature":            (PARAMETRIC, ("extentDefinition.angle", "extentDefinition.angleOne", "extentDefinition.angleTwo")),
    # Constant, variable (start/end) and chord-length fillet edge sets.
    "FilletFeature":             (PARAMETRIC, ("edgeSets*.radius", "edgeSets*.startRadius",
                                               "edgeSets*.endRadius", "edgeSets*.chordLength")),
    # Equal distance, two distances and distance-and-angle chamfers; the
    # angle itself is not grown from zero.
    "ChamferFeature":            (PARAMETRIC, ("edgeSets*.distance", "edgeSets*.distanceOne", "edgeSets*.distanceTwo")),
    "HoleFeature":               (PARAMETRIC, ("extentDefinition.distance", "holeDiameter")),
    "ShellFeature":              (PARAMETRIC, ("insideThickness", "outsideThickness")),
    "CircularPatternFeature":    (PARAMETRIC, ("totalAngle",)),
    "RectangularPatternFeature": (PARAMETRIC, ("distanceOne", "distanceTwo")),
    "SweepFeature":              (PARAMETRIC, ("distanceOne", "distanceTwo")),
    "OffsetFacesFeature":        (PARAMETRIC, ("distance",)),
    "ThickenFeature":            (PARAMETRIC, ("thickness",)),
    "DraftFeature":              (PARAMETRIC, ("angleOne", "angleTwo")),
    "ThreadFeature":             (PARAMETRIC, ("threadLength", "threadOffset")),
    "CoilFeature":               (PARAMETRIC, ("height", "revolutions")),
    "MirrorFeature":             (FADE, ()),
    "CombineFeature":            (FADE, ()),
    "SplitBodyFeature":          (FADE, ()),
    "SplitFaceFeature":          (FADE, ()),
    "LoftFeature":               (FADE, ()),
    "MoveFeature":               (FADE, ()),
}
# Not counted among the 20 above but treated with the generic fade effect.
FADE_ALIASES = ("BaseFeature", "CopyPasteBody", "ImportFeature", "ExportFeature",
                "RemoveFeature", "BoundaryFillFeature", "PatchFeature", "StitchFeature")


def short_kind(object_type):
    """'adsk::fusion::ExtrudeFeature' -> 'ExtrudeFeature'."""
    return (object_type or "").split("::")[-1]


def animation_mode(object_type):
    kind = short_kind(object_type)
    if kind in FEATURES:
        return FEATURES[kind][0]
    if kind in FADE_ALIASES:
        return FADE
    return NONE     # still listed in the panel, but cannot be animated


def parameter_paths(object_type):
    return FEATURES.get(short_kind(object_type), (NONE, ()))[1]


def seconds_per_feature(value):
    """Clamp the control-panel slider value to the paper's 2..10 s range."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 4.0
    return max(MIN_SECONDS, min(MAX_SECONDS, value))


def initial_frames(seconds):
    """15 frames for 2 s, 75 frames for 10 s, linear in between."""
    seconds = seconds_per_feature(seconds)
    ratio = (seconds - MIN_SECONDS) / (MAX_SECONDS - MIN_SECONDS)
    return int(round(MIN_FRAMES + ratio * (MAX_FRAMES - MIN_FRAMES)))


def interpolate(target, progress, start_fraction=START_FRACTION):
    """Parameter value at progress in [0, 1]; keeps the sign of ``target``."""
    progress = max(0.0, min(1.0, float(progress)))
    fraction = start_fraction + (1.0 - start_fraction) * progress
    return target * fraction


class AdaptiveStepper:
    """Chooses the next progress increment so a feature finishes on time.

    The first increment comes from the frame estimate. After each rendered
    frame the increment is re-derived from how long that frame took: slow
    model recomputes give fewer, larger steps; fast ones more, smaller steps.
    """

    def __init__(self, seconds):
        self.seconds = seconds_per_feature(seconds)
        self.increment = 1.0 / initial_frames(self.seconds)
        self.elapsed = 0.0

    def next_increment(self, frame_seconds, progress_done):
        frame_seconds = max(1e-3, float(frame_seconds))
        self.elapsed += frame_seconds
        remaining_time = self.seconds - self.elapsed
        remaining_progress = max(0.0, 1.0 - progress_done)
        if remaining_time <= frame_seconds:
            self.increment = remaining_progress
        else:
            frames_left = max(1.0, remaining_time / frame_seconds)
            self.increment = remaining_progress / frames_left
        return self.increment


@dataclass
class Frame:
    position: int       # index into the clip (0 = newest feature)
    progress: float     # 0 = before the feature, 1 = after it
    finished: bool = False


class Playback:
    """Playback over a clip of N features, newest first.

    ``tick(frame_seconds)`` advances by one adaptive frame and returns the
    Frame to render. Forward playback goes 0 -> 1 per feature and then on to
    the next (older) feature. Stepping backward reverses playback (1 -> 0).
    """

    def __init__(self, count, seconds=4.0, animatable=None):
        self.count = int(count)
        self.seconds = seconds_per_feature(seconds)
        self.animatable = list(animatable) if animatable is not None else [True] * self.count
        self.position = 0
        self.progress = 0.0
        self.direction = 1
        self.playing = False
        self.continuous = True        # False after a single step command
        self._stepper = AdaptiveStepper(self.seconds)
        self._skip_static()

    # --- commands -----------------------------------------------------------
    def play(self):
        if self.count == 0:
            return
        if self.direction > 0 and self.position >= self.count - 1 and self.progress >= 1.0:
            self.replay()
            return
        self.playing = True
        self.continuous = True

    def pause(self):
        self.playing = False

    def replay(self):
        self.position, self.progress, self.direction = 0, 0.0, 1
        self._skip_static()
        self._stepper = AdaptiveStepper(self.seconds)
        self.playing = self.count > 0
        self.continuous = True

    def set_speed(self, seconds):
        self.seconds = seconds_per_feature(seconds)
        done = self.progress if self.direction > 0 else 1.0 - self.progress
        self._stepper = AdaptiveStepper(self.seconds)
        self._stepper.elapsed = done * self.seconds

    def select(self, position):
        if not 0 <= position < self.count:
            raise IndexError("Feature position out of range")
        self.position, self.progress, self.direction = position, 0.0, 1
        self._stepper = AdaptiveStepper(self.seconds)
        self.playing, self.continuous = True, False

    def step_forward(self):
        """Animate the next (older) feature once."""
        if self.count == 0:
            return
        if self.progress >= 1.0 or self.direction < 0:
            if self.position < self.count - 1:
                self.position += 1
        self.progress, self.direction = 0.0, 1
        self._stepper = AdaptiveStepper(self.seconds)
        self.playing, self.continuous = True, False

    def step_backward(self):
        """Reverse playback: undo the current feature, or go to the previous
        (newer) feature and play it in reverse."""
        if self.count == 0:
            return
        if self.progress <= 0.0 and self.position > 0:
            self.position -= 1
            self.progress = 1.0
        elif self.progress <= 0.0:
            self.progress = 1.0
        self.direction = -1
        self._stepper = AdaptiveStepper(self.seconds)
        self._stepper.elapsed = (1.0 - self.progress) * self.seconds
        self.playing, self.continuous = True, False

    # --- clock ----------------------------------------------------------------
    def _skip_static(self):
        """Non-animatable features are shown but pass instantly."""
        while (0 <= self.position < self.count and not self.animatable[self.position]
               and self.direction > 0 and self.position < self.count - 1):
            self.position += 1

    def current(self):
        return Frame(self.position, self.progress, not self.playing)

    def tick(self, frame_seconds=None):
        if not self.playing or self.count == 0:
            return Frame(self.position, self.progress, True)
        if not self.animatable[self.position]:
            self.progress = 1.0 if self.direction > 0 else 0.0
        else:
            if frame_seconds is None:
                step = self._stepper.increment
            else:
                done = self.progress if self.direction > 0 else 1.0 - self.progress
                step = self._stepper.next_increment(frame_seconds, done)
            self.progress = max(0.0, min(1.0, self.progress + self.direction * step))
        reached = self.progress >= 1.0 if self.direction > 0 else self.progress <= 0.0
        if not reached:
            return Frame(self.position, self.progress)
        frame = Frame(self.position, self.progress)
        if not self.continuous or self.direction < 0:
            self.playing = False
            frame.finished = True
            return frame
        if self.position >= self.count - 1:
            self.playing = False
            frame.finished = True
            return frame
        # continue with the next, older feature
        self.position += 1
        self.progress = 0.0
        self._stepper = AdaptiveStepper(self.seconds)
        self._skip_static()
        return frame

    def as_dict(self):
        return {"position": self.position, "progress": round(self.progress, 4),
                "direction": self.direction, "playing": self.playing,
                "seconds": self.seconds, "count": self.count}


class RestoreJournal:
    """Records original parameter expressions before the first change and
    restores all of them. ``key`` identifies a parameter; ``param`` must have a
    read/write ``expression`` attribute (Fusion ModelParameter)."""

    def __init__(self):
        self._originals = {}

    def __len__(self):
        return len(self._originals)

    def capture(self, key, param):
        if key not in self._originals:
            self._originals[key] = (param, param.expression)

    def restore(self, keys=None):
        failures = []
        for key in list(self._originals if keys is None else keys):
            if key not in self._originals:
                continue
            param, expression = self._originals[key]
            try:
                # Always write the original expression back: it also resets
                # the value even if only the value was changed.
                param.expression = expression
                del self._originals[key]
            except Exception:
                failures.append(key)
        if failures:
            raise RuntimeError("Could not restore {} parameter(s): {}".format(
                len(failures), ", ".join(str(k) for k in failures)))
