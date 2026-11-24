import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from exCADmpleRecorder.session import align_transcript, build_session, save_session
from tools import transcribe


class VoiceSessionTests(TestCase):
    def test_matches_cues_by_overlap_and_keeps_unmatched_speech(self):
        observations = [
            {"at_ms": 3000, "features": [{"name": "Sketch1", "index": 0}]},
            {"at_ms": 7000, "features": [{"name": "Extrude1", "index": 1}]},
        ]
        audio = {"file": "voice.wav", "offset_ms": -2000, "duration_ms": 12000}
        cues = [
            {"start_ms": 100, "end_ms": 500, "text": "Before modeling"},
            {"start_ms": 2800, "end_ms": 4700, "text": "画一个草图"},
            {"start_ms": 4600, "end_ms": 5900, "text": "拉伸"},
            {"start_ms": 9200, "end_ms": 9800, "text": "After the extrusion"},
        ]
        data = build_session("Part", 8000, observations, audio, cues)
        sketch, extrude = data["operations"]
        self.assertEqual(sketch["audio_clip"], {"start_ms": 2000, "end_ms": 5000})
        self.assertEqual(extrude["audio_clip"], {"start_ms": 5000, "end_ms": 10000})
        self.assertEqual(sketch["transcript"], [cues[1]])
        self.assertEqual(extrude["transcript"], cues[2:])
        self.assertEqual(data["unassigned_transcript"], [cues[0]])
        self.assertEqual(align_transcript(data), data)
        with tempfile.TemporaryDirectory() as folder:
            save_session(folder, data)
            self.assertEqual(json.loads((Path(folder) / "session.json").read_text()), data)

    def test_no_new_features_preserves_audio_and_transcript(self):
        cue = {"start_ms": 100, "end_ms": 200, "text": "Idea"}
        data = build_session("Part", 1500, [],
                             {"file": "voice.wav", "offset_ms": 0, "duration_ms": 1600}, [cue])
        self.assertEqual(data["operations"], [])
        self.assertEqual(data["unassigned_transcript"], [cue])
        self.assertEqual(data["duration_ms"], 1600)

    def test_late_mic_yields_no_clip_for_operation_before_audio(self):
        data = build_session("Part", 2000, [{"at_ms": 500}, {"at_ms": 1400}],
                             {"file": "voice.wav", "offset_ms": 700, "duration_ms": 1000})
        self.assertIsNone(data["operations"][0]["audio_clip"])
        self.assertEqual(data["operations"][1]["audio_clip"], {"start_ms": 0, "end_ms": 1000})

    def test_json_transcription_preserves_millisecond_cues(self):
        def whisper_model(size, **options):
            self.assertEqual((size, options), ("small", {"device": "cpu", "compute_type": "int8"}))
            return SimpleNamespace(transcribe=lambda *args, **kwargs: (
                iter([SimpleNamespace(start=.125, end=1.375, text=" 草图 ")]), None))

        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "transcript.json"
            with patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=whisper_model)}):
                self.assertEqual(transcribe.main(["voice.wav", "-o", str(target), "--format", "json",
                                                  "--device", "cpu", "--language", "zh"]), 0)
            self.assertEqual(json.loads(target.read_text()),
                             [{"start_ms": 125, "end_ms": 1375, "text": "草图"}])
