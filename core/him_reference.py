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
from .him_fusion import FusionTimelineModel, HiMController, _model_parameters
from .him_motion import Frame, animation_mode, PARAMETRIC, FADE
from .reference_plan import map_steps, animated, frame_target, steps_for_features


class ReferenceSession:
    def __init__(self, app, ui, log=None):
        self.app, self.ui = app, ui
        self.log = log or (lambda *_: None)
        self.him = HiMController(app, ui, lambda *_: None, self.log,
                                 design_provider=lambda: self.model.design if self.model else None)
        self.document = None
        self.model = None
        self.mapped = []
        self.unmatched = []
        self.current = None
        self.filter_result = None
        self.source_name = ""
        self.plan = []              # per step: how each feature is shown
        self.last_error = ""

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
        try:
            design = adsk.fusion.Design.cast(document.products.itemByProductType("DesignProductType"))
            model = FusionTimelineModel(design)
            # A JSON+.f3d pair discovers the ACTUAL timeline after importing
            # a disposable document copy; no guessed feature indices.
            if getattr(package, "needs_populate", False):
                package.populate_from_features(model.features())
        except Exception:
            try:
                document.close(False)
            except Exception:
                pass
            raise
        self.document = document
        self.model = model
        self.him.model_highlights = self.model.highlights     # blue inputs per feature
        self.mapped, self.unmatched = map_steps(package.data["steps"], self.model.features())
        self.source_name = path.name
        self.plan = self.animation_plan()
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
        self.plan = []

    def stop(self):
        """Restore every temporary change (parameters, opacity, overlay)."""
        try:
            self.him._finish_feature()
        except Exception as error:
            self.last_error = "Could not restore the reference model: " + str(error)
            self.log(self.last_error)
        self.current = None

    def _active(self):
        """Only animate while the reference copy is the active document."""
        if self.document is None:
            return True
        try:
            return self.app.activeDocument == self.document
        except Exception:
            return False

    # --- how each step is shown -------------------------------------------------------
    def animation_plan(self):
        """Per step: [{feature, kind, mode, parameters}] where mode is
        "parameter" (native parameter animation), "visual" (fade/scale
        fallback) or "timeline" (shown by rolling the timeline only)."""
        plan = []
        design = self.model.design if self.model else None
        for features in self.mapped:
            items = []
            for feature in features:
                mode, params = "timeline", []
                if not feature.is_sketch:
                    kind = animation_mode(feature.kind)
                    if kind == PARAMETRIC:
                        try:
                            params = [p.name for p in _model_parameters(
                                design, self.model.entity(feature), feature.kind)]
                        except Exception:
                            params = []
                        mode = "parameter" if params else "visual"
                    elif kind == FADE:
                        mode = "visual"
                items.append({"feature": feature.name, "kind": feature.kind,
                              "mode": mode, "parameters": params})
            plan.append(items)
        return plan

    # --- playback -------------------------------------------------------------------------
    def _roll_after(self, feature):
        self.model.go(feature.index + 1)

    def frame(self, step_index, progress):
        """Show step ``step_index`` at ``progress`` (0..1) on the real model.
        Returns what is being shown ({"feature", "mode", ...}) or None."""
        if not self.live or not 0 <= step_index < len(self.mapped) or not self._active():
            return None
        items = animated(self.mapped[step_index])
        if progress >= 1.0 or not items:
            # End of the step: real parameter values, the model after it.
            if self.current != (step_index, "result"):
                self.show_result(step_index)
                self.current = (step_index, "result")
            return {"step": step_index, "feature": None, "mode": "result"}
        position, local = frame_target(self.mapped[step_index], progress)
        key = (step_index, position)
        try:
            if key != self.current:
                self.stop()
                self._read_inputs([items[position]])
                self._roll_after(items[position])
                self.him.clip = [items[position]]
                self.him.active_position = None
                self.current = key
            self.him._render(Frame(0, local))
        except Exception as error:
            self.last_error = "{}: {}".format(items[position].name, error)
            self.log("HiM frame: " + self.last_error)
            self.stop()
            try:
                self._roll_after(items[position])
            except Exception:
                pass
            self.current = (step_index, "error")
            return {"step": step_index, "feature": items[position].name, "mode": "error",
                    "fallback": str(error)}
        status = self.him.status() or {}
        status["step"] = step_index
        return status

    def show_result(self, step_index):
        """The model as it is after this step (timeline rolled, nothing
        animated), with the step's geometry highlighted."""
        if not self.live:
            return
        self.stop()
        features = animated(self.mapped[step_index]) if 0 <= step_index < len(self.mapped) else []
        self._read_inputs(features)
        if step_index >= len(self.mapped) - 1:
            self.model.go(self.model.end_state())        # the finished model
        elif self.mapped[step_index]:
            self._roll_after(self.mapped[step_index][-1])
        try:
            self.him.draw_guidance(features)
        except Exception as error:
            self.log("HiM geometry guidance: " + str(error))

    def _read_inputs(self, features):
        """Record each feature's input profile/edges (blue), once. The
        Fusion API reads them with the marker just before the feature."""
        self.him.model_highlights = self.model.highlights
        for feature in features:
            if feature.index in self.model.highlights:
                continue
            try:
                self.model.input_geometries(feature)
            except Exception as error:
                self.log("HiM inputs of {}: {}".format(feature.name, error))
            self.model.highlights.setdefault(feature.index, [])

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
