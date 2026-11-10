"""History in Motion animation model (paper Sections 4.2, 4.3 and 6.2).

Pure Python: no Fusion import. Covers
* which parameters animate which feature (20 supported features, Figure 7),
* the parameter value at a given progress (from ~0 to the real value),
* a restore journal so every temporarily changed parameter is put back.

Frame pacing (adaptive frames, as in the paper) lives in the reference
panel: ui/reference/frame_clock.js.
"""
from dataclasses import dataclass

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


def interpolate(target, progress, start_fraction=START_FRACTION):
    """Parameter value at progress in [0, 1]; keeps the sign of ``target``."""
    progress = max(0.0, min(1.0, float(progress)))
    fraction = start_fraction + (1.0 - start_fraction) * progress
    return target * fraction


@dataclass
class Frame:
    position: int       # index into the clip (0 = newest feature)
    progress: float     # 0 = before the feature, 1 = after it
    finished: bool = False


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
            try:
                value = float(param.value)
            except Exception:
                value = None
            self._originals[key] = (param, param.expression, value)

    @staticmethod
    def _unchanged(param, expression, value):
        """Same expression text AND same value: writing it back would only
        make Fusion recompute for nothing (e.g. a step that ended exactly at
        its real value)."""
        try:
            if value is None or param.expression != expression:
                return False
            current = float(param.value)
            return abs(current - value) <= 1e-9 * max(1.0, abs(value))
        except Exception:
            return False

    def restore(self, keys=None):
        failures = []
        for key in list(self._originals if keys is None else keys):
            if key not in self._originals:
                continue
            param, expression, value = self._originals[key]
            try:
                if not self._unchanged(param, expression, value):
                    # Write the original expression back: it also resets the
                    # value when only the value was changed.
                    param.expression = expression
                del self._originals[key]
            except Exception:
                failures.append(key)
        if failures:
            raise RuntimeError("Could not restore {} parameter(s): {}".format(
                len(failures), ", ".join(str(k) for k in failures)))
