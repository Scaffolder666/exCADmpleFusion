"""Fusion glue for Design Reasoning Reuse.

Selecting a face, edge or vertex in the *user's own* model runs the HiM
filter read-only (the timeline marker is restored), then matches the user's
relevant features to decisions in every open design example. The reasoning
notebook is stored in the user's design attributes so it travels with the
.f3d file.
"""
import json

import adsk.core
import adsk.fusion

from . import reuse
from .notebook import Notebook, NotebookError, STANCES

ATTR_GROUP = "exCADmple"
ATTR_NAME = "reasoning_notebook"


class ReuseController:
    def __init__(self, app, ui, him, library, post, open_step):
        self.app, self.ui, self.him, self.library = app, ui, him, library
        self.post, self.open_step = post, open_step
        self.features = []
        self.notebook = Notebook(self._load, self._save)
        self._notebook_doc = self._doc_key()

    # --- notebook storage ---------------------------------------------------------
    def _design(self):
        return adsk.fusion.Design.cast(self.app.activeProduct)

    def _doc_key(self):
        design = self._design()
        try:
            return design.rootComponent.entityToken if design else ""
        except Exception:
            return ""

    def _load(self):
        design = self._design()
        if not design:
            return None
        attribute = design.attributes.itemByName(ATTR_GROUP, ATTR_NAME)
        return attribute.value if attribute else None

    def _save(self, text):
        design = self._design()
        if not design:
            raise NotebookError("Open your design to keep a reasoning notebook")
        if self._doc_key() != self._notebook_doc:
            raise NotebookError("The notebook belongs to another design; switch back to it first")
        design.attributes.add(ATTR_GROUP, ATTR_NAME, text)

    def document_changed(self):
        """Call when another design becomes active."""
        self._notebook_doc = self._doc_key()
        try:
            self.notebook.reload()
        except NotebookError as error:
            self.notebook.entries = []
            self.post("status", {"message": "Notebook unreadable: " + str(error), "error": True})
        self.features = []
        self.publish()

    # --- view -----------------------------------------------------------------------
    def refs(self):
        return reuse.collect_decisions(self.library.examples())

    def _ref(self, example_id, step_id):
        for ref in self.refs():
            if ref["example_id"] == example_id and ref["step_id"] == step_id:
                return ref
        raise ValueError("Decision not found in the open examples")

    def _feature(self, key):
        if not key:
            return None
        for feature in self.features:
            if feature.get("key") == key:
                return feature
        return None

    def publish(self, extra=None):
        refs = self.refs()
        matched = reuse.match_features(self.features, refs)
        for item in matched:
            for match in item["matches"]:
                entry = self.notebook.stance_for(match["ref"]["example_id"], match["ref"]["step_id"],
                                                 item["feature"].get("key", ""))
                match["stance"] = entry["stance"] if entry else None
                match["note"] = entry["note"] if entry else ""
        view = {
            "selection": self.him.selection_label if self.features else "",
            "features": matched,
            "topics": reuse.by_topic(refs),
            "examples": self.library.listing(),
            "notebook": self.notebook.entries,
            "summary": self.notebook.summary(),
            "stances": list(STANCES),
        }
        if extra:
            view.update(extra)
        self.post("reuse_view", view)

    # --- events ---------------------------------------------------------------------
    def explain(self, entity):
        """Selection in the user's model -> HiM features -> matched decisions."""
        self.him.explain(entity)
        described = self.him.describe()
        self.features = described["features"]
        self.publish()

    def record(self, body):
        stance = body.get("stance")
        if stance not in STANCES:
            raise ValueError("Choose adopt, adapt, not use or undecided")
        ref = self._ref(body.get("example_id"), body.get("step_id"))
        feature = self._feature(body.get("feature_key"))
        comparison = reuse.compare(ref, feature.get("parameters", [])) if feature else None
        self.notebook.record(stance, ref, body.get("note", ""), feature,
                             comparison["user_value"] if comparison else "")
        self.publish()
        return "Recorded in your reasoning notebook (saved with this design)."

    def remove(self, entry_id):
        self.notebook.remove(entry_id)
        self.publish()

    def watch(self, example_id, step_id):
        ref = self._ref(example_id, step_id)
        self.open_step(ref["example_id"], ref["step_index"])

    def export(self, fmt):
        dialog = self.ui.createFileDialog()
        dialog.title = "Export reasoning notebook"
        dialog.filter = "CSV (*.csv)" if fmt == "csv" else "JSON (*.json)"
        dialog.initialFilename = "reasoning-notebook." + ("csv" if fmt == "csv" else "json")
        if dialog.showSave() != adsk.core.DialogResults.DialogOK:
            return "Export canceled."
        if fmt == "csv":
            text = self.notebook.to_csv()
        else:
            design = self._design()
            text = json.dumps({
                "design": design.parentDocument.name if design else "",
                "examples": self.library.listing(),
                "summary": self.notebook.summary(),
                "entries": self.notebook.entries,
            }, indent=2, ensure_ascii=False)
        with open(dialog.filename, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        return "Notebook exported to " + dialog.filename
