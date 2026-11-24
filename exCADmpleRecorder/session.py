"""Build the timestamped recording JSON independently of the Fusion API."""

import json
from pathlib import Path

FORMAT = "excadmple-voice-session"
VERSION = 1


def build_session(design, duration, observations, audio=None, cues=(), interrupted=False):
    """Build reviewable clips around the modeling operations observed in Fusion.

    The first operation gets the lead-in. Later clips begin at the previous
    commit, and the last clip includes post-operation narration. A cue crossing
    a boundary goes to the clip with the greatest overlap, or the earlier clip
    at a tie. Fusion doesn't know what a speaker meant.
    """
    if audio and audio["offset_ms"] == 0:
        duration = max(duration, audio["duration_ms"])
    operations = []
    start = 0
    for index, observation in enumerate(observations):
        end = duration if index == len(observations) - 1 else observation["at_ms"]
        operations.append({
            **observation, "id": index + 1, "start_ms": start, "end_ms": end, "transcript": [],
        })
        start = end

    data = {
        "format": FORMAT, "version": VERSION, "design": design, "duration_ms": duration,
        "audio": audio, "operations": operations, "transcript": list(cues),
        "unassigned_transcript": [], "interrupted": interrupted,
    }
    return align_transcript(data)


def align_transcript(data):
    audio = data["audio"]
    for operation in data["operations"]:
        operation["transcript"] = []
        operation["audio_clip"] = None
        if audio:
            start = max(0, operation["start_ms"] - audio["offset_ms"])
            end = min(audio["duration_ms"], operation["end_ms"] - audio["offset_ms"])
            if end > start:
                operation["audio_clip"] = {"start_ms": start, "end_ms": end}
    data["unassigned_transcript"] = []
    for cue in data["transcript"]:
        if audio:
            start = cue["start_ms"] + audio["offset_ms"]
            end = cue["end_ms"] + audio["offset_ms"]
            best, best_overlap = None, 0
            for operation in data["operations"]:
                overlap = min(end, operation["end_ms"]) - max(start, operation["start_ms"])
                if overlap > best_overlap:
                    best, best_overlap = operation, overlap
            if best is not None:
                best["transcript"].append(cue)
                continue
        data["unassigned_transcript"].append(cue)
    return data


def save_session(folder, data):
    folder = Path(folder)
    target = folder / "session.json"
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)
