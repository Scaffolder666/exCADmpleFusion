"""The tutorial a designer is preparing (authoring tool), as pure data.

While designing in Fusion the designer presses Record and thinks aloud.
Afterwards they have:
* the Timeline features of their design, each with the time (ms in the
  recording) at which it appeared, or None for features made before;
* what they said, as timed transcript segments.

A Draft groups features into reasoning steps. One step may span several
operations, because a reason often covers more than one feature. Each step
owns the slice of the recording ``[start_ms, end_ms)``; what was said in it
is the step's text, unless the designer typed their own.

Edits: merge two steps, split a step between two features, move the
boundary between two steps (e.g. one sentence earlier/later), rename, and
edit the text. Nothing here talks to Fusion. ``to_pair`` writes the
``excadmple-pair`` JSON the player loads (beside or inside the .f3d).
"""
import re

FORMAT = "excadmple-authoring"
SKETCH_KINDS = ("Sketch", "ConstructionPlane", "ConstructionAxis", "ConstructionPoint")
TAIL_MS = 1500           # speech right after a feature appears still belongs to it
MIN_STEP_MS = 500
MAX_STEP_MS = 3600000


class DraftError(ValueError):
    pass


def _short(text, limit=60):
    text = re.sub(r"\s+", " ", text or "").strip().rstrip(".。")
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def feature_label(feature):
    return feature["name"] or feature["kind"]


