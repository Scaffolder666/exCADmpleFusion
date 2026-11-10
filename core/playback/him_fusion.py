"""Autodesk Fusion side of History in Motion.

* ``FusionTimelineModel`` implements the adapter interface of
  ``core.playback.him_filter`` on a live parametric Design: it rolls the timeline marker
  to the states the algorithm asks for and always restores the marker.
* ``HiMController`` animates one feature at a time on the reference copy:
  real growth by temporarily varying its ModelParameters from ~0 to the
  actual value (paper Section 6.2), or fast motion of its real faces where
  that is the same shape or there is nothing to grow; the model before the
  feature is drawn as translucent faces with a dark outline, the input
  profile/edges in blue, the changed faces in lit teal. Every changed
  parameter expression and opacity is journaled and restored.
"""
import math

import adsk.core
import adsk.fusion

from core.playback.him_filter import FeatureInfo, InputRef
from core.playback.him_motion import (RestoreJournal, animation_mode, parameter_paths,
                         interpolate, short_kind, PARAMETRIC, FADE, NONE)
from core.focus import OpacityFocus, FocusError
from core.playback.him_wireframe import capture_before_feature, can_isolate_feature, WireframeOverflow
from core.playback.fast_motion import EXACT

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
CHANGE_HIGHLIGHT = (20, 184, 166, 255)
NEUTRAL_FACE = (196, 202, 210, 255)  # faces of the feature that do not move
HANDLE_COLOR = (235, 109, 35, 255)    # manipulator arrow + value, like Fusion's
REAL_GROWTH = "real growth: its parameters are animated"
OUTLINE_COLOR = (12, 84, 77, 255)     # edges of highlighted faces, so their shape reads
MAX_OUTLINE_EDGES = 3000  # teal: geometry affected by feature
GHOST_WIREFRAME = (40, 44, 52, 255)     # near-black outline of the model before the feature
CONTEXT_FILL = (232, 236, 241, 255)     # its faces: white, translucent
CONTEXT_FILL_OPACITY = 0.28
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
    """Adapter for core.playback.him_filter on a live Fusion Design."""

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
    kind (core.playback.him_motion.FEATURES). Paths that do not lead to a
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


def _partial_line(geometry, fraction):
    """The first ``fraction`` of a straight line; None for other curves
    (they appear whole once reached rather than being approximated)."""
    try:
        line = adsk.core.Line3D.cast(geometry)
        if not line or fraction <= 0:
            return None
        a, b = line.startPoint, line.endPoint
        end = adsk.core.Point3D.create(a.x + (b.x - a.x) * fraction, a.y + (b.y - a.y) * fraction,
                                       a.z + (b.z - a.z) * fraction)
        return adsk.core.Line3D.create(a, end)
    except Exception:
        return None


def _surface(rgb):
    """A lit colour for highlighted geometry: shaded like a body, so the
    shape reads (a flat solid colour turns it into a silhouette)."""
    r, g, b = rgb[:3]
    try:
        return adsk.fusion.CustomGraphicsBasicMaterialColorEffect.create(
            adsk.core.Color.create(r, g, b, 255),
            adsk.core.Color.create(int(r * 0.45), int(g * 0.45), int(b * 0.45), 255),
            adsk.core.Color.create(70, 70, 70, 255),
            adsk.core.Color.create(0, 0, 0, 255), 25.0, 1.0)
    except Exception:
        return adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(r, g, b, 255))


def _outline(group, item, budget):
    """Dark edges of a highlighted face or body copy. Returns the curve
    entities (fast motion moves them with their faces)."""
    added = []
    try:
        edges = item.edges
        count = min(edges.count, budget[0])
    except Exception:
        return added
    color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*OUTLINE_COLOR))
    for i in range(count):
        try:
            geometry = edges.item(i).geometry
            if geometry is None:
                continue
            line = group.addCurve(geometry)
            line.color = color
            line.weight = 1.5
            line.depthPriority = 2
            line.isSelectable = False
            added.append(line)
        except Exception:
            continue
    budget[0] -= len(added)
    return added


