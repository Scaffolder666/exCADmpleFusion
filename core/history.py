"""HiM-inspired dependency filtering over explicitly authored feature provenance.

This module does not infer Fusion BRep face ancestry. A package must supply
feature ids, input dependencies, and geometry entity ids.
"""
class HistoryError(ValueError):
    pass


def relevant_history(features, entity_id, expand=False):
    """Return features affecting entity, newest first, stopping at sketch.

    Features have id, inputs (upstream feature ids), affects (entity ids),
    type, and optional sketch_plane_feature (feature id supporting its sketch).
    """
    if not isinstance(entity_id, str) or not entity_id:
        raise HistoryError("Select a geometry entity id")
    if not isinstance(features, list) or len(features) > 500:
        raise HistoryError("Invalid feature history")
    by_id = {}
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("id"), str):
            raise HistoryError("Each feature needs an id")
        fid = feature["id"]
        if not fid or fid in by_id:
            raise HistoryError("Duplicate or empty feature id")
        if not isinstance(feature.get("inputs", []), list) or not isinstance(feature.get("affects", []), list):
            raise HistoryError("Feature dependencies must be arrays")
        by_id[fid] = feature
    selected = set()
    visiting = set()

    def visit(fid):
        if fid in selected:
            return
        if fid in visiting:
            raise HistoryError("Cyclic feature dependencies")
        if fid not in by_id:
            raise HistoryError("Unknown upstream feature: " + str(fid))
        visiting.add(fid)
        feature = by_id[fid]
        if feature.get("type", "").lower() == "sketch":
            selected.add(fid)
            if expand and feature.get("sketch_plane_feature"):
                visit(feature["sketch_plane_feature"])
        else:
            for dep in feature.get("inputs", []):
                visit(dep)
            selected.add(fid)
        visiting.remove(fid)

    for feature in features:
        if entity_id in feature.get("affects", []):
            visit(feature["id"])
    return [feature for feature in reversed(features) if feature["id"] in selected]
