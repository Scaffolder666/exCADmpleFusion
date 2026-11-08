"""Autodesk Fusion side of History in Motion.

* ``FusionTimelineModel`` implements the adapter interface of
  ``core.him_filter`` on a live parametric Design: it rolls the timeline marker
  to the states the algorithm asks for and always restores the marker.
* ``HiMController`` animates the filtered features *in the user's design* by
  temporarily varying their ModelParameters from ~0 to the actual value
  (paper Section 6.2), dims other bodies, highlights the input edge/profile,
  and uses a scale/opacity effect for features without parameters. Every
  changed parameter expression is journaled and restored.

The paper renders on a copy in a second Fusion instance connected with web
sockets. Fusion offers no in-process second 3D view, so this add-in animates
in place and restores; see README "HiM implementation notes".
"""
import time

import adsk.core
import adsk.fusion

from . import him_filter
from .him_filter import FeatureInfo, InputRef
from .him_motion import (Playback, RestoreJournal, animation_mode, parameter_paths,
                         interpolate, short_kind, PARAMETRIC, FADE, NONE)
from .focus import OpacityFocus, FocusError
from .him_wireframe import capture_before_feature, can_isolate_feature, WireframeOverflow

GEOMETRY_TYPES = (("face", adsk.fusion.BRepFace), ("edge", adsk.fusion.BRepEdge),
                  ("vertex", adsk.fusion.BRepVertex))
INPUT_PROPERTIES = (
    "profile", "profiles", "axis", "edgeSets", "inputEntities", "inputFaces",
    "inputCylindricalFace", "mirrorPlane", "splittingTool", "splitBodies",
    "targetBody", "toolBodies", "sketchPoints", "loftSections", "path",
    "extentOne.toEntity", "extentTwo.toEntity", "extentDefinition.toEntity",
    "startExtent.profilePlane", "plane", "neutralPlane",
)
MAX_TIMELINE = 600
HIGHLIGHT = (37, 99, 235, 255)  # blue: recorded feature input / target edges
CHANGE_HIGHLIGHT = (20, 184, 166, 255)  # teal: geometry affected by feature
GHOST_WIREFRAME = (155, 164, 175, 255)  # light gray: true BRep edge curves
GHOST_SURFACE_OPACITY = 0.001         # Fusion keeps native topology selectable


def _get_path(obj, path):
    """Evaluate 'a.b' / 'edgeSets*.radius' safely; returns a list of values."""
    values = [obj]
    for part in path.split("."):
        each = part.endswith("*")
        name = part.rstrip("*")
        next_values = []
        for value in values:
            try:
                attr = getattr(value, name, None)
            except Exception:
                attr = None
            if attr is None:
                continue
            if each:
                next_values.extend(_items(attr))
            else:
                next_values.append(attr)
        values = next_values
    return values


def _items(collection, limit=2000):
    if collection is None:
        return []
    if hasattr(collection, "count") and hasattr(collection, "item"):
        try:
            return [collection.item(i) for i in range(min(collection.count, limit))]
        except Exception:
            return []
    if isinstance(collection, (list, tuple)):
        return list(collection)
    return [collection]


def _token(entity):
    try:
        return entity.entityToken or ""
    except Exception:
        return ""


def _geometry_kind(entity):
    for kind, cls in GEOMETRY_TYPES:
        try:
            if cls.cast(entity):
                return kind
        except Exception:
            pass
    return None


def _round_point(point, digits=5):
    return (round(point.x, digits), round(point.y, digits), round(point.z, digits))


