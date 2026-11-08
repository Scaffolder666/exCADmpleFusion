"""Version A: how a tutorial step maps onto the designer's Fusion timeline.

Pure Python. A step lists its ``source_features`` (from the extracted
draft); the reference instance rolls the timeline to the last of them.
"""


def map_steps(steps, timeline_features):
    """steps: package steps; timeline_features: FeatureInfo list of the opened
    .f3d. Returns (per-step FeatureInfo lists, unmatched names)."""
    by_index = {f.index: f for f in timeline_features}
    by_name = {}
    for feature in timeline_features:
        by_name.setdefault(feature.name, []).append(feature)
    mapped, unmatched = [], []
    for step in steps:
        found = []
        for source in step.get("source_features", []):
            name, index = source.get("name"), source.get("index")
            candidates = by_name.get(name, [])
            if len(candidates) == 1:
                match = candidates[0]
            elif index in by_index and by_index[index].name == name:
                match = by_index[index]
            else:
                match = candidates[0] if candidates else None
            if match is None:
                unmatched.append(name)
            elif match not in found:
                found.append(match)
        mapped.append(sorted(found, key=lambda f: f.index))
    return mapped, unmatched


def steps_for_features(mapped, feature_indices):
    """Steps containing any of the given timeline indices (HiM filter result)."""
    wanted = set(feature_indices)
    return [i for i, features in enumerate(mapped) if any(f.index in wanted for f in features)]
