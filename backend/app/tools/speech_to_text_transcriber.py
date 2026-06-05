"""
Audio/Speech Processing Tools — Speech-to-Text Transcriber.

speech_to_text_transcriber → Convert spoken audio files into accurate text
    transcripts using OpenAI Whisper API or local whisper model.
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import tempfile
from typing import Any

import httpx
from pydantic import Field
from pydub import AudioSegment

from app.tools._file_utils import resolve_input
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
WHISPER_TIMEOUT = int(os.getenv("WHISPER_TIMEOUT", "120"))
USE_LOCAL_WHISPER = os.getenv("USE_LOCAL_WHISPER", "").lower() in ("1", "true", "yes")

# Lazy-loaded local whisper model
_local_whisper_model: Any = None


def _get_local_whisper():
    """Load the local whisper model on first use."""
    global _local_whisper_model
    if _local_whisper_model is None:
        import whisper
        _local_whisper_model = whisper.load_model(
            os.getenv("WHISPER_LOCAL_MODEL", "base")
        )
    return _local_whisper_model


# ── Input ─────────────────────────────────────────────────────────────


class SpeechToTextTranscriberInput(ToolInput):
    data: str | None = Field(
        None,
        description="Base64-encoded audio data (data URI prefix optional)",
    )
    url: str | None = Field(
        None,
        description="URL to fetch the audio file from",
    )
    language: str | None = Field(
        None,
        description="ISO language code (e.g. 'en', 'fr', 'ja'). Auto-detected if not set.",
    )
    response_format: str = Field(
        "verbose_json",
        description="Output format: 'json', 'text', 'srt', 'verbose_json', or 'vtt'",
    )
    prompt: str | None = Field(
        None,
        description="Optional prompt to guide transcription style/spelling",
    )
    temperature: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Sampling temperature (0 = deterministic)",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class SpeechToTextTranscriberTool(BaseTool):
    """Transcribe audio to text using OpenAI Whisper API or local model."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="speech_to_text_transcriber",
            name="Speech-to-Text Transcriber",
            description=(
                "Convert spoken audio files into accurate text transcripts "
                "using OpenAI Whisper API with optional local model fallback. "
                "Supports multiple languages and output formats."
            ),
            category="audio-speech-processing",
            input_schema=SpeechToTextTranscriberInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["audio", "speech", "transcription", "whisper", "stt"],
            requires_auth=False,
            timeout_seconds=WHISPER_TIMEOUT + 30,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = SpeechToTextTranscriberInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if not validated.data and not validated.url:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Either 'data' (base64) or 'url' must be provided",
            )

        valid_formats = ("json", "text", "srt", "verbose_json", "vtt")
        if validated.response_format not in valid_formats:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Invalid response_format: '{validated.response_format}'. "
                f"Use: {', '.join(valid_formats)}",
            )

        try:
            result = await self._transcribe(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("speech_to_text_transcriber failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _transcribe ──────────────────────────────────────────────

    async def _transcribe(
        self, validated: SpeechToTextTranscriberInput
    ) -> dict[str, Any]:
        """Transcribe audio via API or local model."""
        audio_bytes = await resolve_input(
            validated.data, validated.url, label="audio", fetch_timeout=60
        )

        if USE_LOCAL_WHISPER:
            return await self._transcribe_local(audio_bytes, validated)
        elif OPENAI_API_KEY:
            return await self._transcribe_api(audio_bytes, validated)
        else:
            # Fall back to local if available
            try:
                import whisper
                return await self._transcribe_local(audio_bytes, validated)
            except ImportError:
                return {
                    "error": (
                        "OPENAI_API_KEY not configured and local whisper not available. "
                        "Set OPENAI_API_KEY or install openai-whisper."
                    ),
                    "text": "",
                    "engine": "none",
                }

    # ── _transcribe_api ──────────────────────────────────────────

    async def _transcribe_api(
        self, audio_bytes: bytes, validated: SpeechToTextTranscriberInput
    ) -> dict[str, Any]:
        """Send audio to OpenAI Whisper API."""
        # Prepare multipart form data
        files = {
            "file": ("audio.mp3", io.BytesIO(audio_bytes), "audio/mpeg"),
        }
        data: dict[str, Any] = {
            "model": WHISPER_MODEL,
            "response_format": validated.response_format,
            "temperature": validated.temperature,
        }
        if validated.language:
            data["language"] = validated.language
        if validated.prompt:
            data["prompt"] = validated.prompt

        url = f"{OPENAI_BASE_URL.rstrip('/')}/v1/audio/transcriptions"

        async with httpx.AsyncClient(timeout=WHISPER_TIMEOUT) as client:
            resp = await client.post(
                url,
                files=files,
                data={k: str(v) for k, v in data.items()},
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            )
            resp.raise_for_status()

        if validated.response_format == "verbose_json":
            result = resp.json()
            return {
                "text": result.get("text", "").strip(),
                "language": result.get("language", "unknown"),
                "duration_seconds": result.get("duration", 0),
                "segments": result.get("segments", []),
                "engine": "openai-whisper-api",
                "model": WHISPER_MODEL,
            }
        elif validated.response_format == "json":
            result = resp.json()
            return {
                "text": result.get("text", "").strip(),
                "engine": "openai-whisper-api",
                "model": WHISPER_MODEL,
            }
        else:
            return {
                "text": resp.text.strip(),
                "engine": "openai-whisper-api",
                "model": WHISPER_MODEL,
            }

    # ── _transcribe_local ────────────────────────────────────────

    async def _transcribe_local(
        self, audio_bytes: bytes, validated: SpeechToTextTranscriberInput
    ) -> dict[str, Any]:
        """Transcribe using local whisper model."""

        # Convert to WAV via pydub so whisper gets a known-good format
        audio_seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_seg.export(tmp.name, format="wav")
            tmp_path = tmp.name

        try:
            model = _get_local_whisper()
            transcribe_opts: dict[str, Any] = {"temperature": validated.temperature}
            if validated.language:
                transcribe_opts["language"] = validated.language
            if validated.prompt:
                transcribe_opts["initial_prompt"] = validated.prompt

            result = model.transcribe(tmp_path, **transcribe_opts)

            segments = []
            for seg in result.get("segments", []):
                segments.append({
                    "start": round(seg.get("start", 0), 2),
                    "end": round(seg.get("end", 0), 2),
                    "text": seg.get("text", "").strip(),
                    "confidence": round(seg.get("confidence", 0), 2),
                })

            return {
                "text": result.get("text", "").strip(),
                "language": result.get("language", "unknown"),
                "duration_seconds": round(result.get("duration", 0), 2),
                "segments": segments,
                "engine": "local-whisper",
                "model": os.getenv("WHISPER_LOCAL_MODEL", "base"),
            }
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)


# ── Register ──────────────────────────────────────────────────────────

register_tool(SpeechToTextTranscriberTool())
