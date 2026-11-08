"""Design Reasoning Reuse: connect the user's own CAD features to the
decisions recorded in design examples.

Pure Python. Matching is deliberately rule-based and explainable:

* feature type — the user's feature has a type the decision applies to
  (``decision.applies_to.features``),
* name tags — the user's feature or parameter names contain an author tag
  (``decision.applies_to.tags``),
* parameter kind — the user's feature has a length/angle parameter of the
  kind the decision is about.

Every match carries the human-readable reasons it was made. Nothing here
generates reasoning: the rationale shown is always the example author's.
"""
import math
import re

LENGTH_UNITS = {"mm": 0.1, "cm": 1.0, "m": 100.0, "in": 2.54, "ft": 30.48}
ANGLE_UNITS = {"deg": math.pi / 180, "°": math.pi / 180, "rad": 1.0}
KINDS = ("length", "angle", "count")
STRONG, NAME, TYPE = "strong", "name", "type"
FEATURE_LABELS = {
    "ExtrudeFeature": "Extrude", "RevolveFeature": "Revolve", "FilletFeature": "Fillet",
    "ChamferFeature": "Chamfer", "HoleFeature": "Hole", "ShellFeature": "Shell",
    "CircularPatternFeature": "Circular pattern", "RectangularPatternFeature": "Rectangular pattern",
    "MirrorFeature": "Mirror", "CombineFeature": "Combine", "MoveFeature": "Move",
    "SweepFeature": "Sweep", "LoftFeature": "Loft", "RibFeature": "Rib", "WebFeature": "Web",
    "ThreadFeature": "Thread", "SplitBodyFeature": "Split body", "DraftFeature": "Draft",
}


class ReuseError(ValueError):
    pass


def _text(value, field, required=True, limit=600):
    if value is None and not required:
        return
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ReuseError("Decision " + field + " must be a non-empty string")


def validate_decision(data):
    if not isinstance(data, dict):
        raise ReuseError("Decision must be an object")
    _text(data.get("topic"), "topic", limit=80)
    if not re.fullmatch(r"[a-z0-9_\-]+", data["topic"]):
        raise ReuseError("Decision topic must be a lowercase identifier")
    _text(data.get("question"), "question")
    criteria = data.get("criteria", [])
    if not isinstance(criteria, list) or len(criteria) > 12:
        raise ReuseError("Decision criteria must be a list")
    for item in criteria:
        _text(item, "criterion", limit=200)
    options = data.get("options")
    if not isinstance(options, list) or not 1 <= len(options) <= 8:
        raise ReuseError("Decision needs 1–8 options")
    chosen = 0
    for option in options:
        if not isinstance(option, dict):
            raise ReuseError("Option must be an object")
        _text(option.get("label"), "option label", limit=120)
        if option.get("value") is not None:
            parse_quantity(option["value"])
        if option.get("chosen"):
            chosen += 1
        if option.get("note") is not None and not isinstance(option["note"], str):
            raise ReuseError("Option note must be a string")
    if chosen > 1:
        raise ReuseError("At most one option can be chosen")
    parameter = data.get("parameter")
    if parameter is not None:
        if not isinstance(parameter, dict) or parameter.get("kind") not in KINDS:
            raise ReuseError("Decision parameter needs kind length, angle or count")
        _text(parameter.get("name"), "parameter name", limit=120)
        value, kind = parse_quantity(parameter.get("value"))
        if kind != parameter["kind"]:
            raise ReuseError("Decision parameter value does not match its kind")
    applies = data.get("applies_to", {})
    if not isinstance(applies, dict):
        raise ReuseError("applies_to must be an object")
    for key in ("features", "tags"):
        values = applies.get(key, [])
        if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
            raise ReuseError("applies_to." + key + " must be a list of strings")
    return data