class Draft:
    def __init__(self, features, duration_ms, segments=(), steps=None):
        self.features = [{"index": int(f["index"]), "name": str(f.get("name") or f.get("kind") or ""),
                          "kind": str(f.get("kind") or ""),
                          "t_ms": None if f.get("t_ms") is None else max(0, int(f["t_ms"]))}
                         for f in sorted(features, key=lambda f: f["index"])]
        if not self.features:
            raise DraftError("The design has no Timeline features to explain")
        self.duration_ms = max(int(duration_ms or 0), MIN_STEP_MS * len(self.features))
        self.segments = []
        self.set_segments(segments)
        self.steps = []
        # Without any feature times the steps share the recording evenly,
        # and keep sharing it when its real length becomes known, until the
        # designer places a boundary by hand.
        self._spread = steps is None and all(f["t_ms"] is None for f in self.features)
        if steps is None:
            self.auto_group()
        else:
            self._load_steps(steps)

    # --- times ---------------------------------------------------------------------------
    def _time(self, position):
        """Recording time of feature ``position`` (features made before the
        recording count as time 0)."""
        t = self.features[position]["t_ms"]
        return 0 if t is None else min(t, self.duration_ms)

    def start_ms(self, i):
        return 0 if i == 0 else self.steps[i - 1]["end_ms"]

    def _boundary_after(self, last_position, next_position, low, latest, parts=2):
        """Where a step ending with feature ``last_position`` hands over to the
        one starting with ``next_position``: shortly after the last feature
        appeared, never after the next one appeared. Without usable times
        the span from ``low`` is shared out evenly among ``parts`` steps."""
        end = min(self._time(last_position) + TAIL_MS, self._time(next_position))
        if end <= low:
            end = low + (latest + MIN_STEP_MS * (parts - 1) - low) // parts
        return max(low + MIN_STEP_MS, min(end, latest))

    # --- grouping ------------------------------------------------------------------------
    def auto_group(self):
        """One step per modeling feature, with the sketches made for it."""
        groups, pending = [], []
        for position, feature in enumerate(self.features):
            pending.append(position)
            if feature["kind"] not in SKETCH_KINDS:
                groups.append(pending)
                pending = []
        if pending:
            if groups:
                groups[-1].extend(pending)
            else:
                groups.append(pending)
        self.steps = []
        low = 0
        for i, group in enumerate(groups):
            remaining = len(groups) - 1 - i
            if remaining:
                end = self._boundary_after(group[-1], groups[i + 1][0], low,
                                           self.duration_ms - MIN_STEP_MS * remaining, remaining + 1)
            else:
                end = self.duration_ms
            self.steps.append(self._new_step(group, end))
            low = end

    def _new_step(self, positions, end_ms):
        return {"features": list(positions), "end_ms": int(end_ms), "title": None, "text": None}

    def _load_steps(self, steps):
        positions = {f["index"]: p for p, f in enumerate(self.features)}
        used, last, low = set(), -1, 0
        for i, raw in enumerate(steps):
            group = [positions.get(index) for index in raw.get("features", [])]
            if not group or None in group:
                raise DraftError("Step {} refers to a feature that is not in the design".format(i + 1))
            if group[0] <= last or group != list(range(group[0], group[-1] + 1)):
                raise DraftError("Step {}: features must be consecutive and in Timeline order".format(i + 1))
            last = group[-1]
            used.update(group)
            end = self.duration_ms if i == len(steps) - 1 else int(raw.get("end_ms", 0))
            if not low < end <= self.duration_ms:
                raise DraftError("Step {} has an invalid time range".format(i + 1))
            step = self._new_step(group, end)
            step["title"] = raw.get("title") or None
            step["text"] = raw.get("text")
            self.steps.append(step)
            low = end
        if len(used) != len(self.features):
            raise DraftError("Every Timeline feature must belong to one step")

    def _check(self, i):
        if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(self.steps):
            raise DraftError("No step {}".format(i))

    def merge(self, i):
        """Join step ``i`` with the next one (one reason, several operations)."""
        self._check(i)
        if i + 1 >= len(self.steps):
            raise DraftError("The last step has no next step to merge with")
        first, second = self.steps[i], self.steps[i + 1]
        if first["text"] is not None or second["text"] is not None:
            # Keep the designer's own words of both parts.
            joined = " ".join(t for t in (self.text(i), self.text(i + 1)) if t)
        else:
            joined = None
        del self.steps[i + 1]
        first["features"] += second["features"]
        first["end_ms"] = second["end_ms"]
        first["text"] = joined
        if first["title"] is None and second["title"] is not None:
            first["title"] = second["title"]

    def split(self, i, at):
        """Split step ``i`` before its ``at``-th feature (1 .. n-1)."""
        self._check(i)
        step = self.steps[i]
        if isinstance(at, bool) or not isinstance(at, int) or not 0 < at < len(step["features"]):
            raise DraftError("Choose a place between two features of the step")
        low, high = self.start_ms(i), step["end_ms"]
        if high - low < 2 * MIN_STEP_MS:
            raise DraftError("This step is too short to split")
        boundary = self._boundary_after(step["features"][at - 1], step["features"][at], low,
                                        high - MIN_STEP_MS)
        second = self._new_step(step["features"][at:], high)
        step["features"] = step["features"][:at]
        step["end_ms"] = boundary
        if step["text"] is not None:
            second["text"] = ""          # the designer's own text stays with the first part
        self.steps.insert(i + 1, second)

    def set_boundary(self, i, end_ms):
        """Move the end of step ``i`` (= start of step ``i+1``)."""
        self._check(i)
        if i + 1 >= len(self.steps):
            raise DraftError("The last step always ends with the recording")
        end_ms = int(end_ms)
        self._spread = False
        if not self.start_ms(i) + MIN_STEP_MS <= end_ms <= self.steps[i + 1]["end_ms"] - MIN_STEP_MS:
            raise DraftError("A step must keep at least half a second of the recording")
        self.steps[i]["end_ms"] = end_ms

    def move_sentence(self, i, direction):
        """Give step ``i``'s first sentence to the previous step (direction -1)
        or its last sentence to the next step (+1)."""
        self._check(i)
        said = self.sentences(i)
        if not said:
            raise DraftError("Nothing was said in this step")
        if direction < 0:
            if i == 0:
                raise DraftError("The first step has no previous step")
            following = said[1]["start_ms"] if len(said) > 1 else self.steps[i]["end_ms"]
            target = min(said[0].get("end_ms", said[0]["start_ms"]) + 1, following)
            self.set_boundary(i - 1, max(target, self.start_ms(i) + 1))
        else:
            if i + 1 >= len(self.steps):
                raise DraftError("The last step has no next step")
            self.set_boundary(i, said[-1]["start_ms"])

    def rename(self, i, title):
        self._check(i)
        title = _short(str(title or ""), 120)
        self.steps[i]["title"] = title or None

    def set_text(self, i, text):
        """The designer's own words for this step; None goes back to what was said."""
        self._check(i)
        self.steps[i]["text"] = None if text is None else str(text)

    def set_segments(self, segments):
        cleaned, last = [], 0
        for seg in segments or ():
            text = str(seg.get("text", "")).strip()
            start = int(seg.get("start_ms", 0))
            end = int(seg.get("end_ms", start))
            if not text:
                continue
            if start < last or end < start:
                raise DraftError("Transcript segments must be in time order")
            last = start
            cleaned.append({"start_ms": start, "end_ms": end, "text": text})
        self.segments = cleaned
        if cleaned and cleaned[-1]["end_ms"] > self.duration_ms:
            if getattr(self, "steps", None):
                self.set_duration(cleaned[-1]["end_ms"])
            else:
                self.duration_ms = cleaned[-1]["end_ms"]

    def set_duration(self, duration_ms):
        """The recording's real length (known once the audio is loaded)."""
        last_said = self.segments[-1]["end_ms"] if self.segments else 0
        if self._spread:
            old, new = self.duration_ms, max(int(duration_ms), MIN_STEP_MS * len(self.steps), last_said)
            for step in self.steps[:-1]:
                step["end_ms"] = int(round(step["end_ms"] * new / old))
            self.duration_ms = self.steps[-1]["end_ms"] = new
            return
        floor = self.start_ms(len(self.steps) - 1) + MIN_STEP_MS
        self.duration_ms = max(int(duration_ms), floor, last_said)
        self.steps[-1]["end_ms"] = self.duration_ms

    # --- reading -------------------------------------------------------------------------
    def _said(self, start, end):
        return [s for s in self.segments if start <= s["start_ms"] < end]

    def sentences(self, i):
        self._check(i)
        return self._said(self.start_ms(i), self.steps[i]["end_ms"])

    def _step_text(self, step, i):
        if step["text"] is not None:
            return step["text"]
        return " ".join(s["text"] for s in self._said(self.start_ms(i), step["end_ms"]))

    def text(self, i):
        self._check(i)
        return self._step_text(self.steps[i], i)

    def title(self, i):
        self._check(i)
        step = self.steps[i]
        if step["title"]:
            return step["title"]
        said = self.sentences(i)
        if said and step["text"] is None:
            return _short(said[0]["text"])
        names = [feature_label(self.features[p]) for p in step["features"]
                 if self.features[p]["kind"] not in SKETCH_KINDS]
        return " + ".join(names) or feature_label(self.features[step["features"][-1]])

    def view(self):
        """What the authoring panel shows."""
        out = []
        for i, step in enumerate(self.steps):
            out.append({
                "title": self.title(i), "title_edited": step["title"] is not None,
                "features": [dict(self.features[p]) for p in step["features"]],
                "start_ms": self.start_ms(i), "end_ms": step["end_ms"],
                "sentences": self.sentences(i), "text": self.text(i),
                "text_edited": step["text"] is not None,
            })
        return {"duration_ms": self.duration_ms, "steps": out,
                "has_transcript": bool(self.segments)}

    # --- saving --------------------------------------------------------------------------
    def to_dict(self):
        return {"format": FORMAT, "version": 1, "duration_ms": self.duration_ms,
                "features": [dict(f) for f in self.features], "segments": [dict(s) for s in self.segments],
                "steps": [{"features": [self.features[p]["index"] for p in s["features"]],
                           "end_ms": s["end_ms"], "title": s["title"], "text": s["text"]}
                          for s in self.steps]}

    @classmethod
    def from_dict(cls, data, features=None):
        """Reopen a saved draft. ``features`` (the design's current Timeline)
        must still contain the same features; otherwise start over."""
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise DraftError("Not an exCADmple authoring draft")
        saved = data.get("features") or []
        if features is not None:
            now = [(int(f["index"]), f.get("name"), f.get("kind")) for f in features]
            then = [(f["index"], f["name"], f["kind"]) for f in saved]
            if now != then:
                raise DraftError("The design's Timeline changed since this tutorial was prepared")
        return cls(saved, data.get("duration_ms", 0), data.get("segments", []), data.get("steps"))

    def to_pair(self, model, title="", audio=None):
        """The excadmple-pair JSON the player loads. With ``audio`` (one long
        think-aloud recording), each step plays its own slice of it."""
        steps = []
        for i, view in enumerate(self.view()["steps"]):
            start, end = view["start_ms"], view["end_ms"]
            duration = max(MIN_STEP_MS, min(MAX_STEP_MS, end - start))
            item = {
                "id": "step-{}".format(i + 1), "title": view["title"],
                "features": [{"index": f["index"], "name": f["name"], "kind": f["kind"]}
                             for f in view["features"]],
                "duration_ms": duration, "transcript": view["text"],
                "reasoning_source": "author" if view["text_edited"] else "recorded",
            }
            if not view["text_edited"]:
                item["cues"] = [{"at_ms": max(0, min(duration, s["start_ms"] - start)), "label": s["text"]}
                                for s in view["sentences"]]
            if audio:
                item["audio"] = audio
                item["audio_offset_ms"] = start
                item["audio_slice"] = True
            steps.append(item)
        pair = {"format": "excadmple-pair", "version": 1, "model": model,
                "title": title or model.rsplit(".", 1)[0], "auto_generate": False,
                "steps": steps, "authoring": self.to_dict()}
        return pair


def draft_from_recording(features, session, audio_start_ms=0, audio_duration_ms=None):
    """A first Draft from the design's final Timeline and the recorder's log.

    ``features``: (index, name, kind) items of the Timeline when recording
    stopped (features undone during the recording are not in it).
    ``audio_start_ms``: session time at which the voice recording started
    (negative when it started before Record was pressed). All draft times
    are recording (audio) times, so transcripts line up without shifting.
    """
    logged = (session or {}).get("features", [])
    items = []
    for index, name, kind in features:
        match = next((e for e in logged if e["index"] == index and e["name"] == name), None) \
            or next((e for e in logged if e["name"] == name), None)
        t = None if match is None else max(0, match["t_ms"] - audio_start_ms)
        items.append({"index": index, "name": name, "kind": kind, "t_ms": t})
    duration = audio_duration_ms
    if duration is None:
        duration = max(0, (session or {}).get("duration_ms", 0) - audio_start_ms)
    return Draft(items, duration)
