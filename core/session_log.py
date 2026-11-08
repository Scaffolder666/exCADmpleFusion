"""What happens while a designer records a tutorial in Fusion.

Pure Python (the Fusion glue is core/session_recorder.py). Times are
milliseconds since the recording started, the same clock as the screen
recording when both are started together.

Logged:
* commands — the tools the designer clicked (Fusion command starts);
* features — each timeline item created, with the time it appeared;
* selections — the 3D point (cm) of what the designer selected, which the
  player shows as the designer's pointer.
"""
import json
import time

FORMAT = "excadmple-session"
MAX_EVENTS = 20000


class SessionLog:
    def __init__(self, clock=time.monotonic, wall=time.time):
        self._clock = clock
        self._start = clock()
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(wall()))
        self.commands, self.features, self.selections = [], [], []
        self._known = set()

    def now_ms(self):
        return int(round((self._clock() - self._start) * 1000))

    def _room(self):
        return len(self.commands) + len(self.features) + len(self.selections) < MAX_EVENTS

    def command(self, command_id, name):
        if self._room() and command_id:
            self.commands.append({"t_ms": self.now_ms(), "id": command_id, "name": name or command_id})

    def timeline(self, items):
        """items: (index, name, kind) of the whole timeline; new ones are logged."""
        t = self.now_ms()
        for index, name, kind in items:
            key = (index, name)
            if key not in self._known and self._room():
                self._known.add(key)
                self.features.append({"t_ms": t, "index": index, "name": name, "kind": kind})

    def baseline(self, items):
        """Items already in the design before recording are not logged."""
        for index, name, _kind in items:
            self._known.add((index, name))

    def selection(self, xyz, kind):
        if self._room() and xyz is not None:
            self.selections.append({"t_ms": self.now_ms(), "xyz": [round(float(c), 4) for c in xyz],
                                    "kind": kind})

    def to_dict(self):
        return {"format": FORMAT, "version": 1, "started_at": self.started_at,
                "duration_ms": self.now_ms(), "commands": self.commands,
                "features": self.features, "selections": self.selections}


def load(path):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("Not an exCADmple session log")
    for key in ("commands", "features", "selections"):
        if not isinstance(data.get(key), list):
            raise ValueError("Session log needs " + key)
    return data


# Commands that are navigation or UI, not modeling tools the designer chose.
IGNORED_COMMANDS = ("SelectCommand", "PanCommand", "OrbitCommand", "ZoomCommand", "FitCommand",
                    "UndoCommand", "RedoCommand", "ViewCube", "NavigationBar", "excadmple")


def tools_between(session, start_ms, end_ms):
    """Distinct tool names the designer used in [start, end), in order."""
    names = []
    for item in session.get("commands", []):
        if not start_ms <= item["t_ms"] < end_ms:
            continue
        if any(ignored.lower() in item["id"].lower() for ignored in IGNORED_COMMANDS):
            continue
        if item["name"] not in names:
            names.append(item["name"])
    return names


def pointer_between(session, start_ms, end_ms, offset_ms=0):
    """The designer's selections in [start, end) as a pointer path relative
    to the step (``offset_ms`` shifts session time to recording time)."""
    path = []
    for item in session.get("selections", []):
        t = item["t_ms"] + offset_ms
        if start_ms <= t < end_ms:
            path.append({"at_ms": int(t - start_ms), "xyz": item["xyz"], "event": "click"})
    return path
