"""
Audio/Speech Processing Tools — Audio Format Converter.

audio_format_converter → Convert audio files between WAV, MP3, FLAC, OGG,
    and other formats using ffmpeg via pydub.
"""

from __future__ import annotations

import base64
import contextlib
import io
import logging
import os
import tempfile
from typing import Any

from pydantic import Field
from pydub import AudioSegment
from pydub.utils import mediainfo

from app.tools._file_utils import resolve_input
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

CONVERTER_TIMEOUT = int(os.getenv("AUDIO_CONVERTER_TIMEOUT", "120"))
MAX_FILE_SIZE_MB = int(os.getenv("AUDIO_CONVERTER_MAX_MB", "500"))

# Format → (ffmpeg codec name, default bitrate, typical extension)
_SUPPORTED_FORMATS: dict[str, tuple[str, str, str]] = {
    "mp3": ("libmp3lame", "192k", ".mp3"),
    "wav": ("pcm_s16le", "", ".wav"),
    "flac": ("flac", "", ".flac"),
    "ogg": ("libvorbis", "128k", ".ogg"),
    "aac": ("aac", "192k", ".aac"),
    "m4a": ("aac", "192k", ".m4a"),
    "opus": ("libopus", "96k", ".opus"),
    "wma": ("wmav2", "128k", ".wma"),
}


# ── Input ─────────────────────────────────────────────────────────────


class AudioFormatConverterInput(ToolInput):
    data: str | None = Field(
        None,
        description="Base64-encoded audio data (data URI prefix optional)",
    )
    url: str | None = Field(
        None,
        description="URL to fetch the audio file from",
    )
    target_format: str = Field(
        ...,
        description="Target audio format: mp3, wav, flac, ogg, aac, m4a, opus, wma",
    )
    bitrate: str | None = Field(
        None,
        description="Target bitrate (e.g. '128k', '192k', '320k'). Uses format default if unset.",
    )
    sample_rate: int | None = Field(
        None,
        ge=8000,
        le=48000,
        description="Target sample rate in Hz (e.g. 44100). Preserved if unset.",
    )
    channels: int | None = Field(
        None,
        ge=1,
        le=2,
        description="Target channels: 1 (mono) or 2 (stereo). Preserved if unset.",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class AudioFormatConverterTool(BaseTool):
    """Convert audio files between formats using ffmpeg."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="audio_format_converter",
            name="Audio Format Converter",
            description=(
                "Convert audio files between WAV, MP3, FLAC, OGG, AAC, M4A, "
                "OPUS, and WMA formats. Supports custom bitrate, sample rate, "
                "and channel configuration."
            ),
            category="audio-speech-processing",
            input_schema=AudioFormatConverterInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["audio", "convert", "format", "ffmpeg", "pydub"],
            requires_auth=False,
            timeout_seconds=CONVERTER_TIMEOUT + 15,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = AudioFormatConverterInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if not validated.data and not validated.url:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Either 'data' (base64) or 'url' must be provided",
            )

        target = validated.target_format.lower()
        if target not in _SUPPORTED_FORMATS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unsupported target format: '{validated.target_format}'. "
                f"Supported: {', '.join(sorted(_SUPPORTED_FORMATS))}",
            )

        try:
            result = await self._convert(validated, target)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("audio_format_converter failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _convert ─────────────────────────────────────────────────

    async def _convert(
        self, validated: AudioFormatConverterInput, target: str
    ) -> dict[str, Any]:
        """Load audio and convert to target format."""
        audio_bytes = await resolve_input(
            validated.data, validated.url, label="audio", fetch_timeout=60
        )

        # Check file size
        size_mb = len(audio_bytes) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            return {
                "error": f"File too large: {size_mb:.1f}MB (max {MAX_FILE_SIZE_MB}MB)",
                "converted_size_bytes": 0,
                "input_format": "unknown",
                "output_format": target,
            }

        tmp_path: str | None = None
        try:
            # Write to temp file so mediainfo can inspect the raw bytes
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            audio = AudioSegment.from_file(tmp_path)

            # Capture input metadata
            input_info: dict[str, Any] = {
                "duration_seconds": round(len(audio) / 1000.0, 2),
                "sample_rate": audio.frame_rate,
                "channels": audio.channels,
                "sample_width": audio.sample_width,
            }
            try:
                info = mediainfo(tmp_path)
                input_info["codec"] = info.get("codec_name", "unknown")
                input_info["bit_rate"] = int(info.get("bit_rate", 0))
            except Exception:
                input_info["codec"] = "unknown"
                input_info["bit_rate"] = 0

            # Apply transformations
            if validated.sample_rate and validated.sample_rate != audio.frame_rate:
                audio = audio.set_frame_rate(validated.sample_rate)
            if validated.channels == 1 and audio.channels == 2:
                audio = audio.set_channels(1)
            elif validated.channels == 2 and audio.channels == 1:
                audio = audio.set_channels(2)

            # Export to target format
            codec, default_bitrate, _ = _SUPPORTED_FORMATS[target]
            export_kwargs: dict[str, Any] = {"format": target}
            if codec:
                export_kwargs["codec"] = codec
            bitrate = validated.bitrate or default_bitrate
            if bitrate:
                export_kwargs["bitrate"] = bitrate

            buf = io.BytesIO()
            audio.export(buf, **export_kwargs)
            converted_bytes = buf.getvalue()
            converted_b64 = base64.b64encode(converted_bytes).decode("ascii")

            return {
                "converted_data": converted_b64,
                "converted_size_bytes": len(converted_bytes),
                "input_format": input_info,
                "output_format": target,
                "output_bitrate": bitrate or "default",
                "output_sample_rate": audio.frame_rate,
                "output_channels": audio.channels,
            }
        finally:
            if tmp_path and os.path.exists(tmp_path):
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)


# ── Register ──────────────────────────────────────────────────────────

register_tool(AudioFormatConverterTool())
