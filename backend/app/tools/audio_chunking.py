"""
File Handling Tools — Audio Chunking.

audio_chunking  → split audio files into optimal segments for transcription APIs
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

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

_SUPPORTED_CODECS = {"mp3", "wav", "ogg", "flac", "m4a", "aac", "opus", "wma", "webm"}

# ---------------------------------------------------------------------------
# audio_chunking
# ---------------------------------------------------------------------------


class AudioChunkingInput(ToolInput):
    data: str | None = Field(
        None,
        description="Base64-encoded audio content (optional if 'url' is provided)",
    )
    url: str | None = Field(
        None,
        description="URL to fetch the audio file from (optional if 'data' is provided)",
    )
    chunk_duration_seconds: int = Field(
        300,
        description=(
            "Target duration per chunk in seconds (default: 300 = 5 minutes). "
            "Must be at least 1. Overlap must be less than chunk duration."
        ),
    )
    overlap_seconds: float = Field(
        1.0,
        description="Overlap between chunks in seconds for context preservation (default: 1.0)",
    )
    output_format: str = Field(
        "mp3",
        description="Output audio format for chunks: mp3, wav, ogg, flac, or m4a",
    )
    max_chunks: int = Field(
        0,
        description="Maximum number of chunks to produce (0 = unlimited)",
    )


class AudioChunkingTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="audio_chunking",
            name="Audio Chunking",
            description="Split large audio files into optimal segments for transcription APIs",
            category="file-handling",
            input_schema=AudioChunkingInput.schema_extra(),
            tags=["audio", "chunking", "transcription", "split", "file-handling"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = AudioChunkingInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.chunk_duration_seconds < 1:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="chunk_duration_seconds must be at least 1",
            )

        if validated.overlap_seconds >= validated.chunk_duration_seconds:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=(
                    f"overlap_seconds ({validated.overlap_seconds}) must be less than "
                    f"chunk_duration_seconds ({validated.chunk_duration_seconds})"
                ),
            )

        out_fmt = validated.output_format.lower()
        if out_fmt not in _SUPPORTED_CODECS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unsupported output format: '{validated.output_format}'. "
                f"Supported: {', '.join(sorted(_SUPPORTED_CODECS))}",
            )

        tmp_path: str | None = None
        try:
            try:
                audio_bytes = await resolve_input(
                    validated.data, validated.url,
                    label="audio", fetch_timeout=60,
                )
            except ValueError as e:
                return ToolResult.error_result(tool_id=self.tool_id, error=str(e))
            except Exception as e:
                return ToolResult.error_result(
                    tool_id=self.tool_id, error=f"Failed to read audio: {e}"
                )

            # Write to temp file so pydub + ffmpeg can read it
            with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            # Load audio (pydub auto-detects format via ffprobe)
            audio = AudioSegment.from_file(tmp_path)
            duration_ms = len(audio)
            duration_sec = duration_ms / 1000.0

            chunk_ms = validated.chunk_duration_seconds * 1000
            overlap_ms = int(validated.overlap_seconds * 1000)
            # Ensure minimum advance of 1ms to prevent infinite loop
            advance_ms = max(1, chunk_ms - overlap_ms)

            chunks: list[dict[str, Any]] = []
            start_ms = 0
            chunk_idx = 0

            while start_ms < duration_ms:
                if validated.max_chunks > 0 and chunk_idx >= validated.max_chunks:
                    break

                end_ms = min(start_ms + chunk_ms, duration_ms)
                segment = audio[start_ms:end_ms]

                # Export chunk to base64
                buf = io.BytesIO()
                segment.export(buf, format=out_fmt)
                chunk_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                chunk_size = buf.tell()

                chunks.append({
                    "index": chunk_idx,
                    "start_seconds": round(start_ms / 1000.0, 3),
                    "end_seconds": round(end_ms / 1000.0, 3),
                    "duration_seconds": round((end_ms - start_ms) / 1000.0, 3),
                    "size_bytes": chunk_size,
                    "data": chunk_b64,
                })

                chunk_idx += 1
                start_ms += advance_ms

            result: dict[str, Any] = {
                "total_duration_seconds": round(duration_sec, 3),
                "chunk_count": len(chunks),
                "chunk_duration_seconds": validated.chunk_duration_seconds,
                "overlap_seconds": validated.overlap_seconds,
                "output_format": out_fmt,
                "chunks": chunks,
            }

            # Audio metadata via mediainfo (ffprobe)
            try:
                info = mediainfo(tmp_path)
                result["audio_metadata"] = {
                    "codec": info.get("codec_name", "unknown"),
                    "sample_rate": int(info.get("sample_rate", 0)),
                    "channels": int(info.get("channels", 0)),
                    "bit_rate": int(info.get("bit_rate", 0)),
                    "duration_seconds": float(info.get("duration", 0)),
                }
            except Exception:
                result["audio_metadata"] = {
                    "codec": "unknown",
                    "sample_rate": audio.frame_rate,
                    "channels": audio.channels,
                    "sample_width": audio.sample_width,
                    "duration_seconds": duration_sec,
                }

            return ToolResult.success_result(tool_id=self.tool_id, result=result)

        except Exception as e:
            logger.exception("audio_chunking failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

register_tool(AudioChunkingTool())
