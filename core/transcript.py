"""Timestamped transcripts of the designer's think-aloud recording.

Reads SubRip (.srt), WebVTT (.vtt) or JSON ``[{start_ms, end_ms, text}]``.
Times refer to the whole recording.
"""
import json
import re
from pathlib import Path

TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


class TranscriptError(ValueError):
    pass


def _ms(text):
    match = TIME.fullmatch(text.strip())
    if not match:
        raise TranscriptError("Bad timestamp: " + text)
    hours, minutes, seconds, fraction = match.groups()
    return ((int(hours or 0) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(fraction.ljust(3, "0"))


def parse_cues(text):
    """SRT or VTT text -> segments."""
    segments = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = [line for line in block.split("\n") if line.strip()]
        timing = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing is None:
            continue           # WEBVTT header, NOTE blocks, cue numbers alone
        start, end = lines[timing].split("-->")
        end = end.strip().split(" ")[0]          # drop VTT cue settings
        words = " ".join(lines[timing + 1:]).strip()
        words = re.sub(r"<[^>]+>", "", words)    # VTT voice / styling tags
        if words:
            segments.append({"start_ms": _ms(start), "end_ms": _ms(end), "text": words})
    return validate(segments)


def validate(segments):
    if not isinstance(segments, list):
        raise TranscriptError("Transcript must be a list of segments")
    last = -1
    for seg in segments:
        if not isinstance(seg, dict) or not isinstance(seg.get("text"), str):
            raise TranscriptError("Each segment needs text")
        start, end = seg.get("start_ms"), seg.get("end_ms", seg.get("start_ms"))
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 for v in (start, end)):
            raise TranscriptError("Segment times must be non-negative milliseconds")
        if end < start or start < last:
            raise TranscriptError("Segments must be in time order")
        last = start
    return segments


def load(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        return validate(json.loads(text))
    return parse_cues(text)


def within(segments, start_ms, end_ms):
    """Segments starting inside [start, end), with times relative to start."""
    return [{"at_ms": seg["start_ms"] - start_ms, "label": seg["text"]}
            for seg in segments if start_ms <= seg["start_ms"] < end_ms]
