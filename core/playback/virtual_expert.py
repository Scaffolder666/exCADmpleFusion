"""Publish a *read-only* virtual demonstrator stream to a macOS overlay.

This module NEVER invokes a Fusion command, changes the user's selection,
sends a real mouse event, or modifies the learner's Feature Timeline.
The separate overlay process draws a teacher cursor over the actual Fusion UI.
"""
import json
import os
import time
from pathlib import Path

STATE_DIR = Path.home() / "Library" / "Application Support" / "exCADmple"
STATE_FILE = STATE_DIR / "expert_state.json"


def _reason(step, progress):
    if step.get("reasoning_source") in ("simulated", "hypothetical"):
        return ""  # Never present a generated hypothesis as the author's intent.
    elapsed = max(0, float(progress)) * float(step.get("duration_ms") or 8000)
    candidates = [
        c for c in step.get("cues") or []
        if float(c.get("at_ms", 0)) <= elapsed
        and str(c.get("label", "")).strip()
    ]
    if not candidates:
        return ""
    return str(candidates[-1].get("label", "")).strip()[:230]


def _parameters(step):
    values = []
    for feature in step.get("source_features") or []:
        for key in ("parameters", "params"):
            for item in feature.get(key) or []:
                if isinstance(item, dict):
                    label = item.get("name") or item.get("label") or ""
                    value = item.get("expression") or item.get("value") or ""
                    if label or value:
                        values.append("%s = %s" % (label, value))
    for item in step.get("parameters") or []:
        if isinstance(item, dict):
            values.append("%s = %s" % (item.get("name", ""), item.get("expression", "")))
    return values[:8]


def semantic_phase(progress):
    """0 tool, 1 selection, 2 parameter interaction, 3 confirm."""
    return min(3, max(0, int(float(progress) * 4)))


class VirtualExpert:
    def __init__(self, output=STATE_FILE, clock=time.monotonic):
        self.output = Path(output)
        self.clock = clock
        self.step = None
        self.index = 0
        self.last = 0
        self.enabled = True
        self.current_progress = 0
        self.screen_anchor = None

    def publish(self, progress=0, playing=False, force=False):
        if not self.enabled or self.step is None:
            return
        now = self.clock()
        if not force and now - self.last < .07:
            return
        self.last = now
        self.current_progress = max(0, min(1, float(progress)))
        step = self.step
        tools = [str(t) for t in step.get("tools", []) if t]
        obj = {
            "format": "excadmple.virtual-expert.v1",
            "updated_at": time.time(),
            "active": True,
            "playing": bool(playing),
            "index": self.index,
            "step": str(step.get("title", "Step %d" % (self.index+1))),
            "tool": tools[0] if tools else "CAD operation",
            "tools": tools,
            "parameters": _parameters(step),
            "reason": _reason(step, progress),
            "phase": semantic_phase(progress),
            "progress": max(0, min(1, float(progress))),
            "model": str(step.get("id", "")),
            "screen_anchor": self.screen_anchor,
        }
        self.output.parent.mkdir(parents=True, exist_ok=True)
        temp = self.output.with_suffix(".tmp")
        temp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        os.replace(str(temp), str(self.output))

    def set_step(self, index, step):
        self.index = int(index)
        self.step = step
        self.current_progress = 0
        self.screen_anchor = None
        self.publish(0, False, force=True)

    def frame(self, index, step, progress, screen_anchor=None):
        if self.index != index or self.step is None:
            self.set_step(index, step)
        self.screen_anchor = screen_anchor
        self.publish(progress, playing=True)

    def pause(self):
        self.publish(self.current_progress, playing=False, force=True)

    def close(self):
        self.step = None
        try:
            self.output.unlink()
        except FileNotFoundError:
            pass
