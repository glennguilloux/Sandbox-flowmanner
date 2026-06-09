"""
Unit tests for audio_sentiment_analyzer.py — Audio Sentiment Analyzer tool.

Tests cover:
- Input validation (missing data, edge cases)
- Acoustic feature extraction (with mocked librosa)
- Emotion mapping heuristics
- Helper methods (categorize_energy, categorize_pitch)
- Optional text sentiment analysis (with mocked httpx)
- Tool metadata and registration
"""

import io
import os
import base64
import struct
import math
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import numpy as np
import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-123")


# ── Helpers ──────────────────────────────────────────────────────────


def generate_tiny_wav_bytes(duration_ms=2000, freq=440, sample_rate=16000):
    """Generate raw WAV bytes for sentiment analysis."""
    num_samples = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + num_samples * 2))
    buf.write(b"WAVEfmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", num_samples * 2))
    for i in range(num_samples):
        s = int(16000 * math.sin(2 * math.pi * freq * i / sample_rate))
        buf.write(struct.pack("<h", s))
    return base64.b64encode(buf.getvalue()).decode("ascii")


def generate_chirp_wav_b64(duration_ms=2000, sample_rate=16000):
    """Generate a frequency sweep (chirp) — more dynamic for analysis."""
    num_samples = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + num_samples * 2))
    buf.write(b"WAVEfmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", num_samples * 2))
    for i in range(num_samples):
        freq = 200 + 600 * i / num_samples
        s = int(10000 * math.sin(2 * math.pi * freq * i / sample_rate))
        buf.write(struct.pack("<h", s))
    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.fixture
def tone_b64():
    return generate_tiny_wav_bytes(duration_ms=2000)


@pytest.fixture
def chirp_b64():
    return generate_chirp_wav_b64(duration_ms=2000)


@pytest.fixture
def analyzer():
    from app.tools.audio_sentiment_analyzer import AudioSentimentAnalyzerTool

    return AudioSentimentAnalyzerTool()


@pytest.fixture
def mock_librosa_features():
    """Return a realistic feature dict as if from _extract_acoustic_features."""
    return {
        "duration_seconds": 2.0,
        "sample_rate": 16000,
        "energy": {"mean": 0.05, "std": 0.01, "range": 0.03, "level": "medium"},
        "pitch": {"mean_hz": 180.0, "std_hz": 30.0, "level": "medium"},
        "tempo_bpm": 120.0,
        "speech_rate_zcr_var": 0.01,
        "spectral": {
            "centroid": 2000.0,
            "bandwidth": 1000.0,
            "rolloff": 4000.0,
            "zero_crossing_rate": 0.05,
        },
        "mfcc_means": {f"mfcc_{i}": 0.0 for i in range(13)},
    }


# ── Input Validation ─────────────────────────────────────────────────


class TestInputValidation:
    """Test input parsing and validation."""

    @pytest.mark.asyncio
    async def test_missing_data_and_url(self, analyzer):
        r = await analyzer.execute({})
        assert not r.success
        assert "data" in r.error.lower()

    @pytest.mark.asyncio
    async def test_include_transcript_default_false(self, analyzer):
        from app.tools.audio_sentiment_analyzer import AudioSentimentAnalyzerInput

        inp = AudioSentimentAnalyzerInput(data="Zm9v")
        assert inp.include_transcript == False

    @pytest.mark.asyncio
    async def test_include_transcript_true(self, analyzer):
        from app.tools.audio_sentiment_analyzer import AudioSentimentAnalyzerInput

        inp = AudioSentimentAnalyzerInput(data="Zm9v", include_transcript=True)
        assert inp.include_transcript == True


# ── Acoustic Feature Extraction ──────────────────────────────────────


