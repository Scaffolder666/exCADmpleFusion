"""History in Motion (Veuskens et al., SCF 2023) feature filtering.

Pure Python implementation of the paper's Algorithm 1 and Algorithm 2, written
against a small adapter interface so it can be unit tested without Fusion.

Geometry is passed around as opaque *references* that the adapter resolves at
a given timeline *state*. A state is the number of timeline items that are
applied: ``state == feature.index`` is the model just before that feature,
``state == feature.index + 1`` is just after it. Rolling the timeline back
invalidates live BRep objects in Fusion, so references must stay opaque.

Adapter interface (duck typed)::

    end_state() -> int
    features() -> list of FeatureInfo, in timeline order
    extract_faces(ref, state) -> list of face refs       # Algorithm 2, l.14
    created(feature, face_ref, state) -> bool            # feature.faces at state
    input_geometries(feature) -> list of InputRef        # Algorithm 2, l.28
    sketch_base_face(sketch_ref) -> face ref | None      # None: ground plane
    signature(ref, state) -> hashable | None             # None: not present
"""
from dataclasses import dataclass, field

MAX_ITERATIONS = 64


@dataclass(frozen=True)
class FeatureInfo:
    index: int          # timeline index
    name: str
    kind: str           # Fusion objectType or short feature kind
    key: str = ""       # stable feature identity (entity token)

    @property
    def is_sketch(self):
        return self.kind.lower().endswith("sketch")


@dataclass(frozen=True)
class InputRef:
    """An input geometry of a feature. kind: face, edge, vertex, body,
    feature, sketch. ``state`` is the timeline state where ``ref`` is valid."""
    kind: str
    ref: object
    state: int
    feature: FeatureInfo = None   # for kind == feature / sketch


@dataclass
class Basis:
    """A sketch on which the filtered features build (paper Section 4.3)."""
    sketch: FeatureInfo
    face: object = None           # base face ref when sketch is on a face
    state: int = 0

    @property
    def on_ground_plane(self):
        return self.face is None


@dataclass
class FilterResult:
    features: list = field(default_factory=list)   # reverse timeline order
    roles: dict = field(default_factory=dict)      # index -> created/modified/input
    bases: list = field(default_factory=list)      # sketches reached
    levels: dict = field(default_factory=dict)     # index -> show-more depth
    truncated: bool = False

    def can_show_more(self):
        return any(not basis.on_ground_plane for basis in self.pending_bases())

    def pending_bases(self):
        return [b for b in self.bases if not getattr(b, "expanded", False)]

    def as_dict(self):
        return {
            "features": [{
                "timeline_index": f.index, "name": f.name, "kind": f.kind,
                "key": f.key, "role": self.roles.get(f.index, "created"),
                "level": self.levels.get(f.index, 0),
            } for f in self.features],
            "bases": [{
                "timeline_index": b.sketch.index, "name": b.sketch.name,
                "on_ground_plane": b.on_ground_plane,
                "expanded": bool(getattr(b, "expanded", False)),
            } for b in self.bases],
            "can_show_more": self.can_show_more(),
            "truncated": self.truncated,
        }


class _Collector:
    def __init__(self, model, result, level):
        self.model = model
        self.result = result
        self.level = level
        self.by_index = {f.index: f for f in result.features}
        self.expanded_features = set()
        self.seen_faces = set()
        self.seen_sketches = {b.sketch.index for b in result.bases}

    def add(self, feature, role):
        if feature.index not in self.by_index:
            self.by_index[feature.index] = feature
            self.result.roles[feature.index] = role
            self.result.levels[feature.index] = self.level

    def expand(self, feature, new_items):
        """get_input_geometries() for one feature; sketches stop the search."""
        if feature.index in self.expanded_features:
            return
        self.expanded_features.add(feature.index)
        for item in self.model.input_geometries(feature):
            if item.kind == "sketch":
                sketch = item.feature
                if sketch is not None and sketch.index not in self.seen_sketches:
                    self.seen_sketches.add(sketch.index)
                    face = self.model.sketch_base_face(item.ref)
                    self.result.bases.append(Basis(sketch, face, sketch.index))
            elif item.kind == "feature":
                # e.g. a pattern of features: seed features fully define it.
                if item.feature is not None:
                    self.add(item.feature, "input")
                    new_items.append(("feature", item.feature, None))
            elif item.kind in ("face", "edge", "vertex"):
                for face in self.model.extract_faces(item.ref, item.state):
                    new_items.append(("face", face, item.state))
            # bodies are deliberately not expanded: a whole body would pull in
            # every feature of the part and defeat the filtering.

    def creation_features(self, face, state):
        """Algorithm 2 find_creation_features for one face at one state."""
        found = []
        for feature in self.model.features():
            if feature.index >= state or feature.is_sketch:
                continue
            if self.model.created(feature, face, state):
                found.append(feature)
        return found

    def run(self, items):
        iterations = 0
        while items:
            iterations += 1
            if iterations > MAX_ITERATIONS:
                self.result.truncated = True
                break
            new_items = []
            for kind, ref, state in items:
                if kind == "feature":
                    self.expand(ref, new_items)
                    continue
                marker = (state, self.model.face_key(ref, state)
                          if hasattr(self.model, "face_key") else id(ref))
                if marker in self.seen_faces:
                    continue
                self.seen_faces.add(marker)
                for feature in self.creation_features(ref, state):
                    self.add(feature, "created")
                    self.expand(feature, new_items)
            items = new_items


def _modified_by(model, selected_ref, end_state):
    """Algorithm 1 lines 17-21: compare the selected entity before and after
    every feature. Signatures: vertex/edge coordinates, face edge and vertex
    counts, area and centroid (paper Section 6.1)."""
    signatures = [model.signature(selected_ref, state) for state in range(end_state + 1)]
    modified = []
    by_state = {f.index: f for f in model.features()}
    for state in range(end_state):
        before, after = signatures[state], signatures[state + 1]
        if before is not None and after is not None and before != after:
            feature = by_state.get(state)
            if feature is not None and not feature.is_sketch:
                modified.append(feature)
    return modified


def _sorted(result, collector):
    result.features = sorted(collector.by_index.values(), key=lambda f: f.index, reverse=True)
    return result


def extract_relevant_features(model, selected_ref, include_modifications=True):
    """Algorithm 1. Returns a FilterResult, newest feature first."""
    end = model.end_state()
    result = FilterResult()
    collector = _Collector(model, result, 0)
    items = [("face", face, end) for face in model.extract_faces(selected_ref, end)]
    collector.run(items)
    if include_modifications:
        for feature in _modified_by(model, selected_ref, end):
            collector.add(feature, "modified")
    return _sorted(result, collector)


def show_more(model, result):
    """Section 4.3 "show more": trace features that created the faces on which
    the reached sketches are built; repeat until sketches lie on a ground
    plane. Appends to ``result`` in place and returns it."""
    pending = [b for b in result.pending_bases() if not b.on_ground_plane]
    if not pending:
        return result
    level = max(result.levels.values(), default=0) + 1
    collector = _Collector(model, result, level)
    items = []
    for basis in pending:
        basis.expanded = True
        items.append(("face", basis.face, basis.state))
    for basis in result.bases:
        if basis.on_ground_plane:
            basis.expanded = True
    collector.run(items)
    return _sorted(result, collector)
