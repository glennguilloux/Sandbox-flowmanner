"""
Multimedia Generation Tools — ElevenLabs Text-to-Speech.

elevenlabs_tts → Convert text to natural-sounding speech via ElevenLabs API with
    configurable voice, model, stability, output format, and SSML support.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
ELEVENLABS_TIMEOUT = int(os.getenv("ELEVENLABS_TIMEOUT", "120"))
ELEVENLABS_STORAGE_DIR = os.getenv("ELEVENLABS_STORAGE_DIR", "/tmp/flowmanner/audio")

ELEVENLABS_MODELS = (
    "eleven_multilingual_v2",
    "eleven_turbo_v2_5",
    "eleven_turbo_v2",
    "eleven_monolingual_v1",
    "eleven_multilingual_v1",
)

OUTPUT_FORMATS = (
    "mp3_44100_128",
    "mp3_44100_192",
    "mp3_22050_32",
    "pcm_44100",
    "pcm_24000",
    "ulaw_8000",
)

MODEL_COST_PER_CHAR = {
    "eleven_multilingual_v2": 0.00005,
    "eleven_turbo_v2_5": 0.00002,
    "eleven_turbo_v2": 0.00002,
    "eleven_monolingual_v1": 0.00002,
    "eleven_multilingual_v1": 0.00002,
}

SSML_PATTERNS = [
    "<speak>",
    "<break",
    "<prosody",
    "<emphasis",
    "<phoneme",
    "<say-as",
    "<sub>",
]


class VoiceSettings(BaseModel):
    """Voice settings for ElevenLabs TTS generation."""

    stability: float = Field(0.5, ge=0.0, le=1.0, description="Voice stability (0.0-1.0)")
    similarity_boost: float = Field(0.75, ge=0.0, le=1.0, description="Similarity to original voice (0.0-1.0)")
    style: float = Field(0.0, ge=0.0, le=1.0, description="Speaking style exaggeration (0.0-1.0)")
    use_speaker_boost: bool = Field(True, description="Enable speaker boost for clarity")


class ElevenLabsTTSInput(ToolInput):
    """Input schema: text, voice_id, model_id, voice_settings, output_format, enable_ssml, save_to_storage."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Text to convert to speech",
    )
    voice_id: str = Field(
        ...,
        description="ElevenLabs voice ID (e.g., '21m00Tcm4TlvDq8ikWAM' for Rachel)",
    )
    model_id: Literal[
        "eleven_multilingual_v2",
        "eleven_turbo_v2_5",
        "eleven_turbo_v2",
        "eleven_monolingual_v1",
        "eleven_multilingual_v1",
    ] = Field(
        "eleven_turbo_v2_5",
        description="Model ID for TTS generation",
    )
    voice_settings: VoiceSettings | None = Field(
        None,
        description="Fine-tune voice stability, similarity, style, and speaker boost",
    )
    output_format: Literal[
        "mp3_44100_128",
        "mp3_44100_192",
        "mp3_22050_32",
        "pcm_44100",
        "pcm_24000",
        "ulaw_8000",
    ] = Field(
        "mp3_44100_128",
        description="Audio output format and quality",
    )
    enable_ssml: bool = Field(
        False,
        description="Treat text as SSML markup",
    )
    api_key: str | None = Field(
        None,
        description="ElevenLabs API key. Uses ELEVENLABS_API_KEY env var if omitted.",
    )
    save_to_storage: bool = Field(
        True,
        description="Save generated audio to local storage",
    )
    optimize_streaming_latency: int = Field(
        0,
        ge=0,
        le=4,
        description="Streaming latency optimization level: 0 (default) to 4 (maximum optimization). Higher values reduce latency but may affect quality.",
    )
    output_prefix: str | None = Field(
        None,
        max_length=100,
        description="Prefix for saved audio filenames",
    )


