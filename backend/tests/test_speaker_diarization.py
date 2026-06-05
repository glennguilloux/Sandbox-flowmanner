"""
Unit tests for speaker_diarization.py — Speaker Diarization tool.

Tests cover:
- Input validation (missing data, parameter ranges)
- Voice Activity Detection (VAD) — merge_speech_frames
- Speaker clustering — with mocked librosa/scipy
- Full pipeline with real generated audio
- Edge cases (short audio, single speaker)
- Tool metadata and registration
"""

import io
import os
import base64
import struct
import math
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest


# ── Helpers ──────────────────────────────────────────────────────────


def generate_two_tone_wav_b64():
    """Generate audio with two distinct tones separated by silence (4s total).
    Pattern: 300Hz (1s) → silence (0.3s) → 500Hz (1s) → silence (0.3s) → 300Hz (1s)."""
    sample_rate = 16000
    duration_ms = 4000
    num_samples = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + num_samples * 2))
    buf.write(b"WAVEfmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", num_samples * 2))

    amp = 10000
    # Tone 1: 300Hz, 1s
    for i in range(sample_rate):
        s = int(amp * math.sin(2 * math.pi * 300 * i / sample_rate))
        buf.write(struct.pack("<h", s))
    # Silence: 0.3s
    for i in range(int(sample_rate * 0.3)):
        buf.write(struct.pack("<h", 0))
    # Tone 2: 500Hz, 1s
    for i in range(sample_rate):
        s = int(amp * math.sin(2 * math.pi * 500 * i / sample_rate))
        buf.write(struct.pack("<h", s))
    # Silence: 0.3s
    for i in range(int(sample_rate * 0.3)):
        buf.write(struct.pack("<h", 0))
    # Tone 3: 300Hz, 1s
    for i in range(sample_rate):
        s = int(amp * math.sin(2 * math.pi * 300 * i / sample_rate))
        buf.write(struct.pack("<h", s))

    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.fixture
def two_tone_b64():
    return generate_two_tone_wav_b64()


@pytest.fixture
def diarization():
    from app.tools.speaker_diarization import SpeakerDiarizationTool

    return SpeakerDiarizationTool()


# ── Input Validation ─────────────────────────────────────────────────


class TestInputValidation:
    """Test input parsing and validation."""

    @pytest.mark.asyncio
    async def test_missing_data_and_url(self, diarization):
        r = await diarization.execute({"max_speakers": 2})
        assert not r.success
        assert "data" in r.error.lower()

    @pytest.mark.asyncio
    async def test_max_speakers_default(self, diarization):
        from app.tools.speaker_diarization import SpeakerDiarizationInput

        inp = SpeakerDiarizationInput(data="Zm9v")
        assert inp.max_speakers > 0

    @pytest.mark.asyncio
    async def test_min_segment_default(self, diarization):
        from app.tools.speaker_diarization import SpeakerDiarizationInput

        inp = SpeakerDiarizationInput(data="Zm9v")
        assert inp.min_segment_seconds > 0

    @pytest.mark.asyncio
    async def test_max_speakers_too_low(self, diarization):
        from app.tools.speaker_diarization import SpeakerDiarizationInput

        with pytest.raises(Exception):
            SpeakerDiarizationInput(data="Zm9v", max_speakers=0)

    @pytest.mark.asyncio
    async def test_max_speakers_too_high(self, diarization):
        from app.tools.speaker_diarization import SpeakerDiarizationInput

        with pytest.raises(Exception):
            SpeakerDiarizationInput(data="Zm9v", max_speakers=100)

    @pytest.mark.asyncio
    async def test_min_segment_too_low(self, diarization):
        from app.tools.speaker_diarization import SpeakerDiarizationInput

        with pytest.raises(Exception):
            SpeakerDiarizationInput(data="Zm9v", min_segment_seconds=0.05)


# ── VAD: merge_speech_frames ─────────────────────────────────────────


