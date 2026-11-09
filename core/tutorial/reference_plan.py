"""Version A: how a tutorial step maps onto the designer's Fusion timeline.

Pure Python. A step lists its ``source_features`` (from the extracted
draft). In the reference instance each step is played HiM-style: the
timeline is rolled to just after the feature being shown and that
feature's parameters grow from ~0 to their value. A step with several
features shares its time equally between them, in timeline order.
"""


def map_steps(steps, timeline_features):
    """Map recorded source features to the imported parametric timeline.

    A recorded feature matches the timeline item with the same index AND
    name (and, when both are known, the same kind). If indices shifted, a
    name that is unique in the timeline is accepted, again only with a
    compatible kind. Never silently choose the first of several identically
    named features, and never give one timeline item to two steps: an
    incorrect mapping would animate a different CAD operation while showing
    the original narration. Anything that cannot be matched is reported.
    Returns (per-step FeatureInfo lists, unmatched descriptions).
    """
    by_index = {f.index: f for f in timeline_features}
    by_name = {}
    for feature in timeline_features:
        by_name.setdefault(feature.name, []).append(feature)
    claimed = {}
    mapped, unmatched = [], []
    for step in steps:
        found = []
        step_id = step.get("id", "?")
        for source in step.get("source_features", []):
            name, index = source.get("name"), source.get("index")
            match, reason = _match(source, by_index, by_name)
            if match is not None and match.index in claimed and claimed[match.index] != step_id:
                match, reason = None, "already used by step " + str(claimed[match.index])
            if match is None:
                unmatched.append("step {}: {} (index {}) - {}".format(
                    step_id, name or "<unnamed>", index, reason))
                continue
            claimed[match.index] = step_id
            if match not in found:
                found.append(match)
        mapped.append(sorted(found, key=lambda f: f.index))
    return mapped, unmatched


def _same_kind(recorded, feature):
    return not recorded or not feature.kind or recorded == feature.kind


def _match(source, by_index, by_name):
    name, index, kind = source.get("name"), source.get("index"), source.get("kind")
    if isinstance(index, bool):
        index = None
    indexed = by_index.get(index) if isinstance(index, int) else None
    if indexed is not None and (not name or indexed.name == name):
        if _same_kind(kind, indexed):
            return indexed, ""
        return None, "timeline item {} is a {}, the tutorial recorded a {}".format(
            index, indexed.kind, kind)
    if not name:
        return None, "no name and no timeline item at this index"
    candidates = by_name.get(name, [])
    if not candidates:
        return None, "not in the model"
    if len(candidates) > 1:
        return None, "{} timeline items share this name".format(len(candidates))
    if not _same_kind(kind, candidates[0]):
        return None, "the model's {} is a {}, the tutorial recorded a {}".format(
            name, candidates[0].kind, kind)
    return candidates[0], ""


def animated(features):
    """Sketches and construction geometry are shown by rolling the
    timeline, not animated."""
    return [f for f in features if not f.is_sketch and not f.kind.startswith("Construction")]


def frame_target(features, progress):
    """(position, local progress) for a step's features at ``progress``."""
    items = animated(features)
    if not items:
        return None, 1.0
    progress = max(0.0, min(1.0, float(progress)))
    if progress >= 1.0:
        return len(items) - 1, 1.0
    scaled = progress * len(items)
    position = min(len(items) - 1, int(scaled))
    return position, scaled - position


def steps_for_features(mapped, feature_indices):
    """Steps containing any of the given timeline indices (HiM filter result)."""
    wanted = set(feature_indices)
    return [i for i, features in enumerate(mapped) if any(f.index in wanted for f in features)]
