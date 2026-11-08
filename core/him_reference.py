"""Version A — the reference instance (as in History in Motion).

Runs in the second Fusion instance. It opens a copy of the designer's .f3d
from the tutorial package. For each step the timeline is rolled to the end
of that step, so the user can rotate and inspect the designer's real model
as it was after the step. Selecting a face, edge or vertex runs HiM's
Algorithm 1 on the model and lists the steps containing the features that
made or changed it; "show more" follows the supporting sketches' faces.
The copy is never saved and no parameter is changed.
If a package has no source model, the recorded step geometry is drawn
instead (Custom Graphics), and the panel says so.
"""
import adsk.core
import adsk.fusion

from . import him_filter
from .him_fusion import FusionTimelineModel
from .reference_plan import map_steps, steps_for_features


class ReferenceSession:
    def __init__(self, app, ui, log=None):
        self.app, self.ui = app, ui
        self.log = log or (lambda *_: None)
        self.document = None
        self.model = None
        self.mapped = []
        self.unmatched = []
        self.shown = None
        self.filter_result = None
        self.source_name = ""

    @property
    def live(self):
        return self.model is not None

    # --- opening the designer's model ------------------------------------------------
    def open(self, package):
        """Open a fresh copy of the package's .f3d. Returns True when the
        tutorial can be shown on the real model."""
        self.close()
        path = package.source_model_path()
        if path is None:
            return False
        manager = self.app.importManager
        options = manager.createFusionArchiveImportOptions(str(path))
        document = manager.importToNewDocument(options)
        if document is None:
            raise RuntimeError("Fusion could not open " + path.name)
        document.activate()
        design = adsk.fusion.Design.cast(document.products.itemByProductType("DesignProductType"))
        self.document = document
        self.model = FusionTimelineModel(design)
        self.mapped, self.unmatched = map_steps(package.data["steps"], self.model.features())
        self.source_name = path.name
        self.model.go(self.model.end_state())
        try:
            self.app.activeViewport.fit()
        except Exception:
            pass
        return True

    def close(self):
        if self.document is not None:
            try:
                self.document.close(False)        # a copy: never saved
            except Exception:
                pass
        self.document = self.model = None
        self.mapped, self.unmatched, self.filter_result = [], [], None
        self.shown = None

    def stop(self):
        """Nothing is animated; kept for the add-in's save/stop hooks."""
        self.shown = None

    # --- showing a step ----------------------------------------------------------------
    def show_result(self, step_index):
        """The designer's model as it is after this step (timeline rolled)."""
        if not self.live or step_index == self.shown or not 0 <= step_index < len(self.mapped):
            return
        self.shown = step_index
        if step_index >= len(self.mapped) - 1:
            self.model.go(self.model.end_state())        # the finished model
        elif self.mapped[step_index]:
            self.model.go(self.mapped[step_index][-1].index + 1)

    # --- HiM filtering ------------------------------------------------------------------------
    def filter(self, entity):
        """Selected geometry -> relevant features (HiM Algorithm 1) -> steps."""
        if not self.live:
            return None
        ref = FusionTimelineModel._ref(entity)
        if not ref:
            return None
        self.shown = None
        self.model.go(self.model.end_state())
        result = him_filter.extract_relevant_features(self.model, ref)
        self.model.go(self.model.end_state())
        self.filter_result = result
        return self._describe(result)

    def show_more(self):
        if not self.live or self.filter_result is None:
            return None
        self.shown = None
        him_filter.show_more(self.model, self.filter_result)
        self.model.go(self.model.end_state())
        return self._describe(self.filter_result)

    def _describe(self, result):
        roles = result.roles
        steps = steps_for_features(self.mapped, [f.index for f in result.features])
        tags = {}
        for i in steps:
            kinds = {roles.get(f.index) for f in self.mapped[i] if f.index in roles}
            tags[i] = ("changed here" if kinds & {"created", "modified"} else "builds on")
        return {"steps": steps, "tags": tags,
                "features": [f.name for f in result.features],
                "can_show_more": result.can_show_more()}