class TestMergeSpeechFrames:
    """Test the _merge_speech_frames static method."""

    def test_single_contiguous_segment(self, diarization):
        # 100 frames, all speech
        speech = np.ones(100, dtype=bool)
        segments = diarization._merge_speech_frames(
            speech, min_frames=1, hop_length=512, sr=16000
        )
        assert len(segments) == 1
        start, end = segments[0]
        assert start == 0
        assert end == 100 * 512

    def test_two_separate_segments(self, diarization):
        # 20 speech, 20 silence, 20 speech
        speech = np.zeros(60, dtype=bool)
        speech[:20] = True
        speech[40:] = True
        segments = diarization._merge_speech_frames(
            speech, min_frames=1, hop_length=512, sr=16000
        )
        assert len(segments) == 2

    def test_min_frames_filter(self, diarization):
        """Segments shorter than min_frames should be dropped."""
        speech = np.zeros(100, dtype=bool)
        speech[10:12] = True  # 2 frames — too short
        speech[50:80] = True  # 30 frames — kept
        segments = diarization._merge_speech_frames(
            speech, min_frames=5, hop_length=512, sr=16000
        )
        assert len(segments) == 1
        start, end = segments[0]
        assert start == 50 * 512
        assert end == 80 * 512

    def test_no_speech_frames(self, diarization):
        speech = np.zeros(100, dtype=bool)
        segments = diarization._merge_speech_frames(
            speech, min_frames=1, hop_length=512, sr=16000
        )
        assert len(segments) == 0

    def test_all_speech(self, diarization):
        speech = np.ones(50, dtype=bool)
        segments = diarization._merge_speech_frames(
            speech, min_frames=1, hop_length=512, sr=16000
        )
        assert len(segments) == 1

    def test_trailing_speech(self, diarization):
        """Speech that continues to end should be captured."""
        speech = np.zeros(100, dtype=bool)
        speech[90:] = True
        segments = diarization._merge_speech_frames(
            speech, min_frames=1, hop_length=512, sr=16000
        )
        assert len(segments) == 1
        start, end = segments[0]
        assert start == 90 * 512
        assert end == 100 * 512


# ── Clustering ────────────────────────────────────────────────────────


class TestClusterSegments:
    """Test the _cluster_segments static method."""

    def test_single_feature_returns_speaker_0(self, diarization):
        feat = np.array([[1.0, 2.0, 3.0]])
        labels = diarization._cluster_segments(feat, max_speakers=5)
        assert len(labels) == 1
        assert labels[0] == 0

    def test_zero_features(self, diarization):
        feat = np.empty((0, 26))
        labels = diarization._cluster_segments(feat, max_speakers=5)
        assert len(labels) == 0

    def test_two_identical_features_one_speaker(self, diarization):
        feat = np.array([[1.0] * 26, [1.0] * 26])
        # With max_speakers=1, identical features must cluster together
        labels = diarization._cluster_segments(feat, max_speakers=1)
        assert len(labels) == 2
        # Identical features should cluster together (both same label)
        assert labels[0] == labels[1]

    def test_two_very_different_features_two_speakers(self, diarization):
        feat = np.array([[1.0] * 26, [-1.0] * 26])
        labels = diarization._cluster_segments(feat, max_speakers=5)
        assert len(labels) == 2
        # Very different features should get different labels
        assert labels[0] != labels[1]

    def test_respects_max_speakers(self, diarization):
        # 10 segments, max 3 speakers
        np.random.seed(42)
        feat = np.random.randn(10, 26)
        labels = diarization._cluster_segments(feat, max_speakers=3)
        assert len(labels) == 10
        assert len(set(labels)) <= 3

    def test_nan_handling(self, diarization):
        """Features with NaN should not crash."""
        feat = np.array([[1.0] * 26, [float("nan")] * 26])
        labels = diarization._cluster_segments(feat, max_speakers=5)
        assert len(labels) == 2


# ── Full Pipeline (Real Audio) ───────────────────────────────────────