class FusionTimelineModel:
    """Adapter for core.him_filter on a live Fusion Design."""

    def __init__(self, design):
        if not design:
            raise ValueError("Open a Fusion Design first")
        if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
            raise ValueError("History in Motion needs a parametric design with a timeline")
        self.design = design
        self.timeline = design.timeline
        if self.timeline.count > MAX_TIMELINE:
            raise ValueError("Timeline has more than {} items".format(MAX_TIMELINE))
        self.objects = {}
        self._features = []
        self._flatten(self.timeline)
        self._end = (max(self.objects) + 1) if self.objects else 0
        self._state = None
        self._face_cache = {}
        self.highlights = {}       # feature index -> list of Curve3D
        self._original_marker = self.timeline.markerPosition
        self._was_at_end = self._original_marker >= self.timeline.count

    def _flatten(self, collection):
        for obj in _items(collection):
            try:
                if obj.isGroup:
                    self._flatten(adsk.fusion.TimelineGroup.cast(obj))
                    continue
            except Exception:
                pass
            try:
                entity = obj.entity
                index = obj.index
            except Exception:
                continue
            if entity is None:
                continue
            self.objects[index] = obj
            kind = short_kind(getattr(entity, "objectType", ""))
            self._features.append(FeatureInfo(index, getattr(entity, "name", "") or kind,
                                              kind, _token(entity)))
        self._features.sort(key=lambda f: f.index)

    # --- timeline state --------------------------------------------------------
    def go(self, state):
        if state == self._state:
            return
        self._face_cache.clear()
        if state >= self._end:
            self.timeline.moveToEnd()
        elif state in self.objects:
            self.objects[state].rollTo(True)
        else:
            earlier = [i for i in self.objects if i < state]
            if earlier:
                self.objects[max(earlier)].rollTo(False)
            else:
                self.timeline.markerPosition = 0
        self._state = state

    def restore(self):
        """Put the marker back where the user had it."""
        self._face_cache.clear()
        self._state = None
        if self._was_at_end:
            self.timeline.moveToEnd()
        else:
            self.timeline.markerPosition = self._original_marker

    # --- adapter interface ----------------------------------------------------
    def end_state(self):
        return self._end

    def features(self):
        return self._features

    def entity(self, feature):
        obj = self.objects.get(feature.index)
        return obj.entity if obj else None

    @staticmethod
    def _ref(entity):
        kind = _geometry_kind(entity)
        token = _token(entity)
        return (kind, token) if kind and token else None

    def ref_of(self, entity):
        return FusionTimelineModel._ref(entity)

    def resolve(self, ref, state):
        if not ref:
            return None
        kind, token = ref
        self.go(state)
        cls = dict(GEOMETRY_TYPES)[kind]
        try:
            for candidate in self.design.findEntityByToken(token) or []:
                if cls.cast(candidate):
                    return candidate
        except Exception:
            return None
        return None

    def face_key(self, ref, state):
        return ref

    def extract_faces(self, ref, state):
        entity = self.resolve(ref, state)
        if entity is None:
            return []
        faces = []
        if ref[0] == "face":
            faces = [entity]
        elif ref[0] == "edge":
            faces = _items(entity.faces)
        else:
            for edge in _items(entity.edges):
                faces.extend(_items(edge.faces))
        refs = []
        for face in faces:
            item = self.ref_of(face)
            if item and item not in refs:
                refs.append(item)
        return refs

    def created(self, feature, face_ref, state):
        face = self.resolve(face_ref, state)
        if face is None:
            return False
        key = (feature.index, state)
        if key not in self._face_cache:
            entity = self.entity(feature)
            self._face_cache[key] = _items(getattr(entity, "faces", None)) if entity else []
        for candidate in self._face_cache[key]:
            try:
                if candidate == face:
                    return True
            except Exception:
                continue
        return False

    def _feature_info(self, entity):
        try:
            index = entity.timelineObject.index
        except Exception:
            return None
        for feature in self._features:
            if feature.index == index:
                return feature
        return None

    def input_geometries(self, feature):
        """Typed inputs, read with the marker right before the feature, as the
        Fusion API requires for profiles and edges."""
        self.go(feature.index)
        entity = self.entity(feature)
        if entity is None:
            return []
        values = []
        for path in INPUT_PROPERTIES:
            for value in _get_path(entity, path):
                values.extend(_items(value))
        # Edge sets and loft sections wrap their entities.
        expanded = []
        for value in values:
            if _geometry_kind(value) is None:
                inner = None
                for attr in ("edges", "entities", "entity"):
                    try:
                        inner = getattr(value, attr, None)
                    except Exception:
                        inner = None
                    if inner is not None:
                        break
                if inner is not None:
                    expanded.extend(_items(inner))
                    continue
            expanded.append(value)
        inputs, curves = [], []
        for value in expanded:
            kind = _geometry_kind(value)
            if kind:
                ref = self.ref_of(value)
                if ref:
                    inputs.append(InputRef(kind, ref, feature.index))
                if kind == "edge":
                    try:
                        curves.append(value.geometry)
                    except Exception:
                        pass
                continue
            sketch = None
            try:
                sketch = adsk.fusion.Sketch.cast(value) or getattr(value, "parentSketch", None)
            except Exception:
                sketch = None
            if sketch:
                info = self._feature_info(sketch)
                if info:
                    inputs.append(InputRef("sketch", _token(sketch), feature.index, info))
                curves.extend(self._profile_curves(value))
                continue
            try:
                if getattr(value, "objectType", "").endswith("Feature") and value.timelineObject:
                    info = self._feature_info(value)
                    if info and info.index < feature.index:
                        inputs.append(InputRef("feature", None, feature.index, info))
                    continue
            except Exception:
                pass
            try:
                if adsk.fusion.BRepBody.cast(value):
                    inputs.append(InputRef("body", _token(value), feature.index))
            except Exception:
                pass
        if curves:
            self.highlights[feature.index] = curves
        return inputs

    @staticmethod
    def _profile_curves(value):
        curves = []
        profile = None
        try:
            profile = adsk.fusion.Profile.cast(value)
        except Exception:
            profile = None
        if not profile:
            return curves
        for loop in _items(profile.profileLoops):
            for curve in _items(loop.profileCurves):
                try:
                    curves.append(curve.sketchEntity.worldGeometry)
                except Exception:
                    pass
        return curves

    def sketch_base_face(self, sketch_token):
        try:
            for sketch in self.design.findEntityByToken(sketch_token) or []:
                sketch = adsk.fusion.Sketch.cast(sketch)
                if not sketch:
                    continue
                face = adsk.fusion.BRepFace.cast(sketch.referencePlane)
                return self.ref_of(face) if face else None
        except Exception:
            return None
        return None

    def signature(self, ref, state):
        entity = self.resolve(ref, state)
        if entity is None:
            return None
        try:
            if ref[0] == "face":
                return (entity.edges.count, entity.vertices.count,
                        round(entity.area, 6), _round_point(entity.centroid))
            if ref[0] == "edge":
                return (_round_point(entity.startVertex.geometry),
                        _round_point(entity.endVertex.geometry))
            return _round_point(entity.geometry)
        except Exception:
            return None


