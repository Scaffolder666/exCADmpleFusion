"""Best-effort read-only feature provenance from an active Fusion design.

Fusion does not expose a universal face/edge/vertex-to-all-features ancestry
API. This scanner reports *candidate* features whose result bodies contain
the selected entity; it never claims a complete dependency graph.
"""
import adsk.core
import adsk.fusion


def _token(entity):
    try:
        return entity.entityToken or ""
    except Exception:
        return ""


def _same_entity(design, left, right):
    if left is right:
        return True
    a, b = _token(left), _token(right)
    if not a or not b:
        return False
    try:
        return any(x is right for x in design.findEntityByToken(a))
    except Exception:
        return a == b


def _body_of(entity):
    try:
        if adsk.fusion.BRepFace.cast(entity):
            return entity.body
        if adsk.fusion.BRepEdge.cast(entity):
            return entity.faces.item(0).body if entity.faces.count else None
        if adsk.fusion.BRepVertex.cast(entity):
            return entity.edges.item(0).faces.item(0).body if entity.edges.count and entity.edges.item(0).faces.count else None
    except Exception:
        return None
    return None


def scan_candidate_features(design, selected, limit=300):
    """Return candidate timeline features associated with selected result body.

    Body association is intentionally not represented as exact feature ancestry.
    """
    if not design or not selected:
        return []
    selected_body = _body_of(selected)
    if selected_body is None:
        return []
    results = []
    timeline = design.timeline
    for index in range(min(timeline.count, limit)):
        item = timeline.item(index)
        try:
            entity = item.entity
            if not entity:
                continue
            bodies = getattr(entity, "bodies", None)
            if not bodies:
                continue
            matched = any(_same_entity(design, bodies.item(j), selected_body)
                          for j in range(bodies.count))
            if matched:
                results.append({
                    "timeline_index": index,
                    "name": getattr(entity, "name", "") or "Feature",
                    "object_type": getattr(entity, "objectType", ""),
                    "entity_token": _token(entity),
                    "association": "result_body_candidate",
                })
        except Exception:
            continue
    return list(reversed(results))
