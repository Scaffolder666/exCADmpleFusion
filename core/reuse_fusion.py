"""Fusion glue for Design Reasoning Reuse.

Selecting a face, edge or vertex in the *user's own* model runs the HiM
filter read-only (the timeline marker is restored), then matches the user's
relevant features to decisions in every open design example.
"""
from . import reuse


class ReuseController:
    def __init__(self, app, ui, him, library, post, open_step):
        self.app, self.ui, self.him, self.library = app, ui, him, library
        self.post, self.open_step = post, open_step
        self.features = []

    def document_changed(self):
        """Call when another design becomes active."""
        self.features = []
        self.publish()

    def refs(self):
        return reuse.collect_decisions(self.library.examples())

    def _ref(self, example_id, step_id):
        for ref in self.refs():
            if ref["example_id"] == example_id and ref["step_id"] == step_id:
                return ref
        raise ValueError("Decision not found in the open examples")

    def publish(self, extra=None):
        refs = self.refs()
        view = {
            "selection": self.him.selection_label if self.features else "",
            "features": reuse.match_features(self.features, refs),
            "topics": reuse.by_topic(refs),
            "examples": self.library.listing(),
        }
        if extra:
            view.update(extra)
        self.post("reuse_view", view)

    def explain(self, entity):
        """Selection in the user's model -> HiM features -> matched decisions."""
        self.him.explain(entity)
        self.features = self.him.describe()["features"]
        self.publish()

    def watch(self, example_id, step_id):
        ref = self._ref(example_id, step_id)
        self.open_step(ref["example_id"], ref["step_index"])