def _model_parameters(design, feature_entity, object_type):
    """ModelParameters to animate: only the registry paths of this feature
    kind (core.him_motion.FEATURES). Paths that do not lead to a
    ModelParameter for this extent type are skipped, as are parameters whose
    value is zero (nothing to grow). There is deliberately no generic
    "every length parameter" fallback: it could animate a parameter that
    does not drive this operation."""
    params, seen = [], set()
    for path in parameter_paths(object_type):
        for value in _get_path(feature_entity, path):
            param = adsk.fusion.ModelParameter.cast(value)
            if not param:
                continue
            try:
                name, number = param.name, float(param.value)
            except Exception:
                continue
            if name in seen or number == 0 or number != number:
                continue
            seen.add(name)
            params.append(param)
    return params


def _feature_failed(entity):
    """True when Fusion reports the feature in an error state."""
    states = getattr(adsk.fusion, "FeatureHealthStates", None)
    error = getattr(states, "ErrorFeatureHealthState", None) if states else None
    if error is None:
        return False
    try:
        return entity.healthState == error
    except Exception:
        return False


def all_feature_parameters(design, feature_entity):
    result = []
    try:
        params = design.allParameters
        for i in range(params.count):
            param = adsk.fusion.ModelParameter.cast(params.item(i))
            if not param:
                continue
            try:
                if param.createdBy == feature_entity:
                    result.append(param)
            except Exception:
                continue
    except Exception:
        pass
    return result


def _center(bodies):
    """Centre of the union of the bodies' bounding boxes."""
    lo, hi = [float("inf")] * 3, [float("-inf")] * 3
    for body in bodies:
        try:
            box = body.boundingBox
            for i, attr in enumerate("xyz"):
                lo[i] = min(lo[i], getattr(box.minPoint, attr))
                hi[i] = max(hi[i], getattr(box.maxPoint, attr))
        except Exception:
            continue
    if lo[0] == float("inf"):
        return (0.0, 0.0, 0.0)
    return tuple((lo[i] + hi[i]) / 2 for i in range(3))


