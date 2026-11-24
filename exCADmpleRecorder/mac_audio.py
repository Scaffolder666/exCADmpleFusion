"""Launch the local AVFoundation helper and receive one finalized clip."""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


class MacAudio:
    def __init__(self, app, folder):
        self.folder = Path(tempfile.mkdtemp(prefix=".mic-", dir=folder))
        self.started = time.monotonic()
        try:
            self.launch = subprocess.Popen(
                ["/usr/bin/open", "-g", "-n", "-a", str(app), "--args", str(self.folder), str(os.getpid())],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError:
            shutil.rmtree(self.folder)
            raise

    def ready(self):
        return (self.folder / "ready").is_file()

    def error(self):
        error = self.folder / "error"
        if error.is_file():
            return error.read_text(encoding="utf-8")
        if self.launch.poll() not in (None, 0):
            return "Could not open exCADmple Microphone. Run the macOS setup command again."
        if not self.ready() and time.monotonic() - self.started > 50:
            return "The Mac microphone did not start. Check microphone access for exCADmple Microphone."
        return None

    def finish(self, target=None):
        (self.folder / "stop").touch()
        done = self.folder / "done"
        deadline = time.monotonic() + 1.5
        try:
            while not done.is_file():
                error = self.error()
                if error:
                    raise ValueError(error)
                if time.monotonic() >= deadline:
                    raise ValueError("The Mac recording did not finish. Please record it again.")
                time.sleep(0.025)
            duration = int(done.read_text(encoding="utf-8") or 0)
            if target is not None and duration > 0:
                (self.folder / "voice.wav").replace(target)
            return duration
        finally:
            if done.is_file() or (self.folder / "error").is_file() or self.launch.poll() not in (None, 0):
                shutil.rmtree(self.folder, ignore_errors=True)
            # Otherwise leave the stop file for a helper that is still launching.