class ElevenLabsTTSTool(BaseTool):
    """Convert text to speech via ElevenLabs API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="elevenlabs_tts",
            name="ElevenLabs Text-to-Speech",
            description=(
                "Convert text to natural-sounding speech via ElevenLabs API with "
                "configurable voice, model, stability, output format, and SSML "
                "support. Includes cost tracking and local audio storage."
            ),
            category="multimedia-generation",
            input_schema=ElevenLabsTTSInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "audio_url": {"type": "string"},
                    "audio_path": {"type": "string"},
                    "voice_id": {"type": "string"},
                    "voice_name": {"type": "string"},
                    "model_id": {"type": "string"},
                    "format": {"type": "string"},
                    "text": {"type": "string"},
                    "character_count": {"type": "integer"},
                    "duration_seconds": {"type": "number"},
                    "file_size_bytes": {"type": "integer"},
                    "cost_usd": {"type": "number"},
                    "generation_time_ms": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["audio", "tts", "elevenlabs", "speech", "multimedia"],
            requires_auth=True,
            timeout_seconds=ELEVENLABS_TIMEOUT + 30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ElevenLabsTTSInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        api_key = validated.api_key or ELEVENLABS_API_KEY
        if not api_key:
            return ToolResult.error_result(tool_id=self.tool_id, error="ElevenLabs API key required")

        text = validated.text

        # SSML validation
        if validated.enable_ssml and not any(pattern in text for pattern in SSML_PATTERNS):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="SSML mode enabled but no SSML tags found in text",
            )

        # Voice settings defaults
        voice_settings = validated.voice_settings or VoiceSettings(
            stability=0.5,
            similarity_boost=0.75,
            style=0.0,
            use_speaker_boost=True,
        )

        start = time.monotonic()

        try:
            headers = {
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": f"audio/{self._get_mime_type(validated.output_format)}",
            }

            body: dict[str, Any] = {
                "text": text,
                "model_id": validated.model_id,
                "voice_settings": {
                    "stability": voice_settings.stability,
                    "similarity_boost": voice_settings.similarity_boost,
                    "style": voice_settings.style,
                    "use_speaker_boost": voice_settings.use_speaker_boost,
                },
            }

            url = f"{ELEVENLABS_BASE_URL}/text-to-speech/{validated.voice_id}"

            if validated.optimize_streaming_latency > 0:
                params = {
                    "output_format": validated.output_format,
                    "optimize_streaming_latency": str(validated.optimize_streaming_latency),
                }
                query_string = "&".join(f"{k}={v}" for k, v in params.items())
                url += f"/stream?{query_string}"
            else:
                body["output_format"] = validated.output_format

            async with httpx.AsyncClient(timeout=ELEVENLABS_TIMEOUT) as client:
                if validated.optimize_streaming_latency > 0:
                    resp = await client.post(
                        url,
                        headers={**headers, "Accept": "audio/mpeg"},
                        json=body,
                    )
                else:
                    resp = await client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                audio_data = resp.content

            # Get voice name
            voice_name = ""
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    vresp = await client.get(
                        f"{ELEVENLABS_BASE_URL}/voices/{validated.voice_id}",
                        headers={"xi-api-key": api_key},
                    )
                    if vresp.status_code == 200:
                        voice_name = vresp.json().get("name", "")
            except Exception:
                logger.debug("Could not fetch voice name", exc_info=True)

            file_size = len(audio_data)
            duration_estimate = self._estimate_duration(text, 150)  # ~150 chars per second

            # Storage
            audio_path = ""
            if validated.save_to_storage:
                audio_path = self._save_audio(
                    audio_data,
                    validated.voice_id,
                    validated.output_format,
                    validated.output_prefix,
                )

            # Cost
            cost_per_char = MODEL_COST_PER_CHAR.get(validated.model_id, 0.00002)
            cost = round(len(text) * cost_per_char, 6)

            gen_time = int((time.monotonic() - start) * 1000)

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "audio_url": "",  # Will be populated by caller if needed
                    "audio_path": audio_path,
                    "voice_id": validated.voice_id,
                    "voice_name": voice_name,
                    "model_id": validated.model_id,
                    "format": validated.output_format,
                    "text": text[:200] + ("..." if len(text) > 200 else ""),
                    "character_count": len(text),
                    "duration_seconds": round(duration_estimate, 2),
                    "file_size_bytes": file_size,
                    "cost_usd": cost,
                    "generation_time_ms": gen_time,
                    "success": True,
                },
            )

        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(tool_id=self.tool_id, error=f"ElevenLabs API error: {detail}")
        except Exception as e:
            logger.exception("elevenlabs_tts failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    @staticmethod
    def _get_mime_type(output_format: str) -> str:
        """Map output format to MIME type."""
        if output_format.startswith("mp3"):
            return "mpeg"
        elif output_format.startswith("pcm"):
            return "L16"
        elif output_format.startswith("ulaw"):
            return "PCMU"
        return "mpeg"

    @staticmethod
    def _estimate_duration(text: str, chars_per_second: float = 150.0) -> float:
        """Estimate audio duration based on character count."""
        return max(len(text) / chars_per_second, 0.5)

    @staticmethod
    def _save_audio(audio_data: bytes, voice_id: str, fmt: str, prefix: str | None = None) -> str:
        """Save audio bytes to local storage with metadata sidecar."""
        os.makedirs(ELEVENLABS_STORAGE_DIR, exist_ok=True)
        digest = hashlib.sha256(audio_data).hexdigest()[:16]
        ext = fmt.split("_")[0]
        prefix_part = f"{prefix}_" if prefix else ""
        filename = f"{prefix_part}tts_{voice_id}_{digest}.{ext}"
        path = os.path.join(ELEVENLABS_STORAGE_DIR, filename)
        with open(path, "wb") as f:
            f.write(audio_data)

        # Write metadata sidecar
        sidecar = {
            "voice_id": voice_id,
            "format": fmt,
            "file_size": len(audio_data),
            "digest": digest,
        }
        sidecar_path = path + ".meta.json"
        with open(sidecar_path, "w") as f:
            json.dump(sidecar, f, indent=2)

        return path


register_tool(ElevenLabsTTSTool())