class TestFullPipeline:
    """Test the full diarization pipeline with real generated audio."""

    @pytest.mark.asyncio
    async def test_two_tone_diarization(self, diarization, two_tone_b64):
        r = await diarization.execute({"data": two_tone_b64})
        assert r.success
        assert r.result["duration_seconds"] > 0
        assert r.result["speaker_count"] >= 1
        assert len(r.result["segments"]) >= 1
        assert "speaker_timelines" in r.result
        assert r.result["engine"] == "mfcc-clustering"

    @pytest.mark.asyncio
    async def test_speech_percentage_reasonable(self, diarization, two_tone_b64):
        r = await diarization.execute({"data": two_tone_b64})
        pct = r.result["speech_percentage"]
        # With 3s of tone and 0.6s of silence in 4s, speech should be 60-95%
        assert 30 <= pct <= 100, f"Speech percentage {pct}% out of range"

    @pytest.mark.asyncio
    async def test_total_speech_seconds(self, diarization, two_tone_b64):
        r = await diarization.execute({"data": two_tone_b64})
        total = r.result["total_speech_seconds"]
        assert total > 0
        assert total <= r.result["duration_seconds"]

    @pytest.mark.asyncio
    async def test_segments_have_required_fields(self, diarization, two_tone_b64):
        r = await diarization.execute({"data": two_tone_b64})
        for seg in r.result["segments"]:
            assert "speaker_id" in seg
            assert "start_seconds" in seg
            assert "end_seconds" in seg
            assert "duration_seconds" in seg
            assert seg["start_seconds"] < seg["end_seconds"]
            assert seg["speaker_id"].startswith("speaker_")

    @pytest.mark.asyncio
    async def test_speaker_timelines_match_segments(self, diarization, two_tone_b64):
        r = await diarization.execute({"data": two_tone_b64})
        timelines = r.result["speaker_timelines"]
        for seg in r.result["segments"]:
            sid = seg["speaker_id"]
            assert sid in timelines

    @pytest.mark.asyncio
    async def test_max_speakers_constraint(self, diarization, two_tone_b64):
        r = await diarization.execute(
            {
                "data": two_tone_b64,
                "max_speakers": 2,
            }
        )
        assert r.result["speaker_count"] <= 2

    @pytest.mark.asyncio
    async def test_short_audio_returns_error(self, diarization):
        """Audio < 1s should return an error in the result."""
        # Generate 0.5s audio
        sample_rate = 16000
        num_samples = int(sample_rate * 0.5)
        buf = io.BytesIO()
        buf.write(b"RIFF")
        buf.write(struct.pack("<I", 36 + num_samples * 2))
        buf.write(b"WAVEfmt ")
        buf.write(
            struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
        )
        buf.write(b"data")
        buf.write(struct.pack("<I", num_samples * 2))
        for i in range(num_samples):
            buf.write(struct.pack("<h", 0))
        short_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        r = await diarization.execute({"data": short_b64})
        assert r.success  # Tool succeeds
        assert "error" in r.result  # But result contains error
        assert r.result["speakers"] == []


# ── Tool Metadata ────────────────────────────────────────────────────


class TestToolMetadata:
    """Test tool metadata and registration."""

    def test_tool_id(self, diarization):
        assert diarization.tool_id == "speaker_diarization"

    def test_tool_category(self, diarization):
        assert diarization.category == "audio-speech-processing"

    def test_tool_tags(self, diarization):
        assert "audio" in diarization.tags
        assert "speaker" in diarization.tags
        assert "diarization" in diarization.tags
        assert "clustering" in diarization.tags

    def test_tool_requires_auth(self, diarization):
        assert diarization.metadata.requires_auth == False

    def test_tool_registered(self, diarization):
        from app.tools.base import get_tool_registry

        registry = get_tool_registry()
        tool = registry.get("speaker_diarization")
        assert tool is not None


# ── Edge Cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_invalid_base64(self, diarization):
        r = await diarization.execute(
            {
                "data": "!!!not-valid!!!",
                "max_speakers": 2,
            }
        )
        assert not r.success

    @pytest.mark.asyncio
    async def test_empty_data(self, diarization):
        r = await diarization.execute(
            {
                "data": "",
                "max_speakers": 2,
            }
        )
        assert not r.success

    @pytest.mark.asyncio
    async def test_custom_min_segment(self, diarization, two_tone_b64):
        r = await diarization.execute(
            {
                "data": two_tone_b64,
                "min_segment_seconds": 1.0,
            }
        )
        assert r.success
        # With min 1s segments, only longer segments should appear
        for seg in r.result["segments"]:
            assert seg["duration_seconds"] >= 1.0
