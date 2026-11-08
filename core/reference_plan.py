"""Version A: how a tutorial step maps onto the designer's Fusion timeline.

Pure Python. A step lists its ``source_features`` (from the extracted
draft). In the reference instance each step is played HiM-style: the
timeline is rolled to just after the feature being shown and that
feature's parameters grow from ~0 to their value. A step with several
features shares its time equally between them, in timeline order.
"""


def map_steps(steps, timeline_features):
    """Map recorded source features to the imported parametric timeline.

    Prefer the recorded timeline index AND name. A unique name is a safe
    fallback when indices shifted. Never silently choose the first of
    several identically named features: an incorrect mapping would animate
    a different CAD operation while showing the original narration.
    Returns (per-step FeatureInfo lists, unmatched descriptions).
    """
    by_index = {f.index: f for f in timeline_features}
    by_name = {}
    for feature in timeline_features:
        by_name.setdefault(feature.name, []).append(feature)
    mapped, unmatched = [], []
    for step in steps:
        found = []
        for source in step.get("source_features", []):
            name, index = source.get("name"), source.get("index")
            indexed = by_index.get(index) if isinstance(index, int) else None
            if indexed is not None and (not name or indexed.name == name):
                match = indexed
            elif name and len(by_name.get(name, [])) == 1:
                match = by_name[name][0]
            else:
                match = None
            if match is None:
                unmatched.append("step {}: {} (index {})".format(
                    step.get("id", "?"), name or "<unnamed>", index))
            elif match not in found:
                found.append(match)
        mapped.append(sorted(found, key=lambda f: f.index))
    return mapped, unmatched


def animated(features):
    """Sketches are shown by rolling the timeline, not animated."""
    return [f for f in features if not f.is_sketch]


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
