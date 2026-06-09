"""
Audio/Speech Processing Tools — Audio Sentiment Analyzer (DIFFERENTIATOR).

audio_sentiment_analyzer → Detect emotion, tone, and sentiment from voice
    recordings using audio feature analysis and text sentiment.
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import tempfile
from typing import Any

import numpy as np
from pydantic import Field

from app.tools._file_utils import resolve_input
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

SENTIMENT_TIMEOUT = int(os.getenv("AUDIO_SENTIMENT_TIMEOUT", "120"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
SENTIMENT_LLM_MODEL = os.getenv("SENTIMENT_LLM_MODEL", "gpt-4o-mini")

_AFFECTIVE_DIMENSIONS = ["valence", "arousal", "dominance"]
_EMOTION_LABELS = [
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


# ── Input ─────────────────────────────────────────────────────────────


class AudioSentimentAnalyzerInput(ToolInput):
    data: str | None = Field(
        None,
        description="Base64-encoded audio data (data URI prefix optional)",
    )
    url: str | None = Field(
        None,
        description="URL to fetch the audio file from",
    )
    include_transcript: bool = Field(
        False,
        description="Also transcribe the audio and include text sentiment",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class AudioSentimentAnalyzerTool(BaseTool):
    """Detect emotion and tone from voice inflections using audio analysis.

    Extracts acoustic features (pitch, energy, tempo, spectral properties)
    and maps them to emotion dimensions. Optionally transcribes and analyzes
    text sentiment via OpenAI API. ⭐ DIFFERENTIATOR
    """

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="audio_sentiment_analyzer",
            name="Audio Sentiment Analyzer",
            description=(
                "Detect emotion and tone directly from voice inflections "
                "using acoustic feature analysis. Extracts pitch, energy, "
                "tempo, and spectral properties to map to emotion dimensions. "
                "⭐ DIFFERENTIATOR"
            ),
            category="audio-speech-processing",
            input_schema=AudioSentimentAnalyzerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["audio", "sentiment", "emotion", "voice", "differentiator"],
            requires_auth=False,
            timeout_seconds=SENTIMENT_TIMEOUT + 30,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = AudioSentimentAnalyzerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if not validated.data and not validated.url:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Either 'data' (base64) or 'url' must be provided",
            )

        try:
            result = await self._analyze(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("audio_sentiment_analyzer failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _analyze ─────────────────────────────────────────────────

    async def _analyze(self, validated: AudioSentimentAnalyzerInput) -> dict[str, Any]:
        """Extract audio features and compute sentiment scores."""
        audio_bytes = await resolve_input(
            validated.data, validated.url, label="audio", fetch_timeout=60
        )

        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                # Convert to WAV for librosa
                from pydub import AudioSegment

                audio_seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
                audio_seg.export(tmp.name, format="wav")
                tmp_path = tmp.name

            features = self._extract_acoustic_features(tmp_path)
            emotion_scores = self._map_features_to_emotion(features)

            result: dict[str, Any] = {
                "acoustic_features": features,
                "emotion_scores": emotion_scores,
                "primary_emotion": max(emotion_scores, key=emotion_scores.get),
                "engine": "acoustic-feature-analysis",
            }

            # Optionally transcribe and analyze text sentiment
            if validated.include_transcript and OPENAI_API_KEY:
                try:
                    text_analysis = await self._analyze_text_sentiment(audio_bytes)
                    result["text_sentiment"] = text_analysis
                except Exception as e:
                    logger.warning("Text sentiment analysis failed: %s", e)
                    result["text_sentiment"] = {"error": str(e)}

            return result
        finally:
            if tmp_path and os.path.exists(tmp_path):
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)

    # ── _extract_acoustic_features ───────────────────────────────

    def _extract_acoustic_features(self, wav_path: str) -> dict[str, Any]:
        """Extract pitch, energy, tempo, and spectral features."""
        import librosa

        y, sr = librosa.load(wav_path, sr=None, mono=True)
        duration = len(y) / sr if sr > 0 else 0

        if duration < 0.1 or len(y) < sr * 0.1:
            return {
                "error": "Audio too short for analysis",
                "duration_seconds": duration,
            }

        # Energy (RMS)
        rms = librosa.feature.rms(y=y)[0]
        energy_mean = float(np.mean(rms))
        energy_std = float(np.std(rms))
        energy_range = float(np.max(rms) - np.min(rms)) if len(rms) > 0 else 0.0

        # Pitch (fundamental frequency)
        f0, voiced_flag, _ = librosa.pyin(y, fmin=50, fmax=500, sr=sr, fill_na=0)
        f0_voiced = f0[voiced_flag] if np.any(voiced_flag) else np.array([0])
        pitch_mean = float(np.mean(f0_voiced)) if len(f0_voiced) > 0 else 0.0
        pitch_std = float(np.std(f0_voiced)) if len(f0_voiced) > 0 else 0.0

        # Tempo
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        if hasattr(tempo, "item"):
            tempo_val = float(tempo.item())
        elif isinstance(tempo, np.ndarray) and tempo.size > 0:
            tempo_val = float(tempo.flat[0])
        else:
            tempo_val = float(tempo)

        # Spectral features
        spectral_centroid = float(
            np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
        )
        spectral_bandwidth = float(
            np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr))
        )
        spectral_rolloff = float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr)))
        zero_crossing_rate = float(np.mean(librosa.feature.zero_crossing_rate(y)))

        # MFCC mean values
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc_means = [float(np.mean(mfcc[i])) for i in range(13)]

        # Speech rate (approximated by zero-crossing variability)
        zcr_var = float(np.std(librosa.feature.zero_crossing_rate(y)[0]))

        return {
            "duration_seconds": round(duration, 2),
            "sample_rate": sr,
            "energy": {
                "mean": round(energy_mean, 6),
                "std": round(energy_std, 6),
                "range": round(energy_range, 6),
                "level": self._categorize_energy(energy_mean),
            },
            "pitch": {
                "mean_hz": round(pitch_mean, 1),
                "std_hz": round(pitch_std, 1),
                "level": self._categorize_pitch(pitch_mean),
            },
            "tempo_bpm": round(tempo_val, 1),
            "speech_rate_zcr_var": round(zcr_var, 6),
            "spectral": {
                "centroid": round(spectral_centroid, 1),
                "bandwidth": round(spectral_bandwidth, 1),
                "rolloff": round(spectral_rolloff, 1),
                "zero_crossing_rate": round(zero_crossing_rate, 6),
            },
            "mfcc_means": {f"mfcc_{i}": round(v, 3) for i, v in enumerate(mfcc_means)},
        }

    # ── _map_features_to_emotion ─────────────────────────────────

    def _map_features_to_emotion(self, features: dict[str, Any]) -> dict[str, float]:
        """Map acoustic features to emotion scores using heuristics."""
        if "error" in features:
            return dict.fromkeys(_EMOTION_LABELS, 0.0)

        energy = features.get("energy", {})
        pitch = features.get("pitch", {})
        spectral = features.get("spectral", {})

        energy_mean = energy.get("mean", 0)
        pitch_mean = pitch.get("mean_hz", 0)
        pitch_std = pitch.get("std_hz", 0)
        tempo = features.get("tempo_bpm", 120)
        centroid = spectral.get("centroid", 2000)

        scores: dict[str, float] = {}

        # High energy, high pitch variation → happy / excited
        energy_factor = min(energy_mean * 10, 1.0) if energy_mean > 0 else 0
        pitch_var_factor = min(pitch_std / 80, 1.0) if pitch_std > 0 else 0
        fast_tempo = min((tempo - 80) / 80, 1.0) if tempo > 80 else 0
        slow_tempo = min((120 - tempo) / 120, 1.0) if tempo < 120 else 0

        scores["happy"] = round(
            min(energy_factor * 0.5 + pitch_var_factor * 0.3 + fast_tempo * 0.2, 1.0), 3
        )
        scores["excited"] = round(
            min(energy_factor * 0.6 + pitch_var_factor * 0.3 + fast_tempo * 0.1, 1.0), 3
        )
        scores["calm"] = round(
            min(
                (1 - energy_factor) * 0.4
                + slow_tempo * 0.4
                + (1 - pitch_var_factor) * 0.2,
                1.0,
            ),
            3,
        )
        scores["sad"] = round(
            min(
                (1 - energy_factor) * 0.3
                + slow_tempo * 0.3
                + (1 - pitch_var_factor) * 0.4,
                1.0,
            ),
            3,
        )
        scores["angry"] = round(
            min(
                energy_factor * 0.4
                + pitch_var_factor * 0.2
                + (1 - slow_tempo) * 0.1
                + 0.3,
                1.0,
            ),
            3,
        )
        scores["fearful"] = round(
            min(pitch_var_factor * 0.4 + energy_factor * 0.3, 1.0), 3
        )
        scores["anxious"] = round(
            min(
                pitch_var_factor * 0.5 + (1 - slow_tempo) * 0.2 + energy_factor * 0.2,
                1.0,
            ),
            3,
        )
        scores["surprised"] = round(
            min(pitch_var_factor * 0.3 + energy_factor * 0.3, 1.0), 3
        )
        scores["disgusted"] = round(
            min((1 - pitch_var_factor) * 0.2 + energy_factor * 0.2, 1.0), 3
        )
        scores["neutral"] = round(
            1.0 - sum(v for k, v in scores.items() if k != "neutral") / 9, 3
        )
        scores["neutral"] = max(0.0, scores["neutral"])

        # Normalize
        total = sum(scores.values())
        if total > 0:
            scores = {k: round(v / total, 3) for k, v in scores.items()}

        return scores

    # ── _analyze_text_sentiment ──────────────────────────────────

    async def _analyze_text_sentiment(self, audio_bytes: bytes) -> dict[str, Any]:
        """Transcribe audio and analyze text sentiment via OpenAI."""
        import httpx

        # Use a single httpx client for both API calls
        async with httpx.AsyncClient(timeout=SENTIMENT_TIMEOUT) as client:
            # First transcribe
            files = {"file": ("audio.mp3", io.BytesIO(audio_bytes), "audio/mpeg")}
            url = f"{OPENAI_BASE_URL.rstrip('/')}/v1/audio/transcriptions"

            resp = await client.post(
                url,
                files=files,
                data={"model": "whisper-1", "response_format": "json"},
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            )
            resp.raise_for_status()
            transcript = resp.json().get("text", "")

            if not transcript.strip():
                return {"transcript": "", "sentiment": "neutral", "confidence": 0.0}

            # Then analyze sentiment
            sentiment_url = f"{OPENAI_BASE_URL.rstrip('/')}/v1/chat/completions"
            payload = {
                "model": SENTIMENT_LLM_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Analyze the sentiment of this transcript. "
                            "Respond with a JSON object: "
                            '{"sentiment": "positive|negative|neutral", '
                            '"confidence": 0.0-1.0, "emotion": "emotion_label", '
                            '"explanation": "brief reason"}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": transcript,
                    },
                ],
                "temperature": 0.0,
                "max_tokens": 200,
            }

            resp = await client.post(
                sentiment_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]

            # Parse JSON from response
            import json

            try:
                sentiment_data = json.loads(content)
            except json.JSONDecodeError:
                sentiment_data = {
                    "sentiment": "neutral",
                    "confidence": 0.5,
                    "explanation": content,
                }

            sentiment_data["transcript"] = transcript
            return sentiment_data

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _categorize_energy(mean: float) -> str:
        if mean < 0.02:
            return "low"
        elif mean < 0.08:
            return "medium"
        return "high"

    @staticmethod
    def _categorize_pitch(mean_hz: float) -> str:
        if mean_hz < 120:
            return "low"
        elif mean_hz < 200:
            return "medium"
        return "high"


# ── Register ──────────────────────────────────────────────────────────

register_tool(AudioSentimentAnalyzerTool())