class HiMController:
    """Owns one filtering result and its animation."""

    def __init__(self, app, ui, post, log=None, design_provider=None):
        self.app, self.ui, self.post = app, ui, post
        # Version A passes the reference copy's design here, so animation
        # never touches whatever document happens to be active.
        self._design_provider = design_provider
        self.log = log or (lambda *_: None)
        self.result = None
        self.clip = []
        self.playback = Playback(0)
        self.journal = RestoreJournal()
        self.focus = OpacityFocus(self._resolve_body, self._document_key)
        self.group = None
        self.ghost_group = None       # persistent backdrop for ONE active Feature
        self.pending_ghost = None     # captured at Timeline marker BEFORE feature
        self.wireframe_context = False  # opt in only on the disposable reference copy
        self.seconds = 4.0
        self.selected_ref = None
        self.selection_label = ""
        self.active_position = None
        self.active = {}            # prepared data of the feature being animated
        self.last_frame_seconds = None
        self.dim_others = False
        # Inspect mode animates the *user's own* features in place (paper
        # behaviour). Off by default: the user's model is the main line.
        self.inspect = False
        self.auto_play = True
        self.busy = False
        self.model_highlights = {}

    # --- helpers --------------------------------------------------------------
    def design(self):
        if self._design_provider is not None:
            return self._design_provider()
        return adsk.fusion.Design.cast(self.app.activeProduct)

    def _document_key(self):
        design = self.design()
        try:
            return design.rootComponent.entityToken if design else ""
        except Exception:
            return ""

    def _resolve_body(self, token):
        design = self.design()
        try:
            for body in design.findEntityByToken(token) or []:
                if adsk.fusion.BRepBody.cast(body):
                    return body
        except Exception:
            pass
        return None

    def _refresh(self):
        try:
            self.app.activeViewport.refresh()
        except Exception:
            pass

    def _feature_entity(self, feature):
        design = self.design()
        if not design:
            return None
        try:
            for entity in design.findEntityByToken(feature.key) or []:
                return entity
        except Exception:
            pass
        try:
            return design.timeline.item(feature.index).entity
        except Exception:
            return None

    # --- filtering ----------------------------------------------------------------
    def explain(self, entity):
        """Selection of a face/edge/vertex -> filtered features + animation."""
        ref = FusionTimelineModel._ref(entity)
        if not ref:
            raise ValueError("Select a single face, edge or vertex")
        if ref == self.selected_ref and self.result is not None:
            return      # recompute during animation re-reports the selection
        self.stop()
        design = self.design()
        model = FusionTimelineModel(design)
        self.busy = True
        started = time.time()
        try:
            result = him_filter.extract_relevant_features(model, ref)
        finally:
            try:
                model.restore()
            finally:
                self.busy = False
        self.model_highlights = model.highlights
        self.selected_ref = ref
        self.selection_label = ref[0].capitalize()
        self.result = result
        self._plan()
        self.post("him_result", self.describe(time.time() - started))
        if self.inspect and self.auto_play and self.clip:
            self.command("play")

    def show_more(self):
        if not self.result:
            raise ValueError("Select geometry first")
        self.stop()
        model = FusionTimelineModel(self.design())
        self.busy = True
        try:
            him_filter.show_more(model, self.result)
        finally:
            try:
                model.restore()
            finally:
                self.busy = False
        self.model_highlights.update(model.highlights)
        self._plan()
        self.post("him_result", self.describe())

    def _plan(self):
        self.clip = list(self.result.features)
        animatable = [animation_mode(f.kind) != NONE for f in self.clip]
        self.playback = Playback(len(self.clip), self.seconds, animatable)

    def describe(self, seconds=None):
        data = self.result.as_dict() if self.result else {"features": [], "bases": []}
        design = self.design()
        for item, feature in zip(data["features"], self.clip):
            item["mode"] = animation_mode(feature.kind)
            entity = self._feature_entity(feature)
            item["parameters"] = []
            if entity is not None and design:
                for param in all_feature_parameters(design, entity):
                    item["parameters"].append({"name": param.name, "expression": param.expression,
                                               "unit": param.unit, "value": param.value})
            try:
                item["suppressed"] = bool(entity.isSuppressed)
            except Exception:
                item["suppressed"] = False
        data["selection"] = self.selection_label
        data["playback"] = self.playback.as_dict()
        data["inspect"] = self.inspect
        if seconds is not None:
            data["analysis_seconds"] = round(seconds, 2)
        return data

    # --- animation ---------------------------------------------------------------
    def capture_ghost_context(self):
        """Read the model's *actual pre-feature* edges, without mutating it.

        Called by ReferenceSession with the timeline marker before the
        current feature, only once per feature; never on every video frame.
        """
        self.pending_ghost = None
        if not self.wireframe_context or not self.dim_others:
            return
        design = self.design()
        if not design:
            return
        try:
            self.pending_ghost = capture_before_feature(design)
        except WireframeOverflow as error:
            self.log("HiM wireframe disabled for this step: " + str(error))
        except Exception as error:
            self.log("HiM wireframe capture failed: " + str(error))

    def _start_ghost_context(self, prepared, snapshot):
        """Draw a true gray BRep edge reference; mask native solid surfaces.

        Must keep the context CustomGraphicsGroup separate from the active
        Feature group, which is rebuilt after each parameter recomputation.
        If a complete ghost cannot be drawn, use the established 20%-opacity
        fallback instead of hiding parts of the actual model.
        """
        if snapshot is None or not snapshot["curves"]:
            return False
        design = self.design()
        group = None
        try:
            group = design.rootComponent.customGraphicsGroups.add()
            group.isSelectable = False
            color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
                adsk.core.Color.create(*GHOST_WIREFRAME))
            drawn = 0
            for curve in snapshot["curves"]:
                line = group.addCurve(curve)
                if line is None:
                    raise RuntimeError("Fusion could not draw a BRep wireframe curve")
                line.color = color
                line.weight = 1
                line.depthPriority = 0
                line.isSelectable = False
                drawn += 1
            if drawn != len(snapshot["curves"]):
                raise RuntimeError("Incomplete background wireframe")
            from .spatial import _model_bodies
            # Hide native shaded faces; ONLY the precise feature-owned face
            # copies (or a provably newly created Body) will be opaque.
            # 0.001 avoids unsupported exact-zero edge cases in Fusion.
            self.focus.apply(self._document_key(), _model_bodies(design),
                             {"\\0wireframe"}, dim_opacity=GHOST_SURFACE_OPACITY)
            self.ghost_group = group
            prepared["wireframe"] = True
            prepared["ghost_edges"] = drawn
            return True
        except Exception as error:
            self.log("HiM wireframe fallback to translucency: " + str(error))
            try:
                self.focus.restore()
            except Exception as restore_error:
                self.log("HiM wireframe restore: " + str(restore_error))
                # Never continue with a partly hidden native model.
                raise
            try:
                if group and group.isValid:
                    group.deleteMe()
            except Exception:
                pass
            return False

    def _prepare(self, position):
        """Start animating: retain ghost edges, capture params, isolate faces."""
        snapshot = self.pending_ghost
        self._finish_feature()           # cleans up previous active graphics
        self.pending_ghost = None
        feature = self.clip[position]
        entity = self._feature_entity(feature)
        mode = animation_mode(feature.kind)
        prepared = {"feature": feature, "mode": mode, "params": [], "bodies": [],
                    "entity": entity, "fallback": "", "wireframe": False,
                    "before_tokens": snapshot["body_tokens"] if snapshot else frozenset()}
        design = self.design()
        if entity is None:
            prepared["mode"] = NONE
            prepared["fallback"] = "feature not found in the model"
        elif mode == PARAMETRIC:
            for param in _model_parameters(design, entity, feature.kind):
                key = param.name
                self.journal.capture(key, param)
                prepared["params"].append((key, param, param.value))
            if not prepared["params"]:
                prepared["mode"] = FADE
                prepared["fallback"] = "no animatable parameter for this extent type"
        try:
            prepared["bodies"] = [b for b in _items(getattr(entity, "bodies", None)) if b]
        except Exception:
            prepared["bodies"] = []
        faces = _items(getattr(entity, "faces", None), self.MAX_FACE_HIGHLIGHTS + 1)
        suitable = len(faces) <= self.MAX_FACE_HIGHLIGHTS and can_isolate_feature(
            feature.kind, faces, prepared["bodies"], prepared["before_tokens"])
        if (self.wireframe_context and self.dim_others and suitable
                and prepared["mode"] in (PARAMETRIC, FADE)):
            self._start_ghost_context(prepared, snapshot)
        if not prepared["wireframe"]:
            if self.wireframe_context and snapshot is not None and snapshot["curves"]:
                self.log("HiM: exact changed faces unavailable for {}: using translucent context"
                         .format(feature.name))
            self._apply_focus(prepared["bodies"], hide_result=prepared["mode"] == FADE)
        self._draw_overlay(prepared, 0.0)
        self.active_position = position
        self.active = prepared

    def _apply_focus(self, bodies, hide_result=False):
        """Dim the other bodies. For the visual fallback the resulting bodies
        are dimmed too, so the fading overlay reads as the result appearing."""
        if not self.dim_others:
            return
        design = self.design()
        protected = {_token(b) for b in bodies if _token(b)}
        if not protected:
            return
        if hide_result:
            protected = {"\0none"}
        from .spatial import _model_bodies
        try:
            self.focus.apply(self._document_key(), _model_bodies(design), protected, dim_opacity=0.2)
        except FocusError as error:
            self.log("HiM focus: " + str(error))

    def _draw_overlay(self, prepared, progress):
        """Highlight the input profile/edges; scale+fade for non-parametric."""
        self._delete_group()
        design = self.design()
        if not design:
            return
        group = design.rootComponent.customGraphicsGroups.add()
        group.isSelectable = False
        curves = self.model_highlights.get(prepared["feature"].index, [])
        for curve in curves:
            try:
                line = group.addCurve(curve)
                line.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
                    adsk.core.Color.create(*HIGHLIGHT))
                line.weight = 3
                line.depthPriority = 1
            except Exception:
                continue
        # Teal marks what the feature changed: the faces the feature itself
        # reports (Feature.faces), copied as temporary bodies so only they are
        # drawn; the whole result body only when no face is reported. Do not
        # pretend to know which face was selected when source inputs are
        # absent. The native feature itself supplies the actual motion.
        if prepared["mode"] in (FADE, PARAMETRIC):
            targets = self._change_targets(prepared)
            if prepared.get("wireframe") and not targets:
                # If Fusion rejects a transient copy of the Feature's
                # changed faces, a ghost-only viewport would be misleading.
                # Restore original faces and fall back to the established
                # shaded context rather than concealing the whole model.
                self.log("HiM: exact changed faces cannot be drawn; reverting to translucent context")
                self.focus.restore()
                if self.ghost_group and self.ghost_group.isValid:
                    self.ghost_group.deleteMe()
                self.ghost_group = None
                prepared["wireframe"] = False
                prepared["context_fallback"] = "changed feature faces could not be copied"
                self._apply_focus(prepared["bodies"], hide_result=prepared["mode"] == FADE)
                targets = self._change_targets(prepared)
            center = _center(targets) if prepared["mode"] == FADE else None
            for body in targets:
                try:
                    overlay = group.addBRepBody(body)
                    overlay.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
                        adsk.core.Color.create(*CHANGE_HIGHLIGHT))
                    if prepared["mode"] == PARAMETRIC:
                        # With the original shaded bodies hidden, opaque
                        # changed faces are the only visible solid geometry.
                        opacity = 1.0 if prepared.get("wireframe") else (
                            0.18 if body in prepared["bodies"] else 0.6)
                        overlay.setOpacity(opacity, True)
                    else:
                        overlay.setOpacity(progress, True)
                        scale = 0.5 + 0.5 * progress
                        matrix = adsk.core.Matrix3D.create()
                        for axis in range(3):
                            matrix.setCell(axis, axis, scale)
                        matrix.setCell(0, 3, center[0] * (1 - scale))
                        matrix.setCell(1, 3, center[1] * (1 - scale))
                        matrix.setCell(2, 3, center[2] * (1 - scale))
                        overlay.transform = matrix
                    overlay.depthPriority = 1
                    overlay.isSelectable = False
                except Exception as error:
                    self.log("HiM geometry guidance: " + str(error))
            # A precise native face copy is a reliable target. A whole
            # result Body is not: omit the arrow rather than point vaguely.
            self._add_geometry_arrow(group, targets, prepared["bodies"])
        self.group = group

    @staticmethod
    def _add_geometry_arrow(group, targets, result_bodies):
        """Point at a feature-owned changed face if its geometry is available."""
        if not targets or not any(all(target is not body for body in result_bodies)
                                  for target in targets):
            return
        try:
            from .renderer import add_target_arrow, body_target_bounds
            add_target_arrow(group, body_target_bounds(targets))
        except Exception:
            pass  # guidance is optional and must never interrupt native playback

    MAX_FACE_HIGHLIGHTS = 200

    def draw_guidance(self, features):
        """Spatial guidance for a finished step, kept until the next frame,
        step change or stop: blue input profile/edges (when the feature's
        inputs were read), teal faces the features created or modified."""
        self._delete_group()
        design = self.design()
        if not design or not features:
            return None
        group = design.rootComponent.customGraphicsGroups.add()
        group.isSelectable = False
        arrow_target = None
        for feature in features:
            for curve in self.model_highlights.get(feature.index, []):
                try:
                    line = group.addCurve(curve)
                    line.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
                        adsk.core.Color.create(*HIGHLIGHT))
                    line.weight = 3
                    line.depthPriority = 2
                except Exception:
                    continue
            entity = self._feature_entity(feature)
            bodies = [b for b in _items(getattr(entity, "bodies", None)) if b] if entity is not None else []
            targets = self._change_targets({"entity": entity, "bodies": bodies})
            if targets and any(all(target is not b for b in bodies) for target in targets):
                arrow_target = (targets, bodies)
            for body in targets:
                try:
                    overlay = group.addBRepBody(body)
                    overlay.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
                        adsk.core.Color.create(*CHANGE_HIGHLIGHT))
                    overlay.setOpacity(0.18 if body in bodies else 0.6, True)
                    overlay.depthPriority = 1
                    overlay.isSelectable = False
                except Exception as error:
                    self.log("HiM geometry guidance: " + str(error))
        if arrow_target:
            self._add_geometry_arrow(group, *arrow_target)
        self.group = group
        self._refresh()
        return group

    def _change_targets(self, prepared):
        """Temporary copies of the faces this feature created or modified
        (read every frame: parameter changes recompute them); else its
        result bodies."""
        faces = _items(getattr(prepared.get("entity"), "faces", None), self.MAX_FACE_HIGHLIGHTS + 1)
        if faces and len(faces) <= self.MAX_FACE_HIGHLIGHTS:
            try:
                manager = adsk.fusion.TemporaryBRepManager.get()
                copies = [manager.copy(face) for face in faces]
                if len(copies) == len(faces) and all(c is not None for c in copies):
                    return copies
                self.log("HiM: incomplete affected-face copy; refusing partial isolation")
            except Exception as error:
                self.log("HiM geometry guidance: " + str(error))
        if prepared.get("wireframe"):
            # A modified pre-existing Body must NEVER be substituted for
            # the Feature's own faces; that would show an entire part as
            # though this one edit had just created it.
            before = prepared.get("before_tokens", frozenset())
            return [b for b in prepared["bodies"]
                    if _token(b) not in before]
        return list(prepared["bodies"])

    def _delete_group(self):
        try:
            if self.group and self.group.isValid:
                self.group.deleteMe()
        except Exception:
            pass
        self.group = None

    def _render(self, frame):
        if frame.position != self.active_position:
            self._prepare(frame.position)
        prepared = self.active
        if prepared["mode"] == PARAMETRIC:
            failure = None
            for key, param, target in prepared["params"]:
                try:
                    param.value = interpolate(target, frame.progress)
                except Exception as error:
                    failure = "Fusion rejected {} = {:.4g}: {}".format(
                        key, interpolate(target, frame.progress), error)
                    break
            if failure is None and _feature_failed(prepared["entity"]):
                failure = "the feature failed to compute at this parameter value"
            if failure is not None:
                self._fallback(prepared, failure)
        if prepared["mode"] in (FADE, PARAMETRIC):
            self._draw_overlay(prepared, frame.progress)
        self._refresh()

    def _fallback(self, prepared, reason):
        """A parameter frame failed: put the real values back and show this
        feature with the visual effect instead (never a half-computed model)."""
        self.log("HiM: {}: {}; using the visual effect".format(prepared["feature"].name, reason))
        try:
            self.journal.restore([key for key, _, _ in prepared["params"]])
        except Exception as error:
            self.log("HiM restore: " + str(error))
        prepared["mode"] = FADE
        prepared["fallback"] = reason
        if not prepared.get("wireframe"):
            try:
                self.focus.restore()
            except Exception as error:
                self.log("HiM focus restore before fallback: " + str(error))
            self._apply_focus(prepared["bodies"], hide_result=True)
        # With an active ghost, keep the real model almost invisible and
        # switch ONLY the feature-owned overlay to the visual fade. Mixing
        # opaque source bodies with the ghost would break the isolation.

    def status(self):
        """What the active feature is doing: parameter animation or visual."""
        prepared = self.active
        if not prepared:
            return None
        return {"feature": prepared["feature"].name, "kind": prepared["feature"].kind,
                "mode": {PARAMETRIC: "parameter", FADE: "visual"}.get(prepared["mode"], "timeline"),
                "parameters": [key for key, _, _ in prepared["params"]] if prepared["mode"] == PARAMETRIC else [],
                "fallback": prepared.get("fallback", ""),
                "wireframe": bool(prepared.get("wireframe")),
                "ghost_edges": prepared.get("ghost_edges", 0),
                "context_fallback": prepared.get("context_fallback", "")}

    def _finish_feature(self):
        """Restore parameters, opacity and overlay of the active feature."""
        errors = []
        try:
            self.journal.restore()
        except Exception as error:
            errors.append(str(error))
        try:
            self.focus.restore()
        except Exception as error:
            errors.append(str(error))
        self._delete_group()
        if self.ghost_group is not None:
            try:
                if self.ghost_group.isValid:
                    self.ghost_group.deleteMe()
            except Exception as error:
                errors.append("ghost graphics: " + str(error))
            self.ghost_group = None
        self.active_position = None
        self.active = {}
        if errors:
            raise RuntimeError("; ".join(errors))

    def tick(self):
        """One animation frame; called from the add-in's custom event."""
        if not self.playback.playing or not self.clip:
            return False
        started = time.perf_counter()
        frame = self.playback.tick(self.last_frame_seconds)
        try:
            self._render(frame)
        finally:
            self.last_frame_seconds = time.perf_counter() - started
        if frame.finished and frame.progress >= 1.0:
            # Forward clip done: the model is back at its real state.
            self._finish_feature()
        self.post("him_playback", self.playback.as_dict())
        return self.playback.playing

    ANIMATING = ("play", "replay", "forward", "backward", "select")

    def command(self, name, value=None):
        if name in self.ANIMATING and not self.inspect:
            raise ValueError("Turn on Inspect mode to animate your own model's features")
        if name == "inspect":
            self.inspect = bool(value)
            if not self.inspect:
                self.stop()
        elif name == "play":
            self.playback.play()
        elif name == "pause":
            self.playback.pause()
        elif name == "replay":
            self._finish_feature()
            self.playback.replay()
        elif name == "forward":
            self.playback.step_forward()
        elif name == "backward":
            self.playback.step_backward()
        elif name == "select":
            self.playback.select(int(value))
        elif name == "speed":
            self.seconds = float(value)
            self.playback.set_speed(self.seconds)
        elif name == "dim":
            self.dim_others = bool(value)
        elif name == "auto":
            self.auto_play = bool(value)
        else:
            raise ValueError("Unknown HiM command " + str(name))
        self.last_frame_seconds = None
        self.post("him_playback", self.playback.as_dict())

    def stop(self):
        """Stop and restore the user's model completely."""
        self.playback.pause()
        self._finish_feature()

    # --- edit shortcuts ---------------------------------------------------------------
    EDIT_COMMANDS = ("FusionEditFeatureCommand", "FusionEditFeatureCmd", "EditFeatureCommand")

    def edit_feature(self, position):
        self.stop()
        feature = self.clip[int(position)]
        entity = self._feature_entity(feature)
        if entity is None:
            raise ValueError("Feature no longer exists")
        self.busy = True
        try:
            self.ui.activeSelections.clear()
            self.ui.activeSelections.add(entity)
        finally:
            self.busy = False
        for command_id in self.EDIT_COMMANDS:
            definition = self.ui.commandDefinitions.itemById(command_id)
            if definition:
                definition.execute()
                return "Editing " + feature.name
        return feature.name + " selected; right-click it and choose Edit Feature, or edit its parameters below."

    def set_parameter(self, position, name, expression):
        self.stop()
        feature = self.clip[int(position)]
        entity = self._feature_entity(feature)
        for param in all_feature_parameters(self.design(), entity):
            if param.name == name:
                if not self.design().unitsManager.isValidExpression(expression, param.unit):
                    raise ValueError("Invalid expression for " + name)
                param.expression = expression
                self.post("him_result", self.describe())
                return name + " = " + expression
        raise ValueError("Parameter not found: " + str(name))
