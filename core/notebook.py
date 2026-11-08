"""Reasoning notebook: what the user did with an example's reasoning.

Each entry records one reuse decision — adopt, adapt, not use, or undecided —
for one example decision, optionally tied to one of the user's own features,
with the user's own words. The notebook is stored with the user's design
(Fusion design attributes) and can be exported as JSON or CSV for research.
"""
import csv
import io
import json
import time
import uuid

STANCES = ("adopt", "adapt", "reject", "undecided")
STANCE_LABELS = {"adopt": "Adopt", "adapt": "Adapt", "reject": "Not use", "undecided": "Undecided"}
VERSION = 1
MAX_ENTRIES = 500
FIELDS = ("id", "created_at", "updated_at", "stance", "note", "example_id", "example_title",
          "step_id", "step_title", "topic", "question", "example_choice", "user_feature",
          "user_feature_key", "user_value")


class NotebookError(ValueError):
    pass


def _clean(value, limit=2000):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.strip()[:limit]


class Notebook:
    def __init__(self, load=None, save=None, clock=time.time):
        self._load, self._save, self._clock = load, save, clock
        self.entries = []
        if load:
            self.reload()

    def reload(self):
        raw = self._load() if self._load else None
        self.entries = self.parse(raw) if raw else []

    @staticmethod
    def parse(raw):
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise NotebookError("Notebook data is not valid JSON") from error
        if not isinstance(data, dict) or data.get("version") != VERSION:
            raise NotebookError("Unsupported notebook version")
        entries = data.get("entries", [])
        if not isinstance(entries, list):
            raise NotebookError("Notebook entries must be a list")
        return [{k: _clean(e.get(k)) for k in FIELDS} for e in entries if isinstance(e, dict)]

    def dumps(self):
        return json.dumps({"version": VERSION, "entries": self.entries}, ensure_ascii=False)

    def _persist(self):
        if self._save:
            self._save(self.dumps())

    def _stamp(self):
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self._clock()))

    def record(self, stance, ref, note="", feature=None, user_value=""):
        """Add or update the entry for (example decision, user feature)."""
        if stance not in STANCES:
            raise NotebookError("Stance must be one of " + ", ".join(STANCES))
        feature = feature or {}
        key = (ref["example_id"], ref["step_id"], _clean(feature.get("key")))
        for entry in self.entries:
            if (entry["example_id"], entry["step_id"], entry["user_feature_key"]) == key:
                entry.update(stance=stance, note=_clean(note), user_value=_clean(user_value),
                             updated_at=self._stamp())
                self._persist()
                return entry
        if len(self.entries) >= MAX_ENTRIES:
            raise NotebookError("Notebook is full")
        choice = next((o for o in ref.get("options", []) if o.get("chosen")), None)
        now = self._stamp()
        entry = {
            "id": uuid.uuid4().hex[:12], "created_at": now, "updated_at": now,
            "stance": stance, "note": _clean(note),
            "example_id": _clean(ref["example_id"]), "example_title": _clean(ref.get("example_title")),
            "step_id": _clean(ref["step_id"]), "step_title": _clean(ref.get("step_title")),
            "topic": _clean(ref.get("topic")), "question": _clean(ref.get("question")),
            "example_choice": _clean(choice["label"] if choice else ""),
            "user_feature": _clean(feature.get("name")), "user_feature_key": _clean(feature.get("key")),
            "user_value": _clean(user_value),
        }
        self.entries.append(entry)
        self._persist()
        return entry

    def remove(self, entry_id):
        before = len(self.entries)
        self.entries = [e for e in self.entries if e["id"] != entry_id]
        if len(self.entries) == before:
            raise NotebookError("No such notebook entry")
        self._persist()

    def stance_for(self, example_id, step_id, feature_key=""):
        for entry in self.entries:
            if (entry["example_id"], entry["step_id"], entry["user_feature_key"]) == (example_id, step_id, feature_key or ""):
                return entry
        return None

    def summary(self):
        counts = {s: 0 for s in STANCES}
        for entry in self.entries:
            counts[entry["stance"]] = counts.get(entry["stance"], 0) + 1
        return counts

    def to_csv(self):
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=FIELDS)
        writer.writeheader()
        for entry in self.entries:
            writer.writerow(entry)
        return buffer.getvalue()
