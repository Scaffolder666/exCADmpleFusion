"""A diagnostic log the researcher can send after a run.

Every add-in start writes one file in ``<add-in>/logs/`` and keeps a copy
as ``logs/latest.log``: the build, Fusion version and OS, the tutorial that
was loaded, how each feature was played (fast motion or Fusion recompute,
and why), slow frames, the tools found for each step, panel script errors
and full tracebacks. Pure Python; never raises into the add-in.
"""
import json
import platform
import time
import traceback
from pathlib import Path

KEEP = 10                       # older session logs are deleted
MAX_BYTES = 5 * 1024 * 1024     # a single log stops growing beyond this


class DiagnosticLog:
    def __init__(self, folder, build=""):
        self.folder = Path(folder)
        self.build = build
        self.path = None
        self.latest = None
        self.size = 0
        self.closed = False
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            self.path = self.folder / "session-{}.log".format(stamp)
            self.latest = self.folder / "latest.log"
            for path in (self.path, self.latest):
                path.write_text("", encoding="utf-8")
            self._prune()
        except Exception:
            self.path = self.latest = None

    def _prune(self):
        sessions = sorted(self.folder.glob("session-*.log"))
        for old in sessions[:-KEEP]:
            try:
                old.unlink()
            except Exception:
                pass

    def write(self, category, message, data=None):
        """One line: time, category, message (and optional JSON data)."""
        if self.path is None or self.closed:
            return
        line = "{} [{}] {}".format(time.strftime("%H:%M:%S"), category, message)
        if data is not None:
            try:
                line += " " + json.dumps(data, ensure_ascii=False, default=str, sort_keys=True)
            except Exception:
                line += " " + repr(data)
        line += "\n"
        if self.size + len(line) > MAX_BYTES:
            line = "{} [log] size limit reached; later events are not written\n".format(time.strftime("%H:%M:%S"))
            self.closed = True
        try:
            for path in (self.path, self.latest):
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
            self.size += len(line)
        except Exception:
            pass

    def header(self, **fields):
        info = {"build": self.build, "python": platform.python_version(),
                "os": "{} {}".format(platform.system(), platform.release())}
        info.update(fields)
        self.write("start", "exCADmple diagnostic log", info)

    def exception(self, context=""):
        """The current exception's full traceback."""
        self.write("error", context or "exception", {"traceback": traceback.format_exc()})