def _short_number(value):
    """6.1584118 -> '6.16', 12.0 -> '12', 0.5 -> '0.5'."""
    text = "{:.2f}".format(value).rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


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
    """Animates one feature at a time on the reference copy (HiM): native
    parameter growth or fast motion, its highlights and the context."""

    def __init__(self, app, ui, log=None, design_provider=None):
        self.app, self.ui = app, ui
        # Version A passes the reference copy's design here, so animation
        # never touches whatever document happens to be active.
        self._design_provider = design_provider
        # Same-viewport mode: overlays are drawn into the user's design
        # (callable returning it) and moved beside the user's model.
        self.graphics_design = None
        self.display_offset = (0.0, 0.0, 0.0)
        self.log = log or (lambda *_: None)
        self.clip = []
        self.journal = RestoreJournal()
        self.focus = OpacityFocus(self._resolve_body, self._document_key)
        self.group = None
        self.ghost_group = None       # persistent backdrop for ONE active Feature
        self.hidden_sketches = []     # native sketches hidden while being drawn
        # Fast motion (core.playback.fast_motion): move the feature's real
        # faces instead of recomputing every frame. Opt in (reference copy).
        self.fast_motion = False
        self.pending_inputs = {}
        self.inputs_by_index = {}      # feature index -> plane / axis read before it
        self.fast_group = None
        self.handle_group = None
        self.pending_ghost = None     # captured at Timeline marker BEFORE feature
        self.wireframe_context = False  # opt in only on the disposable reference copy
        self.instant_nonparametric = False  # reference: no invented fades or scale
        self.active_position = None
        self.active = {}            # prepared data of the feature being animated
        self.auto_focus = False
        self.dim_others = False
        self.model_highlights = {}

    # --- helpers --------------------------------------------------------------
    def design(self):
        if self._design_provider is not None:
            return self._design_provider()
        return adsk.fusion.Design.cast(self.app.activeProduct)

    def _new_group(self, design):
        """A Custom Graphics group where the user sees the reference."""
        target = self.graphics_design() if self.graphics_design else None
        return (target or design).rootComponent.customGraphicsGroups.add()

    def _placed(self, group):
        if any(self.display_offset):
            from .same_viewport import place
            place(group, self.display_offset)
        return group

    def _document_key(self):
        design = self.design()
        try:
            return design.rootComponent.entityToken if design else ""
        except Exception:
            return ""

    def _resolve_token(self, token):
        """Any entity of the reference design by its entity token."""
        try:
            for entity in self.design().findEntityByToken(token) or []:
                return entity
        except Exception:
            pass
        return None

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
            if self.pending_ghost is not None:
                copies = self._copy_bodies_before() or {}
                self.pending_ghost["copies"] = {t: c for t, c in copies.items()
                                                if t in self.pending_ghost["body_tokens"]}
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
        if snapshot is None:
            return False
        # No bodies before this feature (e.g. the first solid): an empty
        # context is still exact; there is just nothing to draw.
        design = self.design()
        group = None
        try:
            group = self._new_group(design)
            group.isSelectable = False
            color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
                adsk.core.Color.create(*GHOST_WIREFRAME))
            # One look for "the model before this step" in every step:
            # translucent white faces with a dark outline.
            fill = _surface(CONTEXT_FILL)
            for copy in (snapshot.get("copies") or {}).values():
                try:
                    face = group.addBRepBody(copy)
                    face.color = fill
                    face.setOpacity(CONTEXT_FILL_OPACITY, True)
                    face.depthPriority = 0
                    face.isSelectable = False
                except Exception as error:
                    self.log("HiM context fill: " + str(error))
            drawn = 0
            for curve in snapshot["curves"]:
                line = group.addCurve(curve)
                if line is None:
                    raise RuntimeError("Fusion could not draw a BRep wireframe curve")
                line.color = color
                line.weight = 1.2
                line.depthPriority = 1
                line.isSelectable = False
                drawn += 1
            if drawn != len(snapshot["curves"]):
                raise RuntimeError("Incomplete background wireframe")
            self._placed(group)
            from core.spatial import _model_bodies
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
                    "before_tokens": snapshot["body_tokens"] if snapshot else frozenset(),
                    "context_captured": snapshot is not None}
        design = self.design()
        if entity is None:
            prepared["mode"] = NONE
            prepared["fallback"] = "feature not found in the model"
        inputs, self.pending_inputs = self.pending_inputs, {}
        if not inputs:
            inputs = self.inputs_by_index.get(feature.index, {})
        prepared["inputs"] = inputs
        plan = None
        native_reason = ""
        if self.fast_motion and entity is not None:
            from .fast_motion import plan_for
            reasons = []
            extra = {"resolve": self._resolve_token,
                     "profile_curves": self.model_highlights.get(feature.index, []),
                     "after_tokens": self._visible_tokens()}
            plan = plan_for(feature.kind, entity, dict(inputs, **extra), reasons=reasons)
            native_reason = reasons[0] if reasons else ""
        if entity is None:
            pass
        elif mode == PARAMETRIC:
            for param in _model_parameters(design, entity, feature.kind):
                key = param.name
                if plan is None:          # fast motion captures only if it settles
                    self.journal.capture(key, param)
                prepared["params"].append((key, param, param.value))
            if not prepared["params"]:
                prepared["mode"] = FADE
                prepared["fallback"] = "no animatable parameter for this extent type"
        if plan is not None and prepared["params"] and plan.accuracy != EXACT:
            # A feature that can grow grows for real, as in HiM: Fusion
            # recomputes it at each parameter value. Fast motion is kept only
            # where it is the same shape (a new-body extrude) or where the
            # operation has no parameter to grow (move, mirror, combine...).
            for key, param, _ in prepared["params"]:
                self.journal.capture(key, param)
            plan = None
            native_reason = REAL_GROWTH
        try:
            prepared["bodies"] = [b for b in _items(getattr(entity, "bodies", None)) if b]
        except Exception:
            prepared["bodies"] = []
        faces = _items(getattr(entity, "faces", None), self.MAX_FACE_HIGHLIGHTS + 1)
        suitable = len(faces) <= self.MAX_FACE_HIGHLIGHTS and can_isolate_feature(
            feature.kind, faces, prepared["bodies"], prepared["before_tokens"])
        if plan is not None:
            # Fast motion draws exactly what moves (e.g. a Move's bodies), so
            # the native result can be hidden behind the ghost context.
            suitable = True
        if (self.wireframe_context and self.dim_others and suitable
                and (prepared["mode"] in (PARAMETRIC, FADE) or plan is not None)):
            self._start_ghost_context(prepared, snapshot)
        if not prepared["wireframe"]:
            prepared["context_fallback"] = ("exact pre-feature context or affected faces unavailable")
            if self.wireframe_context and snapshot is not None and snapshot["curves"]:
                self.log("HiM: exact changed faces unavailable for {}: using translucent context"
                         .format(feature.name))
            self._apply_focus(prepared["bodies"], hide_result=(
                prepared["mode"] == FADE and not self.instant_nonparametric))
        if plan is not None and prepared["wireframe"]:
            # Only with the native result hidden can moved face copies show
            # the intermediate shape without the final one behind them.
            prepared["fast"] = plan
        elif plan is not None:
            native_reason = "the finished result cannot be hidden (ghost context unavailable)"
            for key, param, _ in prepared["params"]:
                self.journal.capture(key, param)
        prepared["native_reason"] = native_reason
        if self.auto_focus:
            self.focus_feature(prepared)
        self._draw_overlay(prepared, 0.0)
        if prepared.get("fast") and not self._start_fast(prepared):
            for key, param, _ in prepared["params"]:
                self.journal.capture(key, param)
            prepared["fast"] = None
            prepared["native_reason"] = "the feature's faces could not be copied"
            self._draw_overlay(prepared, 0.0)
        if self.fast_motion and (prepared["mode"] in (PARAMETRIC, FADE) or prepared.get("fast")):
            self.log("HiM motion {} ({}): {}".format(
                feature.name, feature.kind,
                "fast, " + prepared["fast"].accuracy + (
                    " (" + prepared["fast"].note + ")" if getattr(prepared["fast"], "note", "") else "")
                if prepared.get("fast")
                else "Fusion recompute, " + (prepared["native_reason"] or "no reason recorded")))
        self.active_position = position
        self.active = prepared

    def focus_feature(self, prepared=None):
        """Frame once at feature entry, never on every animation frame."""
        if not self.auto_focus:
            return False
        prepared = self.active if prepared is None else prepared
        if not prepared:
            return False
        from .him_camera import focus_geometry
        try:
            entity = prepared.get("entity")
            geometry = _items(getattr(entity, "faces", None)) or prepared.get("bodies", [])
            ox, oy, oz = self.display_offset
            return focus_geometry(self.app.activeViewport, geometry,
                                  lambda x, y, z: adsk.core.Point3D.create(x + ox, y + oy, z + oz))
        except Exception as error:
            self.log("HiM auto-focus: " + str(error))
            return False  # camera guidance must not interrupt native reconstruction

    CONTEXT_OPACITY = 0.2

    def dim_context(self):
        """A sketch step's context in the same look as every other step
        (translucent white faces, dark outline); dimmed bodies only if that
        cannot be drawn."""
        if not self.dim_others:
            return
        if self.wireframe_context:
            self.capture_ghost_context()
            snapshot, self.pending_ghost = self.pending_ghost, None
            if snapshot is not None and self._start_ghost_context({}, snapshot):
                return
        from core.spatial import _model_bodies
        try:
            self.focus.apply(self._document_key(), _model_bodies(self.design()), {"\0none"},
                             dim_opacity=self.CONTEXT_OPACITY)
        except FocusError as error:
            self.log("HiM focus: " + str(error))

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
        from core.spatial import _model_bodies
        try:
            self.focus.apply(self._document_key(), _model_bodies(design), protected,
                             dim_opacity=self.CONTEXT_OPACITY)
        except FocusError as error:
            self.log("HiM focus: " + str(error))

    def _draw_overlay(self, prepared, progress):
        """Highlight the input profile/edges; scale+fade for non-parametric."""
        self._delete_group()
        design = self.design()
        if not design:
            return
        group = self._new_group(design)
        self.group = group  # own it before any draw can fail
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
        if prepared["mode"] in (FADE, PARAMETRIC) and not self._moving(prepared):
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
                self._apply_focus(prepared["bodies"], hide_result=(
                    prepared["mode"] == FADE and not self.instant_nonparametric))
                targets = self._change_targets(prepared)
            center = _center(targets) if prepared["mode"] == FADE else None
            draw_failed = False
            roles = self._target_roles(prepared["entity"], prepared["feature"].kind,
                                       targets, prepared["bodies"])
            outline_budget = [MAX_OUTLINE_EDGES]
            for number, body in enumerate(targets):
                role = roles[number] if roles else None
                if role == "body" and not prepared.get("wireframe"):
                    continue          # the native body already shows it
                try:
                    overlay = group.addBRepBody(body)
                    overlay.color = _surface(NEUTRAL_FACE if role == "body" else CHANGE_HIGHLIGHT)
                    _outline(group, body, outline_budget)
                    if prepared["mode"] == PARAMETRIC:
                        # One look for every step: the feature's changed
                        # faces are opaque teal, whatever the context style.
                        opacity = 1.0
                        if overlay.setOpacity(opacity, True) is False:
                            raise RuntimeError("Fusion rejected feature overlay opacity")
                    elif self.instant_nonparametric:
                        # The real Timeline already contains the operation's
                        # result. There is no numeric parameter to animate:
                        # simply SHOW that geometry at its actual size.
                        if overlay.setOpacity(1.0, True) is False:
                            raise RuntimeError("Fusion rejected feature overlay opacity")
                    else:
                        # Legacy HiM inspect mode retains its original
                        # fade/scale visual effect outside the reference.
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
                    draw_failed = True
                    self.log("HiM geometry guidance: " + str(error))
            if draw_failed and prepared.get("wireframe"):
                self.focus.restore()
                if self.ghost_group and self.ghost_group.isValid:
                    self.ghost_group.deleteMe()
                self.ghost_group = None
                prepared["wireframe"] = False
                prepared["context_fallback"] = "changed feature faces could not be drawn"
                self._apply_focus(prepared["bodies"])
                self._draw_overlay(prepared, progress)
                return
            # A precise native face copy is a reliable target. A whole
            # result Body is not: omit the arrow rather than point vaguely.
            from .manipulator import handles
            live = handles(prepared["feature"].kind, prepared["entity"], prepared.get("inputs", {}))
            if roles and live:
                self._draw_handles(live, prepared, group=group)
            else:
                self._add_geometry_arrow(group, targets, prepared["bodies"])
        self.group = self._placed(group)

    @staticmethod
    def _add_geometry_arrow(group, targets, result_bodies):
        """Point at a feature-owned changed face if its geometry is available."""
        if not targets or not any(all(target is not body for body in result_bodies)
                                  for target in targets):
            return
        try:
            from core.renderer import add_target_arrow, body_target_bounds
            add_target_arrow(group, body_target_bounds(targets))
        except Exception:
            pass  # guidance is optional and must never interrupt native playback

    MAX_FACE_HIGHLIGHTS = 200
    MAX_SKETCH_CURVES = 2000

    def draw_sketch(self, sketches, progress, hide_native=True):
        """Draw the sketches' real curves in blue, revealed in the order of
        Fusion's sketchCurves collection (the designer's drawing order was
        not recorded). A line being drawn grows from its start point. While
        drawing, the native sketch is hidden so it does not appear all at
        once; _finish_feature shows it again."""
        self._delete_group()
        design = self.design()
        curves = []
        for sketch in sketches:
            if hide_native and progress < 1.0:
                try:
                    if sketch.isLightBulbOn and sketch not in self.hidden_sketches:
                        sketch.isLightBulbOn = False
                        self.hidden_sketches.append(sketch)
                except Exception:
                    pass
            collection = getattr(sketch, "sketchCurves", None)
            for curve in _items(collection, self.MAX_SKETCH_CURVES):
                try:
                    curves.append(curve.worldGeometry)
                except Exception:
                    continue
        if not design or not curves:
            return 0
        group = self._new_group(design)
        self.group = group
        group.isSelectable = False
        progress = max(0.0, min(1.0, float(progress)))
        shown = len(curves) * progress
        complete = int(shown)
        color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*HIGHLIGHT))
        drawn = 0
        for i, geometry in enumerate(curves):
            if i > complete or (i == complete and complete == len(curves)):
                break
            if i == complete:                     # the curve being drawn now
                geometry = _partial_line(geometry, shown - complete)
                if geometry is None:
                    break
            try:
                line = group.addCurve(geometry)
                line.color = color
                line.weight = 3
                line.depthPriority = 2
                line.isSelectable = False
                drawn += 1
            except Exception:
                continue
        self._placed(group)
        self._refresh()
        return drawn

    def draw_guidance(self, features):
        """Spatial guidance for a finished step, kept until the next frame,
        step change or stop: blue input profile/edges (when the feature's
        inputs were read), teal faces the features created or modified."""
        self._delete_group()
        design = self.design()
        if not design or not features:
            return None
        group = self._new_group(design)
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
            roles = self._target_roles(entity, feature.kind, targets, bodies)
            from .manipulator import handles
            live = handles(feature.kind, entity, self.inputs_by_index.get(feature.index, {})) if roles else []
            if live:
                self._draw_handles(live, {"bodies": bodies}, group=group)
            elif targets and any(all(target is not b for b in bodies) for target in targets):
                arrow_target = (targets, bodies)
            for number, body in enumerate(targets):
                if roles and roles[number] == "body":
                    continue          # only the face that moved is marked
                try:
                    overlay = group.addBRepBody(body)
                    overlay.color = _surface(CHANGE_HIGHLIGHT)
                    _outline(group, body, [MAX_OUTLINE_EDGES])
                    overlay.setOpacity(1.0, True)          # same opaque teal as the animation
                    overlay.depthPriority = 1
                    overlay.isSelectable = False
                except Exception as error:
                    self.log("HiM geometry guidance: " + str(error))
        if arrow_target:
            self._add_geometry_arrow(group, *arrow_target)
        self.group = self._placed(group)
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
        if prepared.get("wireframe") or self.instant_nonparametric:
            # A modified pre-existing Body must NEVER be substituted for
            # the Feature's own faces; that would show an entire part as
            # though this one edit had just created it.
            before = prepared.get("before_tokens", frozenset())
            feature = prepared.get("feature")
            if (not prepared.get("context_captured") or feature is None
                    or not can_isolate_feature(feature.kind, [], prepared["bodies"], before)):
                return []
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

    # --- fast motion ----------------------------------------------------------------
    @staticmethod
    def _moving(prepared):
        return bool(prepared.get("fast")) and not prepared.get("settled")

    def capture_motion_inputs(self, feature):
        """Profile plane / axis / mirror plane, read with the Timeline marker
        before the feature. Used by the next _prepare."""
        self.pending_inputs = {}
        if not self.fast_motion:
            return
        from .fast_motion import capture_inputs
        entity = self._feature_entity(feature)
        if entity is not None:
            self.pending_inputs = capture_inputs(feature.kind, entity)
            from .fast_motion import SPECIFIC
            if feature.kind not in SPECIFIC or feature.kind == "RevolveFeature":
                ghost = self.pending_ghost or {}
                before = ghost.get("copies") if ghost.get("copies") is not None else self._copy_bodies_before()
                if before is not None:
                    self.pending_inputs["before_bodies"] = before
            self.inputs_by_index[feature.index] = self.pending_inputs

    MAX_BEFORE_BODIES = 60

    def _copy_bodies_before(self):
        """Transient copies of the visible bodies as they are now (marker
        before a feature), keyed by token: the "before" of a crossfade.
        None when there are too many to copy."""
        from core.spatial import _model_bodies
        design = self.design()
        bodies = [(t, b) for t, b in _model_bodies(design) if getattr(b, "isVisible", True) is not False]
        if len(bodies) > self.MAX_BEFORE_BODIES:
            return None
        try:
            manager = adsk.fusion.TemporaryBRepManager.get()
        except Exception:
            return None
        copies = {}
        for token, body in bodies:
            try:
                copy = manager.copy(body)
            except Exception:
                copy = None
            if copy is not None:
                copies[token] = copy
        return copies

    def _visible_tokens(self):
        from core.spatial import _model_bodies
        try:
            return {t for t, b in _model_bodies(self.design()) if getattr(b, "isVisible", True) is not False}
        except Exception:
            return None

    def _start_fast(self, prepared):
        """Copy the feature's real faces once; frames only move them."""
        self._delete_fast()
        design = self.design()
        group = None
        try:
            manager = adsk.fusion.TemporaryBRepManager.get()
            group = self._new_group(design)
            group.isSelectable = False
            color = _surface(CHANGE_HIGHLIGHT)
            neutral = _surface(NEUTRAL_FACE)
            outline_budget = [MAX_OUTLINE_EDGES]
            from .manipulator import moving_faces, handles
            kind = prepared["feature"].kind
            moving = moving_faces(kind, prepared["entity"])
            prepared["handles"] = handles(kind, prepared["entity"], prepared.get("inputs", {}))
            entities = []
            profile = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*HIGHLIGHT))
            for piece in prepared["fast"].pieces:
                for face in piece.faces:
                    if piece.kind == "curve":
                        entity = group.addCurve(face)
                        entity.color = profile
                        entity.weight = 3
                        entity.depthPriority = 3
                        entity.isSelectable = False
                        entities.append((piece, entity))
                        continue
                    copy = face if piece.copied else manager.copy(face)
                    if copy is None:
                        raise RuntimeError("Fusion could not copy a feature face")
                    entity = group.addBRepBody(copy)
                    if entity is None:
                        raise RuntimeError("Fusion could not draw a feature face")
                    if piece.role in ("before", "after"):
                        entity.color = neutral
                    elif piece.role == "change":
                        entity.color = color
                    else:
                        # Only the face that moves is highlighted, as in Fusion's
                        # own commands; the rest of the feature looks like a body.
                        entity.color = neutral if moving and _token(face) not in moving else color
                    entity.depthPriority = 2 if piece.role == "change" else 1
                    entity.isSelectable = False
                    entities.append((piece, entity))
                    for line in _outline(group, copy, outline_budget):
                        entities.append((piece, line))      # the outline moves with its face
            if kind == "MoveFeature":
                self._add_move_path(group, prepared["fast"])
                self._placed(group)          # the path; moving entities are placed per frame
            self.fast_group = group
            prepared["fast_entities"] = entities
            prepared["settled"] = False
            return True
        except Exception as error:
            self.log("HiM fast motion unavailable for {}: {}".format(prepared["feature"].name, error))
            try:
                if group is not None and group.isValid:
                    group.deleteMe()
            except Exception:
                pass
            self.fast_group = None
            return False

    def _add_move_path(self, group, plan):
        """Orange arrow from where the moved bodies were to where they end,
        labelled with the distance: makes "from where to where" readable
        while the bodies travel along it."""
        from .fast_motion import apply
        from .manipulator import arrow_lines
        piece = plan.pieces[0]
        end = _center(piece.faces)
        start = apply(piece.matrix(0.0), end)
        distance = math.dist(start, end)
        if distance < 1e-6:
            return                                   # a pure rotation in place
        shape = arrow_lines(start, tuple(end[i] - start[i] for i in range(3)), distance)
        if shape is None:
            return
        points, indices = shape
        color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*HANDLE_COLOR))
        try:
            lines = group.addLines(adsk.fusion.CustomGraphicsCoordinates.create(
                [c for p in points for c in p]), indices, False)
            lines.color = color
            lines.weight = 3
            lines.depthPriority = 3
            lines.isSelectable = False
        except Exception as error:
            self.log("HiM move path: " + str(error))
            return
        try:
            units = self.design().unitsManager
            unit = units.defaultLengthUnits
            text = _short_number(units.convert(distance, "cm", unit)) + " " + unit
        except Exception:
            text = _short_number(distance * 10) + " mm"
        middle = tuple((start[i] + end[i]) / 2 for i in range(3))
        self._add_label(group, text, middle, color)

    def _move_fast(self, prepared, progress):
        offset = None
        if any(self.display_offset):
            from .same_viewport import offset_matrix
            offset = offset_matrix(self.display_offset)
        for piece, entity in prepared["fast_entities"]:
            matrix = adsk.core.Matrix3D.create()
            values = piece.matrix(progress)
            for r in range(4):               # cell by cell: no row/column-order assumption
                for c in range(4):
                    matrix.setCell(r, c, values[r][c])
            if offset is not None:
                matrix.transformBy(offset)
            entity.transform = matrix
            opacity = piece.opacity(progress)
            if opacity is not None:
                try:
                    entity.setOpacity(max(0.0, opacity), True)
                except Exception:
                    entity.isVisible = opacity > 0.5      # entities without opacity
        if prepared.get("handles"):
            from .fast_motion import apply
            m = prepared["fast"].handle_motion(progress)
            moved = []
            for h in prepared["handles"]:
                tip = tuple(h["anchor"][i] + h["direction"][i] for i in range(3))
                anchor, tip = apply(m, h["anchor"]), apply(m, tip)
                moved.append(dict(h, anchor=anchor, direction=tuple(tip[i] - anchor[i] for i in range(3))))
            fraction = interpolate(1.0, progress) if prepared["feature"].kind == "ExtrudeFeature" else progress
            self._draw_handles(moved, prepared, value_fraction=fraction)

    def _settle(self, prepared, progress):
        """Paused: show Fusion's real recompute at this progress."""
        if not prepared["params"]:
            return False                     # no real intermediate state exists
        for key, param, _ in prepared["params"]:
            self.journal.capture(key, param)
        self._delete_fast()
        prepared["settled"] = True
        return True

    def _resume_fast(self, prepared):
        """Back to moving copies after a settled (paused) frame."""
        try:
            self.journal.restore([key for key, _, _ in prepared["params"]])
        except Exception as error:
            raise RuntimeError("Could not restore parameters after pause: " + str(error)) from error
        prepared["settled"] = False
        self._draw_overlay(prepared, 0.0)
        if not self._start_fast(prepared):
            for key, param, _ in prepared["params"]:
                self.journal.capture(key, param)
            prepared["fast"] = None

    def _draw_handles(self, handle_list, prepared, value_fraction=None, group=None):
        """Orange arrow on each moving face plus the current distance/angle.
        With ``group`` the handles join it; otherwise they get their own
        group (fast motion rebuilds only this small group every frame)."""
        from .manipulator import arrow_lines, arrow_length
        own = group is None
        if own:
            self._delete_handles()
            if not handle_list:
                return
            group = self._new_group(self.design())
            group.isSelectable = False
        span = self._feature_span(prepared)
        color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*HANDLE_COLOR))
        for h in handle_list:
            shape = arrow_lines(h["anchor"], h["direction"], arrow_length(span))
            if shape is None:
                continue
            points, indices = shape
            try:
                lines = group.addLines(adsk.fusion.CustomGraphicsCoordinates.create(
                    [c for p in points for c in p]), indices, False)
                lines.color = color
                lines.weight = 4
                lines.depthPriority = 3
                lines.isSelectable = False
            except Exception as error:
                self.log("HiM manipulator arrow: " + str(error))
                continue
            label = self._value_label(h, value_fraction)
            if label:
                self._add_label(group, label, points[1], color)
        if own:
            self.handle_group = self._placed(group)

    def _feature_span(self, prepared):
        bounds = []
        for body in prepared.get("bodies") or []:
            try:
                box = body.boundingBox
                bounds.append(math.dist((box.minPoint.x, box.minPoint.y, box.minPoint.z),
                                        (box.maxPoint.x, box.maxPoint.y, box.maxPoint.z)))
            except Exception:
                continue
        return max(bounds) if bounds else 0.0

    def _value_label(self, handle, fraction=None):
        """'12.5 mm' / '90 deg' from the real parameter (scaled by
        ``fraction`` during fast motion, where the parameter is not changed)."""
        param = handle.get("parameter")
        try:
            value = float(param.value) * (1.0 if fraction is None else fraction)
        except Exception:
            return ""
        angle = handle.get("unit") == "angle"
        unit = getattr(param, "unit", "") or ("deg" if angle else "mm")
        try:
            # Internal units are cm and rad; show at most two decimals.
            shown = self.design().unitsManager.convert(value, "rad" if angle else "cm", unit)
        except Exception:
            shown, unit = (math.degrees(value), "deg") if angle else (value * 10, "mm")
        return _short_number(shown) + " " + unit

    @staticmethod
    def _add_label(group, text, at, color):
        try:
            matrix = adsk.core.Matrix3D.create()
            for i in range(3):
                matrix.setCell(i, 3, at[i])
            label = group.addText(text, "Arial", 0.3, matrix)
            label.color = color
            label.isSelectable = False
            label.depthPriority = 3
            anchor = adsk.core.Point3D.create(*at)
            billboard = adsk.fusion.CustomGraphicsBillBoard.create(anchor)
            billboard.billBoardStyle = adsk.fusion.CustomGraphicsBillBoardStyles.ScreenBillBoardStyle
            label.billBoarding = billboard
            label.viewScale = adsk.fusion.CustomGraphicsViewScale.create(40, anchor)
        except Exception:
            pass                       # the value label is optional

    def _target_roles(self, entity, kind, targets, bodies):
        """Per target: "moving" / "body", when targets are copies of the
        feature's faces and the operation has a moving face; else None."""
        from .manipulator import moving_faces, MOVING, BODY
        moving = moving_faces(kind, entity)
        if not moving or any(t in bodies for t in targets):
            return None
        faces = _items(getattr(entity, "faces", None), self.MAX_FACE_HIGHLIGHTS + 1)
        if len(faces) != len(targets):
            return None
        return [MOVING if _token(f) in moving else BODY for f in faces]

    def _delete_handles(self):
        try:
            if self.handle_group is not None and self.handle_group.isValid:
                self.handle_group.deleteMe()
        except Exception:
            pass
        self.handle_group = None

    def _delete_fast(self):
        try:
            if self.fast_group is not None and self.fast_group.isValid:
                self.fast_group.deleteMe()
        except Exception:
            pass
        self.fast_group = None

    def _render(self, frame, settle=False):
        if frame.position != self.active_position:
            self._prepare(frame.position)
        prepared = self.active
        if prepared.get("fast"):
            if settle and not prepared.get("settled") and self._settle(prepared, frame.progress):
                pass                         # fall through to the native recompute below
            elif not settle and prepared.get("settled"):
                self._resume_fast(prepared)
            if self._moving(prepared):
                self._move_fast(prepared, frame.progress)
                self._refresh()
                return
        if prepared["mode"] == PARAMETRIC:
            failure = None
            if not self._set_together(prepared["params"], frame.progress):
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

    def _set_together(self, params, progress):
        """Several parameters of one feature (two-sided extrude, pattern
        X/Y, hole depth + diameter) in ONE recompute via
        Design.modifyParameters, instead of one recompute per parameter.
        False when not applicable or not available: set them one by one."""
        if len(params) < 2:
            return False
        design = self.design()
        modify = getattr(design, "modifyParameters", None)
        if modify is None:
            return False
        try:
            values = [adsk.core.ValueInput.createByReal(interpolate(target, progress))
                      for _, _, target in params]
            return modify([param for _, param, _ in params], values) is not False
        except Exception as error:
            self.log("HiM: batched parameter update unavailable: " + str(error))
            return False

    def _fallback(self, prepared, reason):
        """A parameter frame failed: put the real values back and show this
        feature with the visual effect instead (never a half-computed model)."""
        self.log("HiM: {}: {}; using the visual effect".format(prepared["feature"].name, reason))
        try:
            self.journal.restore([key for key, _, _ in prepared["params"]])
        except Exception as error:
            raise RuntimeError("Native fallback could not restore parameters: " + str(error)) from error
        prepared["mode"] = FADE
        prepared["fallback"] = reason
        if not prepared.get("wireframe"):
            try:
                self.focus.restore()
            except Exception as error:
                self.log("HiM focus restore before fallback: " + str(error))
            self._apply_focus(prepared["bodies"], hide_result=(
            not self.instant_nonparametric))
        # With an active ghost, keep the real model almost invisible and
        # switch ONLY the feature-owned overlay to the visual fade. Mixing
        # opaque source bodies with the ghost would break the isolation.

    def status(self):
        """What the active feature is doing: parameter animation or visual."""
        prepared = self.active
        if not prepared:
            return None
        return {"feature": prepared["feature"].name, "kind": prepared["feature"].kind,
                "mode": {PARAMETRIC: "parameter", FADE: (
                    "instant" if self.instant_nonparametric else "visual"
                )}.get(prepared["mode"], "timeline"),
                "parameters": [key for key, _, _ in prepared["params"]] if prepared["mode"] == PARAMETRIC else [],
                "fallback": prepared.get("fallback", ""),
                "wireframe": bool(prepared.get("wireframe")),
                "ghost_edges": prepared.get("ghost_edges", 0),
                "context_fallback": prepared.get("context_fallback", ""),
                "motion": self._motion_kind(prepared),
                "motion_note": self._motion_note(prepared)}

    MOTION_NOTES = {
        "exact": "Fast preview: same shape as Fusion's recompute",
        "approximate": "Fast preview: may differ where it meets other geometry; pause shows the real model",
        "illustrative": "Fast preview: illustrative motion; the end state is the real result",
    }

    def _motion_kind(self, prepared):
        if self._moving(prepared):
            return prepared["fast"].accuracy
        if prepared.get("settled"):
            return "settled"
        return "native"

    def _motion_note(self, prepared):
        kind = self._motion_kind(prepared)
        if kind == "settled":
            return "Paused: Fusion's real recompute at this point"
        if kind == "native":
            if not self.fast_motion or prepared["mode"] not in (PARAMETRIC, FADE):
                return ""
            reason = prepared.get("native_reason")
            if reason == REAL_GROWTH:
                return "Real growth: Fusion computes the feature at every step of its parameter"
            return "Fusion recomputes every frame" + (" (" + reason + ")" if reason else "")
        return self.MOTION_NOTES.get(kind, "")

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
        self._delete_fast()
        self._delete_handles()
        for sketch in self.hidden_sketches:
            try:
                sketch.isLightBulbOn = True
            except Exception as error:
                errors.append("sketch visibility: " + str(error))
        self.hidden_sketches = []
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
