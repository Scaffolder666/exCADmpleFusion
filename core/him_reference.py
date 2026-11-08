"""Version A — the reference instance (History in Motion, Veuskens et al.).

Runs in the second Fusion instance. It opens a copy of the designer's .f3d
from the example package and plays the tutorial on that real parametric
model, the way HiM does:

* rolling the timeline to the feature being shown and growing its
  parameters from ~0 to their value (distance, angle, radius, pattern
  spacing...), with other bodies made transparent and the profile / edges
  highlighted; parameter-less features fade in;
* selecting a face, edge or vertex runs HiM's Algorithm 1 on the model and
  filters the tutorial to the steps containing those features; "show more"
  follows the supporting sketches' faces.

The copy is never saved. Every changed parameter is restored.
If a package has no source model, the recorded step geometry is drawn
instead (Custom Graphics), and the panel says so.
"""
import adsk.core
import adsk.fusion

from . import him_filter
from .him_fusion import FusionTimelineModel, HiMController
from .him_motion import Frame
from .reference_plan import map_steps, animated, frame_target, steps_for_features


class ReferenceSession:
    def __init__(self, app, ui, log=None):
        self.app, self.ui = app, ui
        self.log = log or (lambda *_: None)
        self.him = HiMController(app, ui, lambda *_: None, self.log)
        self.document = None
        self.model = None
        self.mapped = []
        self.unmatched = []
        self.current = None
        self.filter_result = None
        self.source_name = ""

    @property
    def live(self):
        return self.model is not None

    # --- opening the designer's model ------------------------------------------------
    def open(self, package):
        """Open a fresh copy of the package's .f3d. Returns True when the
        tutorial can play on the real model."""
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
        self.stop()
        if self.document is not None:
            try:
                self.document.close(False)        # a copy: never saved
            except Exception:
                pass
        self.document = self.model = None
        self.mapped, self.unmatched, self.filter_result = [], [], None

    def stop(self):
        try:
            self.him._finish_feature()
        except Exception as error:
            self.log("HiM restore: " + str(error))
        self.current = None

    # --- playback -------------------------------------------------------------------------
    def _roll_after(self, feature):
        self.model.go(feature.index + 1)

    def frame(self, step_index, progress):
        """Show step ``step_index`` at ``progress`` (0..1) on the real model."""
        if not self.live or not 0 <= step_index < len(self.mapped):
            return
        items = animated(self.mapped[step_index])
        position, local = frame_target(self.mapped[step_index], progress)
        if position is None:
            self.show_result(step_index)
            return
        key = (step_index, position)
        if key != self.current:
            self.stop()
            self._roll_after(items[position])
            self.him.clip = [items[position]]
            self.him.active_position = None
            self.current = key
        self.him._render(Frame(0, local))

    def show_result(self, step_index):
        """The model as it is after this step (timeline rolled, nothing animated)."""
        if not self.live:
            return
        self.stop()
        if step_index >= len(self.mapped) - 1:
            self.model.go(self.model.end_state())        # the finished model
        elif self.mapped[step_index]:
            self._roll_after(self.mapped[step_index][-1])

    def set_dim(self, enabled):
        self.him.dim_others = bool(enabled)

    # --- HiM filtering ------------------------------------------------------------------------
    def filter(self, entity):
        """Selected geometry -> relevant features (HiM Algorithm 1) -> steps."""
        if not self.live:
            return None
        ref = FusionTimelineModel._ref(entity)
        if not ref:
            return None
        self.stop()
        self.model.go(self.model.end_state())
        result = him_filter.extract_relevant_features(self.model, ref)
        self.model.go(self.model.end_state())
        self.filter_result = result
        return self._describe(result)

    def show_more(self):
        if not self.live or self.filter_result is None:
            return None
        self.stop()
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
