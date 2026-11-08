"""Version A — the reference instance (History in Motion, Veuskens et al.).

Runs in the second Fusion instance. It opens a copy of the designer's .f3d
from the example package and plays the tutorial on that real parametric
model, the way HiM does:

* rolling the timeline to the feature being shown and growing its
  genuine numeric parameters from ~0 to their value (distance, angle,
  radius, pattern spacing...), using a ghost of the previous geometry
  when reliable; features with no suitable parameter appear instantly;
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
        # HiM (SCF 2023, Section 6.2) dims unrelated geometry to reveal the
        # feature's input and result. Apply only in the unsaved reference copy.
        self.him.dim_others = True
        # Native HiM playback: one opaque Feature in front of a transparent
        # wireframe of actual geometry BEFORE that Feature was modeled.
        self.him.wireframe_context = True
        # Operations with no editable numeric parameter appear immediately.
        # They do not grow by an invented fade/scale transformation.
        self.him.instant_nonparametric = True
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
                package.populate_from_features(model.features(), model=model)
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

    def stop(self, restore_timeline=True):
        """Restore every temporary change (parameters, opacity, overlay)."""
        try:
            self.him._finish_feature()
            if restore_timeline and self.model is not None:
                self.model.restore()
        except Exception as error:
            self.last_error = "Could not restore the reference model: " + str(error)
            self.log(self.last_error)
            raise
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
        "parameter" (native Fusion parameter interpolation), "instant"
        (actual feature visible immediately), or "timeline" (unsupported
        feature kinds, shown without fabricated animation)."""
        plan = []
        design = self.model.design if self.model else None
        for features in self.mapped:
            items = []
            for feature in features:
                mode, params = (
                    "instant" if feature.is_sketch or feature.kind.startswith("Construction")
                    else "timeline"), []
                if not feature.is_sketch and not feature.kind.startswith("Construction"):
                    kind = animation_mode(feature.kind)
                    if kind == PARAMETRIC:
                        try:
                            params = [p.name for p in _model_parameters(
                                design, self.model.entity(feature), feature.kind)]
                        except Exception:
                            params = []
                        mode = "parameter" if params else "instant"
                    elif kind == FADE:
                        mode = "instant"
                items.append({"feature": feature.name, "kind": feature.kind,
                              "mode": mode, "parameters": params})
            plan.append(items)
        return plan

    # --- whole-model endpoints -----------------------------------------------------------
    def show_overview(self):
        """Present the complete designer model, shaded and with no ghost.

        Used before playback begins and after the full sequence finishes.
        This does not change the user's original .f3d or save the copy.
        """
        if not self.live:
            return
        self.stop(restore_timeline=False)  # restores parameter expressions and opacity
        self.model.go(self.model.end_state())
        self.current = ("overview",)
        try:
            self.app.activeViewport.refresh()
        except Exception:
            pass

    # --- playback -------------------------------------------------------------------------
    def _roll_after(self, feature):
        self.model.go(feature.index + 1)

    def frame(self, step_index, progress):
        """Show step ``step_index`` at ``progress`` (0..1) on the real model.
        Returns what is being shown ({"feature", "mode", ...}) or None."""
        if not self.live or not 0 <= step_index < len(self.mapped) or not self._active():
            return None
        items = animated(self.mapped[step_index])
        if not items and progress < 1.0:
            # Sketch/construction-only steps have no BRep parameter to grow.
            # Roll to their real completed Timeline state immediately,
            # rather than pretending an extrusion-like animation exists.
            if self.current != (step_index, "result"):
                self.show_result(step_index)
                self.current = (step_index, "result")
            features = self.mapped[step_index]
            return {"step": step_index,
                    "feature": features[-1].name if features else None,
                    "kind": features[-1].kind if features else None,
                    "mode": "instant", "parameters": []}
        if progress >= 1.0:
            # The FINAL step returns to the entire shaded model, not a
            # ghost/partial-timeline state. Intermediate steps preserve the
            # actual post-step model until the following Feature begins.
            if step_index == len(self.mapped) - 1:
                if self.current != ("overview",):
                    self.show_overview()
                return {"step": step_index, "feature": None, "mode": "overview"}
            if self.current != (step_index, "result"):
                self.show_result(step_index)
                self.current = (step_index, "result")
            return {"step": step_index, "feature": None, "mode": "result"}
        position, local = frame_target(self.mapped[step_index], progress)
        key = (step_index, position)
        try:
            if key != self.current:
                self.stop(restore_timeline=False)
                self._read_inputs([items[position]])
                # Exact pre-feature context is more informative than a ghost
                # copy of the finished model. Capture once, before rolling
                # to the native feature and animating its real parameters.
                if self.him.wireframe_context and self.him.dim_others:
                    self.model.go(items[position].index)
                    self.him.capture_ghost_context()
                self._roll_after(items[position])
                self.him.clip = [items[position]]
                self.him.active_position = None
                self.current = key
            self.him._render(Frame(0, local))
        except Exception as error:
            self.last_error = "{}: {}".format(items[position].name, error)
            self.log("HiM frame: " + self.last_error)
            try:
                self.show_overview()
            except Exception as restore_error:
                self.last_error += "; restoration failed: " + str(restore_error)
            self.current = (step_index, "error")
            return {"step": step_index, "feature": items[position].name, "mode": "error",
                    "fallback": self.last_error}
        status = self.him.status() or {}
        status["step"] = step_index
        return status

    def show_result(self, step_index):
        """The model as it is after this step (timeline rolled, nothing
        animated), with the step's geometry highlighted."""
        if not self.live:
            return
        self.stop(restore_timeline=False)
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

