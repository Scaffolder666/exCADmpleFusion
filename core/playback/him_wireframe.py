"""Read a real Fusion Timeline *before* one feature, for a ghost wireframe.

Pure-Python API-facing helper, deliberately does not change visibility,
opacity, feature parameters, timeline position, or document state. The caller
must put the Fusion marker immediately before the feature first.

Curves returned by BRepEdge.geometry are transient Curve3D values suitable
for CustomGraphicsGroup.addCurve; no triangle meshes or guessed geometry.
"""
from core.spatial import _model_bodies

MAX_GHOST_BODIES = 200
MAX_GHOST_EDGES = 2000


class WireframeOverflow(RuntimeError):
    pass


def capture_before_feature(design, max_bodies=MAX_GHOST_BODIES,
                           max_edges=MAX_GHOST_EDGES):
    """Return a complete, budgeted edge snapshot or None (never partial).

    A body already hidden by the original document is excluded from the
    context. If any visible body does not expose edges (e.g. mesh-only
    geometry), abort wireframe isolation rather than conceal its surfaces
    and silently omit its context.
    """
    curves, tokens = [], set()
    visible = 0
    for token, body in _model_bodies(design):
        if getattr(body, "isVisible", True) is False:
            continue
        visible += 1
        if visible > max_bodies:
            raise WireframeOverflow("ghost context exceeds {} visible bodies".format(max_bodies))
        edges = getattr(body, "edges", None)
        if edges is None:
            return None
        if not hasattr(edges, "count") or not hasattr(edges, "item"):
            return None
        count = edges.count
        if count > max_edges - len(curves):
            raise WireframeOverflow("ghost context exceeds {} BRep edges".format(max_edges))
        for i in range(count):
            # An edge without geometry (e.g. a degenerate apex of a revolved
            # body) is skipped; it used to discard the whole context.
            try:
                geometry = edges.item(i).geometry
            except Exception:
                continue
            if geometry is None:
                continue
            curves.append(geometry)
        tokens.add(token)
    return {"curves": tuple(curves), "body_tokens": frozenset(tokens),
            "body_count": visible}


def can_isolate_feature(kind, feature_faces, result_bodies, before_tokens):
    """Decide if a Feature's *own geometry* can be rendered without lying.

    Surface-modifying Features require the affected faces. A whole Body may
    only stand in for operations that can introduce a genuinely new body,
    and only if the body was not present before the Timeline operation.
    """
    if feature_faces:
        return True
    creates_body = {
        "ExtrudeFeature", "RevolveFeature", "MirrorFeature",
        "CircularPatternFeature", "RectangularPatternFeature",
        "BaseFeature", "PasteBodiesFeature", "CopyPasteBody",
    }
    return kind in creates_body and any(
        getattr(body, "entityToken", None) not in before_tokens
        for body in result_bodies)