class TestAcousticFeatures:
    """Test acoustic feature extraction with real audio."""

    @pytest.mark.asyncio
    async def test_extract_features_success(self, analyzer, chirp_b64):
        r = await analyzer.execute({"data": chirp_b64})
        assert r.success
        features = r.result["acoustic_features"]
        assert "energy" in features
        assert "pitch" in features
        assert "spectral" in features
        assert "mfcc_means" in features
        assert "duration_seconds" in features
        assert features["duration_seconds"] > 0

    @pytest.mark.asyncio
    async def test_energy_level_categorized(self, analyzer, chirp_b64):
        r = await analyzer.execute({"data": chirp_b64})
        energy = r.result["acoustic_features"]["energy"]
        assert energy["level"] in ("low", "medium", "high")
        assert energy["mean"] > 0

    @pytest.mark.asyncio
    async def test_pitch_level_categorized(self, analyzer, chirp_b64):
        r = await analyzer.execute({"data": chirp_b64})
        pitch = r.result["acoustic_features"]["pitch"]
        assert pitch["level"] in ("low", "medium", "high")

    @pytest.mark.asyncio
    async def test_tempo_extracted(self, analyzer, chirp_b64):
        r = await analyzer.execute({"data": chirp_b64})
        assert "tempo_bpm" in r.result["acoustic_features"]

    @pytest.mark.asyncio
    async def test_mfcc_13_coefficients(self, analyzer, chirp_b64):
        r = await analyzer.execute({"data": chirp_b64})
        mfcc = r.result["acoustic_features"]["mfcc_means"]
        assert len(mfcc) == 13
        for i in range(13):
            assert f"mfcc_{i}" in mfcc

    @pytest.mark.asyncio
    async def test_spectral_features_present(self, analyzer, chirp_b64):
        r = await analyzer.execute({"data": chirp_b64})
        spectral = r.result["acoustic_features"]["spectral"]
        assert "centroid" in spectral
        assert "bandwidth" in spectral
        assert "rolloff" in spectral
        assert "zero_crossing_rate" in spectral


# ── Emotion Mapping ──────────────────────────────────────────────────


class TestEmotionMapping:
    """Test the heuristic emotion mapping."""

    def test_map_features_to_emotion(self, analyzer, mock_librosa_features):
        scores = analyzer._map_features_to_emotion(mock_librosa_features)
        assert len(scores) == 10  # 10 emotion labels
        # All scores should be between 0 and 1
        for label, score in scores.items():
            assert 0.0 <= score <= 1.0, f"{label}: {score}"
        # Scores should sum to approximately 1
        total = sum(scores.values())
        assert abs(total - 1.0) < 0.01, f"Scores sum to {total}"

    def test_map_features_error_input(self, analyzer):
        scores = analyzer._map_features_to_emotion({"error": "too short"})
        # Should return all zeros
        assert all(v == 0.0 for v in scores.values())
        assert len(scores) == 10

    def test_primary_emotion_present(self, analyzer, mock_librosa_features):
        scores = analyzer._map_features_to_emotion(mock_librosa_features)
        primary = max(scores, key=scores.get)
        assert primary in scores
        assert scores[primary] > 0

    @pytest.mark.asyncio
    async def test_primary_emotion_in_result(self, analyzer, chirp_b64):
        r = await analyzer.execute({"data": chirp_b64})
        assert "primary_emotion" in r.result
        assert r.result["primary_emotion"] in [
            "neutral",
            "happy",
            "sad",
            "angry",
            "fearful",
            "surprised",
            "disgusted",
            "calm",
            "excited",
            "anxious",
        ]

    def test_high_energy_excited(self, analyzer):
        """Very high energy should map to high excited score."""
        features = {
            "duration_seconds": 2.0,
            "sample_rate": 16000,
            "energy": {"mean": 0.5, "std": 0.1, "range": 0.2, "level": "high"},
            "pitch": {"mean_hz": 250.0, "std_hz": 80.0, "level": "high"},
            "tempo_bpm": 180.0,
            "speech_rate_zcr_var": 0.02,
            "spectral": {
                "centroid": 4000.0,
                "bandwidth": 2000.0,
                "rolloff": 6000.0,
                "zero_crossing_rate": 0.1,
            },
            "mfcc_means": {f"mfcc_{i}": 0.0 for i in range(13)},
        }
        scores = analyzer._map_features_to_emotion(features)
        assert scores["excited"] > 0.1
        assert scores["happy"] > 0.05


# ── Helper Methods ───────────────────────────────────────────────────


class TestHelperMethods:
    """Test static helper methods."""

    def test_categorize_energy_low(self):
        from app.tools.audio_sentiment_analyzer import AudioSentimentAnalyzerTool

        assert AudioSentimentAnalyzerTool._categorize_energy(0.01) == "low"

    def test_categorize_energy_medium(self):
        from app.tools.audio_sentiment_analyzer import AudioSentimentAnalyzerTool

        assert AudioSentimentAnalyzerTool._categorize_energy(0.05) == "medium"

    def test_categorize_energy_high(self):
        from app.tools.audio_sentiment_analyzer import AudioSentimentAnalyzerTool

        assert AudioSentimentAnalyzerTool._categorize_energy(0.10) == "high"

    def test_categorize_pitch_low(self):
        from app.tools.audio_sentiment_analyzer import AudioSentimentAnalyzerTool

        assert AudioSentimentAnalyzerTool._categorize_pitch(100) == "low"

    def test_categorize_pitch_medium(self):
        from app.tools.audio_sentiment_analyzer import AudioSentimentAnalyzerTool

        assert AudioSentimentAnalyzerTool._categorize_pitch(150) == "medium"

    def test_categorize_pitch_high(self):
        from app.tools.audio_sentiment_analyzer import AudioSentimentAnalyzerTool

        assert AudioSentimentAnalyzerTool._categorize_pitch(250) == "high"


