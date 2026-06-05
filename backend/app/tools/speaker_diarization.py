"""
Audio/Speech Processing Tools — Speaker Diarization.

speaker_diarization → Identify and separate multiple speakers in a single
    audio track using voice activity detection and speaker clustering.
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

DIARIZATION_TIMEOUT = int(os.getenv("DIARIZATION_TIMEOUT", "180"))
MIN_SEGMENT_SECONDS = float(os.getenv("DIARIZATION_MIN_SEGMENT", "0.5"))
MAX_SPEAKERS = int(os.getenv("DIARIZATION_MAX_SPEAKERS", "10"))


# ── Input ─────────────────────────────────────────────────────────────


class SpeakerDiarizationInput(ToolInput):
    data: str | None = Field(
        None,
        description="Base64-encoded audio data (data URI prefix optional)",
    )
    url: str | None = Field(
        None,
        description="URL to fetch the audio file from",
    )
    max_speakers: int = Field(
        MAX_SPEAKERS,
        ge=1,
        le=50,
        description="Maximum number of speakers to detect",
    )
    min_segment_seconds: float = Field(
        MIN_SEGMENT_SECONDS,
        ge=0.1,
        le=10.0,
        description="Minimum segment duration in seconds",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class SpeakerDiarizationTool(BaseTool):
    """Identify and separate multiple speakers using acoustic analysis.

    Uses voice activity detection to find speech segments, then clusters
    them by speaker using MFCC feature similarity. Provides speaker-labeled
    timeline segments.
    """

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="speaker_diarization",
            name="Speaker Diarization",
            description=(
                "Identify and separate multiple speakers in a single audio "
                "track. Uses voice activity detection and acoustic feature "
                "clustering to produce speaker-labeled timeline segments."
            ),
            category="audio-speech-processing",
            input_schema=SpeakerDiarizationInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["audio", "speaker", "diarization", "voice", "clustering"],
            requires_auth=False,
            timeout_seconds=DIARIZATION_TIMEOUT + 30,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = SpeakerDiarizationInput(**input_data)
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
            result = await self._diarize(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("speaker_diarization failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _diarize ─────────────────────────────────────────────────

    async def _diarize(
        self, validated: SpeakerDiarizationInput
    ) -> dict[str, Any]:
        """Load audio and run speaker diarization pipeline."""
        audio_bytes = await resolve_input(
            validated.data, validated.url, label="audio", fetch_timeout=60
        )

        tmp_path: str | None = None
        try:
            from pydub import AudioSegment
            audio_seg = AudioSegment.from_file(io.BytesIO(audio_bytes))

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                audio_seg.export(tmp.name, format="wav")
                tmp_path = tmp.name

            duration_sec = len(audio_seg) / 1000.0

            if duration_sec < 1.0:
                return {
                    "error": "Audio too short for diarization (< 1 second)",
                    "duration_seconds": round(duration_sec, 2),
                    "speakers": [],
                    "segments": [],
                }

            # Run the diarization pipeline
            segments = self._detect_and_cluster_speakers(
                tmp_path, validated.max_speakers, validated.min_segment_seconds
            )

            speaker_ids = sorted({s["speaker_id"] for s in segments})
            speaker_timelines: dict[str, list[dict]] = {
                sid: [] for sid in speaker_ids
            }
            for seg in segments:
                speaker_timelines[seg["speaker_id"]].append({
                    "start_seconds": seg["start_seconds"],
                    "end_seconds": seg["end_seconds"],
                })

            total_speech = sum(
                s["end_seconds"] - s["start_seconds"] for s in segments
            )

            return {
                "duration_seconds": round(duration_sec, 2),
                "speaker_count": len(speaker_ids),
                "speaker_ids": speaker_ids,
                "total_speech_seconds": round(total_speech, 2),
                "speech_percentage": round(
                    total_speech / duration_sec * 100, 1
                ) if duration_sec > 0 else 0.0,
                "segments": segments,
                "speaker_timelines": speaker_timelines,
                "engine": "mfcc-clustering",
            }
        finally:
            if tmp_path and os.path.exists(tmp_path):
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)

    # ── _detect_and_cluster_speakers ─────────────────────────────

    def _detect_and_cluster_speakers(
        self,
        wav_path: str,
        max_speakers: int,
        min_segment_sec: float,
    ) -> list[dict[str, Any]]:
        """Voice activity detection + MFCC clustering for speaker diarization."""
        import librosa

        y, sr = librosa.load(wav_path, sr=16000, mono=True)

        # Step 1: Voice Activity Detection (VAD)
        # Use energy-based VAD: find frames where RMS exceeds threshold
        frame_length = 2048
        hop_length = 512
        rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
        rms_db = librosa.amplitude_to_db(rms, ref=np.max)

        # Dynamic threshold: mean - 10dB for speech
        threshold_db = np.mean(rms_db) - 10
        speech_frames = rms_db > threshold_db

        # Merge adjacent speech frames into segments
        min_frames = max(1, int(min_segment_sec * sr / hop_length))
        segments = self._merge_speech_frames(speech_frames, min_frames, hop_length, sr)

        if not segments:
            return []

        # Step 2: Extract MFCC features for each segment
        mfcc_features = []
        valid_segments = []
        for start_sample, end_sample in segments:
            segment_y = y[start_sample:end_sample]
            if len(segment_y) < sr * 0.1:  # skip very short segments
                continue
            mfcc = librosa.feature.mfcc(y=segment_y, sr=sr, n_mfcc=13)
            mfcc_mean = np.mean(mfcc, axis=1)
            mfcc_std = np.std(mfcc, axis=1)
            features = np.concatenate([mfcc_mean, mfcc_std])
            mfcc_features.append(features)
            valid_segments.append((start_sample, end_sample))

        if len(valid_segments) < 2:
            # Only one segment — single speaker
            result = []
            for i, (start_s, end_s) in enumerate(valid_segments):
                result.append({
                    "speaker_id": "speaker_0",
                    "start_seconds": round(start_s / sr, 2),
                    "end_seconds": round(end_s / sr, 2),
                    "duration_seconds": round((end_s - start_s) / sr, 2),
                })
            return result

        # Step 3: Cluster segments by MFCC similarity
        mfcc_array = np.array(mfcc_features)

        # Normalize features
        mfcc_array = (mfcc_array - np.mean(mfcc_array, axis=0)) / (
            np.std(mfcc_array, axis=0) + 1e-8
        )

        labels = self._cluster_segments(mfcc_array, max_speakers)

        # Build result
        result = []
        for i, (start_s, end_s) in enumerate(valid_segments):
            speaker_idx = int(labels[i])
            result.append({
                "speaker_id": f"speaker_{speaker_idx}",
                "start_seconds": round(start_s / sr, 2),
                "end_seconds": round(end_s / sr, 2),
                "duration_seconds": round((end_s - start_s) / sr, 2),
            })

        return result

    # ── _merge_speech_frames ─────────────────────────────────────

    @staticmethod
    def _merge_speech_frames(
        speech_frames: np.ndarray,
        min_frames: int,
        hop_length: int,
        sr: int,
    ) -> list[tuple[int, int]]:
        """Merge adjacent speech frames into contiguous segments."""
        segments: list[tuple[int, int]] = []
        start = None

        for i, is_speech in enumerate(speech_frames):
            if is_speech and start is None:
                start = i
            elif not is_speech and start is not None:
                end = i
                if end - start >= min_frames:
                    segments.append((
                        int(start * hop_length),
                        int(end * hop_length),
                    ))
                start = None

        if start is not None:
            end = len(speech_frames)
            if end - start >= min_frames:
                segments.append((
                    int(start * hop_length),
                    int(end * hop_length),
                ))

        return segments

    # ── _cluster_segments ────────────────────────────────────────

    @staticmethod
    def _cluster_segments(features: np.ndarray, max_speakers: int) -> np.ndarray:
        """Cluster feature vectors using agglomerative clustering."""
        from scipy.cluster.hierarchy import fcluster, linkage
        from scipy.spatial.distance import pdist

        if len(features) <= 1:
            return np.zeros(len(features), dtype=int)

        # Compute pairwise cosine distances
        dists = pdist(features, metric="cosine")
        dists = np.nan_to_num(dists, nan=1.0, posinf=1.0)

        # Agglomerative clustering (average linkage for cosine distances)
        z = linkage(dists, method="average")
        labels = fcluster(z, t=min(max_speakers, len(features)), criterion="maxclust")
        return labels - 1  # zero-index


# ── Register ──────────────────────────────────────────────────────────

register_tool(SpeakerDiarizationTool())
