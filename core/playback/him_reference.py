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
import time

import adsk.core
import adsk.fusion

from core import him_filter
from core.him_fusion import FusionTimelineModel, HiMController, _model_parameters
from core.him_motion import Frame, animation_mode, PARAMETRIC, FADE
from core.reference_plan import map_steps, animated, frame_target, steps_for_features
from .same_viewport import SameViewportPresenter, side_by_side_offset


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
        # Move the feature's real faces between frames instead of
        # recomputing the model every frame (pause recomputes natively).
        self.him.fast_motion = True
        self.document = None
        self.model = None
        self.mapped = []
        self.unmatched = []
        self.current = None
        self.filter_result = None
        self.source_name = ""
        self.plan = []              # per step: how each feature is shown
        self.last_error = ""
        self.last_timing = None
        # Same viewport: the user's Design stays active and editable; the
        # reference is drawn into it. The reference keeps its own document
        # and Timeline, never merged into the user's.
        self.same_viewport = True
        self.user_document = None
        self.presenter = SameViewportPresenter(self.log)

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
        user_document = self._user_document() if self.same_viewport else None
        manager = self.app.importManager
        options = manager.createFusionArchiveImportOptions(str(path))
        document = manager.importToNewDocument(options)
        if document is None:
            raise RuntimeError("Fusion could not open " + path.name)
        if user_document is None:
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
            if user_document is not None:
                self._activate(user_document)
            raise
        self.document = document
        self.model = model
        self.him.model_highlights = self.model.highlights     # blue inputs per feature
        self.mapped, self.unmatched = map_steps(package.data["steps"], self.model.features())
        self.source_name = path.name
        self.plan = self.animation_plan()
        self.model.go(self.model.end_state())
        if user_document is not None:
            # The user's Design is the active, editable workspace again.
            self._activate(user_document)
            self.user_document = user_document
            target = self._user_design()
            offset = side_by_side_offset(target, design, package.data.get("reference_offset_cm"))
            self.presenter.attach(design, target, offset)
            self.him.graphics_design = self._user_design
            self.him.display_offset = offset
            self.present()
        try:
            if self.him.auto_focus:
                self.app.activeViewport.fit()
        except Exception:
            pass
        return True

    # --- the user's document (same viewport) ---------------------------------------------
    def _user_document(self):
        """The user's active Design document; a new one if none is open."""
        document = None
        try:
            document = self.app.activeDocument
            if document is not None and not adsk.fusion.Design.cast(
                    document.products.itemByProductType("DesignProductType")):
                document = None
        except Exception:
            document = None
        if document is None:
            document = self.app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        return document

    @staticmethod
    def _activate(document):
        try:
            document.activate()
        except Exception:
            pass

    def _user_design(self):
        if self.user_document is None:
            return None
        try:
            return adsk.fusion.Design.cast(self.user_document.products.itemByProductType("DesignProductType"))
        except Exception:
            return None

    def present(self, changing=()):
        """Draw the reference's current state into the user's viewport."""
        if not self.presenter.attached:
            return
        if not getattr(self.user_document, "isValid", True):
            self.presenter.detach()
            raise RuntimeError("Your design was closed; load the tutorial again to show the reference")
        try:
            self.presenter.refresh(self.current, changing)
        except Exception as error:
            self.log("Reference display: " + str(error))
            raise

    def hide(self):
        """Remove the reference graphics from the user's design (e.g. before save)."""
        self.presenter.clear()

    def owns(self, entity):
        """True when ``entity`` (a selected face/edge/vertex) belongs to the
        reference copy, not to the user's own design."""
        if not self.live:
            return False
        try:
            body = entity.body if hasattr(entity, "body") else None
            if body is None:
                edges = getattr(entity, "edges", None)
                body = edges.item(0).body if edges is not None and edges.count else None
            return body.parentComponent.parentDesign == self.model.design
        except Exception:
            return False

    def close(self):
        self.stop()
        self.presenter.detach()
        self.him.graphics_design = None
        self.him.display_offset = (0.0, 0.0, 0.0)
        if self.document is not None:
            try:
                self.document.close(False)        # a copy: never saved
            except Exception:
                pass
        self.document = self.model = None
        self.user_document = None
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
        """Playback may run. Same viewport: while the reference copy is still
        open, whichever document is active (it only ever changes the copy).
        Otherwise only while the reference copy is the active document."""
        if self.document is None:
            return True
        try:
            if self.presenter.attached:
                return bool(self.document.isValid)
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
        self.present()
        try:
            if self.him.auto_focus and self._active():
                self.app.activeViewport.fit()
            self.app.activeViewport.refresh()
        except Exception:
            pass

    # --- playback -------------------------------------------------------------------------
    def _roll_after(self, feature):
        self.model.go(feature.index + 1)

    def frame(self, step_index, progress, settle=False):
        """Show step ``step_index`` at ``progress`` (0..1) on the real model.
        Returns what is being shown ({"feature", "mode", ...}) or None."""
        if not self.live or not 0 <= step_index < len(self.mapped) or not self._active():
            return None
        items = animated(self.mapped[step_index])
        if not items and progress < 1.0:
            # Sketch/construction-only steps have no BRep parameter to grow.
            # Roll to their real completed Timeline state; sketches are drawn
            # line by line from their actual curves (no invented geometry).
            sketches = self._sketch_entities(step_index)
            if self.current != (step_index, "sketch"):
                self.show_result(step_index, guidance=False)
                self.current = (step_index, "sketch")
            if sketches:
                try:
                    self.him.draw_sketch(sketches, progress)
                except Exception as error:
                    self.log("HiM sketch drawing: " + str(error))
                self.present()
            features = self.mapped[step_index]
            return {"step": step_index,
                    "feature": features[-1].name if features else None,
                    "kind": features[-1].kind if features else None,
                    "mode": "instant", "parameters": [], "drawing": bool(sketches)}
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
                self.present()
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
                if self.him.fast_motion:
                    self.model.go(items[position].index)
                    self.him.capture_motion_inputs(items[position])
                self._roll_after(items[position])
                self.him.clip = [items[position]]
                self.him.active_position = None
                self.current = key
            started = time.perf_counter()
            self.him._render(Frame(0, local), settle=settle)
            computed = time.perf_counter()
            self.present(changing=self._changing_tokens())
            self._note_timing(items[position], computed - started, time.perf_counter() - computed)
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

    def _sketch_entities(self, step_index):
        sketches = []
        for feature in self.mapped[step_index] if 0 <= step_index < len(self.mapped) else []:
            if feature.is_sketch:
                entity = self.model.entity(feature)
                if entity is not None:
                    sketches.append(entity)
        return sketches

    def show_result(self, step_index, guidance=True):
        """The model as it is after this step (timeline rolled, nothing
        animated), with the step's geometry highlighted."""
        if not self.live:
            return
        self.stop(restore_timeline=False)
        features = animated(self.mapped[step_index]) if 0 <= step_index < len(self.mapped) else []
        self._read_inputs(features)
        for feature in features:          # plane / axis for the manipulator arrows
            if self.him.fast_motion and feature.index not in self.him.inputs_by_index:
                self.model.go(feature.index)
                self.him.capture_motion_inputs(feature)
        if step_index >= len(self.mapped) - 1:
            self.model.go(self.model.end_state())        # the finished model
        elif self.mapped[step_index]:
            self._roll_after(self.mapped[step_index][-1])
        try:
            if not guidance:
                pass
            elif features:
                self.him.draw_guidance(features)
            else:
                # A sketch-only step: its finished sketch stays outlined in blue.
                sketches = self._sketch_entities(step_index)
                if sketches:
                    self.him.draw_sketch(sketches, 1.0)
        except Exception as error:
            self.log("HiM geometry guidance: " + str(error))
        self.present()

    SLOW_FRAME_SECONDS = 0.25

    def _note_timing(self, feature, compute_seconds, display_seconds):
        """Keep the last frame's timing; log slow frames so a slow model can
        be diagnosed (Fusion recompute vs drawing in the user's viewport)."""
        self.last_timing = {"feature": feature.name, "kind": feature.kind,
                            "compute_ms": round(compute_seconds * 1000),
                            "display_ms": round(display_seconds * 1000)}
        if compute_seconds + display_seconds > self.SLOW_FRAME_SECONDS:
            self.log("Slow frame {} ({}): recompute {} ms, reference display {} ms".format(
                feature.name, feature.kind, self.last_timing["compute_ms"],
                self.last_timing["display_ms"]))

    def _changing_tokens(self):
        """Bodies recomputed by the active parameter frame."""
        from .him_fusion import _token
        if self.him._moving(self.him.active):
            return set()                    # the native bodies are not being recomputed
        return {_token(b) for b in self.him.active.get("bodies", []) if _token(b)}

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

    def set_auto_focus(self, enabled):
        was_enabled = self.him.auto_focus
        self.him.auto_focus = bool(enabled)
        if self.him.auto_focus and not was_enabled and self._active():
            self.him.focus_feature()

    def set_dim(self, enabled):
        self.him.dim_others = bool(enabled)

    # --- HiM filtering ------------------------------------------------------------------------
    def filter(self, entity):
        """Selected geometry -> relevant features (HiM Algorithm 1) -> steps."""
        if not self.live:
            return None
        if self.presenter.attached and not self.owns(entity):
            return None          # the user's own geometry: never filter on it
        ref = FusionTimelineModel._ref(entity)
        if not ref:
            return None
        self.stop()
        self.model.go(self.model.end_state())
        result = him_filter.extract_relevant_features(self.model, ref)
        self.model.go(self.model.end_state())
        self.current = None
        self.present()
        self.filter_result = result
        return self._describe(result)

    def show_more(self):
        if not self.live or self.filter_result is None:
            return None
        self.stop()
        him_filter.show_more(self.model, self.filter_result)
        self.model.go(self.model.end_state())
        self.current = None
        self.present()
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