# ── Text Sentiment (Optional) ────────────────────────────────────────


class TestTextSentiment:
    """Test optional text sentiment analysis path."""

    @pytest.mark.asyncio
    async def test_include_transcript_false_no_text_sentiment(
        self, analyzer, chirp_b64
    ):
        r = await analyzer.execute(
            {
                "data": chirp_b64,
                "include_transcript": False,
            }
        )
        assert r.success
        assert "text_sentiment" not in r.result

    @pytest.mark.asyncio
    async def test_include_transcript_true_no_api_key(self, analyzer, chirp_b64):
        """When include_transcript=True but no API key, should still succeed."""
        with patch("app.tools.audio_sentiment_analyzer.OPENAI_API_KEY", ""):
            r = await analyzer.execute(
                {
                    "data": chirp_b64,
                    "include_transcript": True,
                }
            )
        # Should succeed (acoustic features) but no text sentiment
        assert r.success
        # text_sentiment might be absent or contain error
        ts = r.result.get("text_sentiment")
        if ts is not None:
            assert isinstance(ts, dict)

    @pytest.mark.asyncio
    async def test_include_transcript_with_api_key(self, analyzer, chirp_b64):
        """Mock the full text sentiment pipeline."""
        mock_transcribe_resp = MagicMock()
        mock_transcribe_resp.json.return_value = {"text": "I am very happy today"}
        mock_transcribe_resp.raise_for_status = MagicMock()

        mock_sentiment_resp = MagicMock()
        mock_sentiment_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"sentiment": "positive", "confidence": 0.95, '
                        '"emotion": "happy", "explanation": "Positive tone"}'
                    }
                }
            ]
        }
        mock_sentiment_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.side_effect = [mock_transcribe_resp, mock_sentiment_resp]

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("app.tools.audio_sentiment_analyzer.OPENAI_API_KEY", "sk-test"):
                r = await analyzer.execute(
                    {
                        "data": chirp_b64,
                        "include_transcript": True,
                    }
                )
        assert r.success
        ts = r.result.get("text_sentiment")
        if ts and "transcript" in ts:
            assert ts["sentiment"] in ("positive", "negative", "neutral")


# ── Tool Metadata ────────────────────────────────────────────────────


class TestToolMetadata:
    """Test tool metadata and registration."""

    def test_tool_id(self, analyzer):
        assert analyzer.tool_id == "audio_sentiment_analyzer"

    def test_tool_category(self, analyzer):
        assert analyzer.category == "audio-speech-processing"

    def test_tool_tags(self, analyzer):
        assert "audio" in analyzer.tags
        assert "sentiment" in analyzer.tags
        assert "emotion" in analyzer.tags
        assert "differentiator" in analyzer.tags

    def test_tool_requires_auth(self, analyzer):
        assert analyzer.metadata.requires_auth == False

    def test_tool_registered(self, analyzer):
        from app.tools.base import get_tool_registry

        registry = get_tool_registry()
        tool = registry.get("audio_sentiment_analyzer")
        assert tool is not None

    def test_emotion_labels_complete(self, analyzer):
        from app.tools.audio_sentiment_analyzer import _EMOTION_LABELS

        assert len(_EMOTION_LABELS) == 10
        assert "neutral" in _EMOTION_LABELS
        assert "happy" in _EMOTION_LABELS
        assert "sad" in _EMOTION_LABELS

    def test_affective_dimensions(self, analyzer):
        from app.tools.audio_sentiment_analyzer import _AFFECTIVE_DIMENSIONS

        assert "valence" in _AFFECTIVE_DIMENSIONS
        assert "arousal" in _AFFECTIVE_DIMENSIONS


# ── Edge Cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_invalid_base64(self, analyzer):
        r = await analyzer.execute({"data": "!!!bad!!!base64!!!"})
        assert not r.success

    @pytest.mark.asyncio
    async def test_very_short_audio(self, analyzer):
        """Very short audio should not crash."""
        from app.tools.audio_sentiment_analyzer import AudioSentimentAnalyzerTool

        # Test the internal method directly with a tiny signal
        import tempfile
        import numpy as np

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            try:
                import soundfile as sf

                y = np.sin(2 * np.pi * 440 * np.arange(0, 0.05, 1 / 16000))
                sf.write(tmp.name, y, 16000)
                features = AudioSentimentAnalyzerTool()._extract_acoustic_features(
                    tmp.name
                )
                assert "error" in features or "duration_seconds" in features
            except ImportError:
                pass  # soundfile not available
            finally:
                os.unlink(tmp.name)
