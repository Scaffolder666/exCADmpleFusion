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


def _adjacent_faces(entity):
    """Collect faces touching a selected BRep face, edge, or vertex."""
    if adsk.fusion.BRepFace.cast(entity):
        return [entity]
    if adsk.fusion.BRepEdge.cast(entity):
        return [entity.faces.item(i) for i in range(entity.faces.count)]
    if adsk.fusion.BRepVertex.cast(entity):
        faces = []
        for i in range(entity.edges.count):
            edge = entity.edges.item(i)
            for j in range(edge.faces.count):
                face = edge.faces.item(j)
                if not any(existing is face for existing in faces):
                    faces.append(face)
        return faces
    return []


def _feature_from_face(face):
    """Fusion exposes a creator on some BRepFace implementations only.

    Never substitute body membership for face provenance.
    """
    try:
        return face.createdByFeature
    except (AttributeError, RuntimeError):
        return None


def trace_direct_creators(design, selected):
    """Conservative direct creator attribution, not complete ancestry.

    Edge/vertex provenance is ambiguous if adjacent faces have different
    creators. Such features are reported as adjacent-face provenance.
    """
    if not design or not selected:
        return {"features": [], "complete": False, "reason": "No selected geometry"}
    faces = _adjacent_faces(selected)
    if not faces:
        return {"features": [], "complete": False, "reason": "No adjacent BRep faces"}
    result = {}
    for face in faces:
        feature = _feature_from_face(face)
        if not feature:
            continue
        token = _token(feature)
        key = token or str(id(feature))
        result[key] = feature
    features = []
    for feature in result.values():
        try:
            timeline = feature.timelineObject
            index = timeline.index if timeline else None
        except Exception:
            index = None
        features.append({
            "timeline_index": index,
            "name": getattr(feature, "name", "") or "Feature",
            "object_type": getattr(feature, "objectType", ""),
            "entity_token": _token(feature),
            "association": "face_creator" if adsk.fusion.BRepFace.cast(selected) else "adjacent_face_creator",
        })
    features.sort(key=lambda item: item["timeline_index"] if item["timeline_index"] is not None else -1, reverse=True)
    return {
        "features": features, "complete": False,
        "reason": "Direct creator attribution only; complete historical topology lineage is not exposed",
    }