def parse_quantity(text):
    """'80 mm' -> (8.0, 'length') in Fusion internal units (cm, radians);
    '65 deg' / '65°' -> (1.134, 'angle'); '4' -> (4.0, 'count')."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text), "count"
    if not isinstance(text, str):
        raise ReuseError("Quantity must be a string such as '8 mm'")
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(mm|cm|m|in|ft|deg|°|rad)?\s*", text)
    if not match:
        raise ReuseError("Cannot read quantity: " + text)
    number, unit = float(match.group(1)), match.group(2)
    if unit in LENGTH_UNITS:
        return number * LENGTH_UNITS[unit], "length"
    if unit in ANGLE_UNITS:
        return number * ANGLE_UNITS[unit], "angle"
    return number, "count"


def unit_kind(unit):
    unit = (unit or "").strip().lower()
    if unit in LENGTH_UNITS:
        return "length"
    if unit in ("deg", "rad", "°"):
        return "angle"
    return "count" if unit in ("", "no units") else None


def format_quantity(value, kind, unit=None):
    if kind == "length":
        unit = unit if unit in LENGTH_UNITS else "mm"
        return "{:g} {}".format(round(value / LENGTH_UNITS[unit], 2), unit)
    if kind == "angle":
        return "{:g}°".format(round(math.degrees(value), 1))
    return "{:g}".format(round(value, 2))


def _unit_of(text):
    match = re.search(r"(mm|cm|m|in|ft)\s*$", text or "")
    return match.group(1) if match else None


def tokens(*names):
    words = set()
    for name in names:
        name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name or "")
        words.update(w for w in re.split(r"[^a-zA-Z]+", name.lower()) if len(w) > 2)
    return words


# --- library of decisions ---------------------------------------------------------
def collect_decisions(examples):
    """examples: iterable of (example_id, example_data). Returns decision refs."""
    refs = []
    for example_id, data in examples:
        for index, step in enumerate(data.get("steps", [])):
            decision = step.get("decision")
            if not decision:
                continue
            reasoning = step.get("reasoning") or {}
            refs.append({
                "example_id": example_id, "example_title": data.get("title", example_id),
                "step_index": index, "step_id": step["id"], "step_title": step["title"],
                "topic": decision["topic"], "question": decision["question"],
                "criteria": decision.get("criteria", []), "options": decision["options"],
                "parameter": decision.get("parameter"),
                "applies_to": decision.get("applies_to", {}),
                "rationale": reasoning.get("text", ""), "source": reasoning.get("source", ""),
                "tool": (step.get("operation") or {}).get("tool", ""),
            })
    return refs


def chosen_option(ref):
    for option in ref["options"]:
        if option.get("chosen"):
            return option
    return None


def by_topic(refs):
    """Same question across examples -> list of each example's answer."""
    topics = {}
    for ref in refs:
        topic = topics.setdefault(ref["topic"], {"topic": ref["topic"], "question": ref["question"],
                                                 "answers": []})
        choice = chosen_option(ref)
        topic["answers"].append({
            "example_id": ref["example_id"], "example_title": ref["example_title"],
            "step_index": ref["step_index"], "step_id": ref["step_id"], "step_title": ref["step_title"],
            "choice": choice["label"] if choice else None,
            "value": choice.get("value") if choice else None,
            "note": choice.get("note", "") if choice else "", "rationale": ref["rationale"],
        })
    return sorted(topics.values(), key=lambda t: (-len(t["answers"]), t["topic"]))


# --- matching -------------------------------------------------------------------------
def match_feature(feature, refs, limit=6):
    """Rank decisions for one user feature (dict with name, kind, parameters)."""
    kind = feature.get("kind", "")
    params = feature.get("parameters", [])
    words = tokens(feature.get("name", ""), *[p.get("name", "") for p in params])
    param_kinds = {unit_kind(p.get("unit")) for p in params}
    label = FEATURE_LABELS.get(kind, kind)
    results = []
    for ref in refs:
        applies = ref["applies_to"]
        reasons, score = [], 0.0
        type_match = kind in applies.get("features", [])
        if type_match:
            score += 2
            reasons.append("Your {} is a {} feature; this decision was made with {}.".format(
                feature.get("name", "feature"), label, ref["tool"] or label))
        tags = sorted(words & {t.lower() for t in applies.get("tags", [])})
        if tags:
            score += 1.5 * min(2, len(tags))
            reasons.append("Its name mentions " + ", ".join("“" + t + "”" for t in tags) + ".")
        parameter = ref.get("parameter")
        if parameter and parameter["kind"] in param_kinds and (type_match or tags):
            score += 0.5
            reasons.append("It has a {} parameter, like “{}”.".format(parameter["kind"], parameter["name"]))
        if not (type_match or tags):
            continue
        level = STRONG if type_match and tags else (NAME if tags else TYPE)
        results.append({"ref": ref, "score": score, "level": level, "reasons": reasons,
                        "comparison": compare(ref, params)})
    results.sort(key=lambda r: (-r["score"], r["ref"]["example_title"], r["ref"]["step_index"]))
    return results[:limit]


def match_features(features, refs, limit=6):
    """For each of the user's filtered features, its ranked decisions."""
    return [{"feature": f, "matches": match_feature(f, refs, limit)} for f in features]


def compare(ref, user_params):
    """Put the user's own value next to the example's options. Informational
    only: no option is called right or wrong for the user's design."""
    parameter = ref.get("parameter")
    if not parameter:
        return None
    candidates = [p for p in user_params if unit_kind(p.get("unit")) == parameter["kind"]
                  and isinstance(p.get("value"), (int, float))]
    if not candidates:
        return None
    user = candidates[0]
    example_value, kind = parse_quantity(parameter["value"])
    unit = _unit_of(parameter["value"])
    options = []
    for option in ref["options"]:
        if option.get("value") is None:
            continue
        value, option_kind = parse_quantity(option["value"])
        if option_kind == kind:
            options.append((abs(value - user["value"]), option["label"], value))
    nearest = min(options)[1] if options else None
    return {
        "parameter": parameter["name"],
        "example_value": format_quantity(example_value, kind, unit),
        "user_parameter": user.get("name", ""),
        "user_value": format_quantity(user["value"], kind, unit),
        "user_expression": user.get("expression", ""),
        "nearest_option": nearest,
        "difference": format_quantity(user["value"] - example_value, kind, unit),
        "note": ("Angles may be measured from a different reference in your model."
                 if kind == "angle" else ""),
    }
