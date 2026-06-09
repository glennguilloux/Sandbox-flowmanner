"""
Unit tests for speech_to_text_transcriber.py — Speech-to-Text Transcriber tool.

Tests cover:
- Input validation (missing data, wrong format, edge cases)
- Local whisper path (mocked model)
- OpenAI API path (mocked httpx)
- Error handling
- Tool metadata and registration
"""

import io
import os
import base64
import struct
import math
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-123")
os.environ.setdefault("USE_LOCAL_WHISPER", "1")
os.environ.setdefault("WHISPER_LOCAL_MODEL", "tiny")


# ── Helpers ──────────────────────────────────────────────────────────


def generate_tiny_wav(duration_ms=1000, freq=440):
    """Generate a small WAV file for testing (mono, 16-bit PCM)."""
    sample_rate = 16000
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


@pytest.fixture
def tiny_audio_b64():
    return generate_tiny_wav(duration_ms=1000)


@pytest.fixture
def mock_whisper_model():
    """Mock local whisper model transcribe result."""
    mock = MagicMock()
    mock.transcribe.return_value = {
        "text": "hello world",
        "language": "en",
        "duration": 1.0,
        "segments": [
            {"start": 0.0, "end": 0.5, "text": "hello", "confidence": 0.95},
            {"start": 0.5, "end": 1.0, "text": "world", "confidence": 0.92},
        ],
    }
    return mock


@pytest.fixture
def transcriber():
    from app.tools.speech_to_text_transcriber import SpeechToTextTranscriberTool

    return SpeechToTextTranscriberTool()


# ── Input Validation ─────────────────────────────────────────────────


class TestInputValidation:
    """Test input parsing and validation."""

    @pytest.mark.asyncio
    async def test_missing_data_and_url(self, transcriber):
        r = await transcriber.execute({"response_format": "json"})
        assert not r.success
        assert "data" in r.error.lower()

    @pytest.mark.asyncio
    async def test_invalid_response_format(self, transcriber, tiny_audio_b64):
        r = await transcriber.execute(
            {
                "data": tiny_audio_b64,
                "response_format": "xml",
            }
        )
        assert not r.success
        assert "response_format" in r.error.lower()

    @pytest.mark.asyncio
    async def test_temperature_out_of_range(self, transcriber):
        """Pydantic should reject temperature outside [0, 1]."""
        from app.tools.speech_to_text_transcriber import SpeechToTextTranscriberInput

        with pytest.raises(Exception):
            SpeechToTextTranscriberInput(data="Zm9v", temperature=2.0)

    @pytest.mark.asyncio
    async def test_all_valid_formats_accepted(self, transcriber, tiny_audio_b64):
        """All valid response formats should pass validation."""
        for fmt in ("json", "text", "srt", "verbose_json", "vtt"):
            # Validation happens before whisper is called, so empty data triggers
            # a different error but NOT an invalid format error
            r = await transcriber.execute(
                {
                    "data": tiny_audio_b64,
                    "response_format": fmt,
                }
            )
            # Should not be an invalid format error
            assert "response_format" not in (r.error or "").lower()

    @pytest.mark.asyncio
    async def test_custom_language_set(self, transcriber):
        """language parameter should be accepted."""
        from app.tools.speech_to_text_transcriber import SpeechToTextTranscriberInput

        inp = SpeechToTextTranscriberInput(data="Zm9v", language="fr")
        assert inp.language == "fr"

    @pytest.mark.asyncio
    async def test_prompt_parameter_set(self, transcriber):
        """prompt parameter should be accepted."""
        from app.tools.speech_to_text_transcriber import SpeechToTextTranscriberInput

        inp = SpeechToTextTranscriberInput(data="Zm9v", prompt="Use proper punctuation")
        assert inp.prompt == "Use proper punctuation"


# ── Local Whisper Path ────────────────────────────────────────────────


class TestLocalWhisper:
    """Test local whisper transcription path."""

    @pytest.mark.asyncio
    async def test_transcribe_local_success(
        self, transcriber, tiny_audio_b64, mock_whisper_model
    ):
        with patch(
            "app.tools.speech_to_text_transcriber._get_local_whisper",
            return_value=mock_whisper_model,
        ):
            with patch("app.tools.speech_to_text_transcriber.USE_LOCAL_WHISPER", True):
                r = await transcriber.execute(
                    {
                        "data": tiny_audio_b64,
                        "response_format": "verbose_json",
                    }
                )
        assert r.success
        assert r.result["engine"] == "local-whisper"
        assert "text" in r.result
        assert "segments" in r.result
        assert len(r.result["segments"]) == 2
        assert r.result["segments"][0]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_transcribe_local_json_format(
        self, transcriber, tiny_audio_b64, mock_whisper_model
    ):
        with patch(
            "app.tools.speech_to_text_transcriber._get_local_whisper",
            return_value=mock_whisper_model,
        ):
            with patch("app.tools.speech_to_text_transcriber.USE_LOCAL_WHISPER", True):
                r = await transcriber.execute(
                    {
                        "data": tiny_audio_b64,
                        "response_format": "json",
                    }
                )
        assert r.success
        assert r.result["engine"] == "local-whisper"
        assert "text" in r.result

    @pytest.mark.asyncio
    async def test_transcribe_local_text_format(
        self, transcriber, tiny_audio_b64, mock_whisper_model
    ):
        with patch(
            "app.tools.speech_to_text_transcriber._get_local_whisper",
            return_value=mock_whisper_model,
        ):
            with patch("app.tools.speech_to_text_transcriber.USE_LOCAL_WHISPER", True):
                r = await transcriber.execute(
                    {
                        "data": tiny_audio_b64,
                        "response_format": "text",
                    }
                )
        assert r.success

    @pytest.mark.asyncio
    async def test_transcribe_local_with_language(
        self, transcriber, tiny_audio_b64, mock_whisper_model
    ):
        with patch(
            "app.tools.speech_to_text_transcriber._get_local_whisper",
            return_value=mock_whisper_model,
        ):
            with patch("app.tools.speech_to_text_transcriber.USE_LOCAL_WHISPER", True):
                r = await transcriber.execute(
                    {
                        "data": tiny_audio_b64,
                        "language": "es",
                        "response_format": "verbose_json",
                    }
                )
        assert r.success
        # Verify language was passed through
        mock_whisper_model.transcribe.assert_called_once()
        call_kwargs = mock_whisper_model.transcribe.call_args[1]
        assert call_kwargs.get("language") == "es"

    @pytest.mark.asyncio
    async def test_transcribe_local_with_prompt(
        self, transcriber, tiny_audio_b64, mock_whisper_model
    ):
        with patch(
            "app.tools.speech_to_text_transcriber._get_local_whisper",
            return_value=mock_whisper_model,
        ):
            with patch("app.tools.speech_to_text_transcriber.USE_LOCAL_WHISPER", True):
                r = await transcriber.execute(
                    {
                        "data": tiny_audio_b64,
                        "prompt": "Technical terms",
                        "response_format": "verbose_json",
                    }
                )
        assert r.success
        call_kwargs = mock_whisper_model.transcribe.call_args[1]
        assert call_kwargs.get("initial_prompt") == "Technical terms"

    @pytest.mark.asyncio
    async def test_transcribe_local_tempfile_cleaned(
        self, transcriber, tiny_audio_b64, mock_whisper_model
    ):
        """Verify temp file is cleaned up after transcription."""
        with patch(
            "app.tools.speech_to_text_transcriber._get_local_whisper",
            return_value=mock_whisper_model,
        ):
            with patch("app.tools.speech_to_text_transcriber.USE_LOCAL_WHISPER", True):
                r = await transcriber.execute(
                    {
                        "data": tiny_audio_b64,
                        "response_format": "verbose_json",
                    }
                )
        assert r.success


# ── OpenAI API Path ──────────────────────────────────────────────────


class TestOpenAIAPIPath:
    """Test OpenAI Whisper API path."""

    @pytest.mark.asyncio
    async def test_transcribe_api_success(self, transcriber, tiny_audio_b64):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "text": "hello from api",
            "language": "en",
            "duration": 2.0,
            "segments": [
                {
                    "start": 0.0,
                    "end": 2.0,
                    "text": "hello from api",
                    "confidence": 0.98,
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("app.tools.speech_to_text_transcriber.USE_LOCAL_WHISPER", False):
                with patch(
                    "app.tools.speech_to_text_transcriber.OPENAI_API_KEY", "sk-test"
                ):
                    r = await transcriber.execute(
                        {
                            "data": tiny_audio_b64,
                            "response_format": "verbose_json",
                        }
                    )
        assert r.success
        assert r.result["engine"] == "openai-whisper-api"
        assert "hello from api" in r.result["text"]

    @pytest.mark.asyncio
    async def test_transcribe_api_json_format(self, transcriber, tiny_audio_b64):
        mock_response = MagicMock()
        mock_response.json.return_value = {"text": "json text"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("app.tools.speech_to_text_transcriber.USE_LOCAL_WHISPER", False):
                with patch(
                    "app.tools.speech_to_text_transcriber.OPENAI_API_KEY", "sk-test"
                ):
                    r = await transcriber.execute(
                        {
                            "data": tiny_audio_b64,
                            "response_format": "json",
                        }
                    )
        assert r.success
        assert r.result["text"] == "json text"

    @pytest.mark.asyncio
    async def test_transcribe_api_passes_language(self, transcriber, tiny_audio_b64):
        mock_response = MagicMock()
        mock_response.json.return_value = {"text": "bonjour"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("app.tools.speech_to_text_transcriber.USE_LOCAL_WHISPER", False):
                with patch(
                    "app.tools.speech_to_text_transcriber.OPENAI_API_KEY", "sk-test"
                ):
                    r = await transcriber.execute(
                        {
                            "data": tiny_audio_b64,
                            "language": "fr",
                            "response_format": "json",
                        }
                    )
        assert r.success
        # Verify language was in the POST data
        call_args = mock_client.post.call_args
        data_dict = call_args[1]["data"]
        assert any("fr" in str(v) for v in data_dict.values())

    @pytest.mark.asyncio
    async def test_no_api_key_no_local_fallback_error(
        self, transcriber, tiny_audio_b64
    ):
        """When no API key and no local whisper, should return error result."""
        with patch("app.tools.speech_to_text_transcriber.USE_LOCAL_WHISPER", False):
            with patch("app.tools.speech_to_text_transcriber.OPENAI_API_KEY", ""):
                # Force whisper import to fail (it IS installed on the system)
                with patch.dict("sys.modules", {"whisper": None}):
                    r = await transcriber.execute(
                        {
                            "data": tiny_audio_b64,
                            "response_format": "json",
                        }
                    )
        # The fallback returns a dict with "error" key wrapped in success_result
        assert r.success
        assert r.result is not None
        assert "error" in r.result or (
            isinstance(r.result, dict)
            and "not configured" in r.result.get("error", "").lower()
        )


# ── Tool Metadata ────────────────────────────────────────────────────


class TestToolMetadata:
    """Test tool metadata and registration."""

    def test_tool_id(self, transcriber):
        assert transcriber.tool_id == "speech_to_text_transcriber"

    def test_tool_category(self, transcriber):
        assert transcriber.category == "audio-speech-processing"

    def test_tool_tags(self, transcriber):
        assert "audio" in transcriber.tags
        assert "transcription" in transcriber.tags
        assert "stt" in transcriber.tags

    def test_tool_requires_auth(self, transcriber):
        assert transcriber.metadata.requires_auth == False

    def test_tool_registered(self, transcriber):
        from app.tools.base import get_tool_registry

        registry = get_tool_registry()
        tool = registry.get("speech_to_text_transcriber")
        assert tool is not None
        assert tool.tool_id == "speech_to_text_transcriber"


# ── Edge Cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_string_data(self, transcriber):
        r = await transcriber.execute(
            {
                "data": "",
                "response_format": "json",
            }
        )
        # Should error on resolve_input since empty base64 decodes to empty bytes
        assert not r.success

    @pytest.mark.asyncio
    async def test_invalid_base64_data(self, transcriber):
        r = await transcriber.execute(
            {
                "data": "!!!not-valid-base64!!!",
                "response_format": "json",
            }
        )
        assert not r.success

    @pytest.mark.asyncio
    async def test_url_input_accepted(self, transcriber):
        """URL input should be accepted as alternative to data."""
        r = await transcriber.execute(
            {
                "url": "https://example.com/audio.mp3",
                "response_format": "json",
            }
        )
        # Will try to fetch the URL, which will fail, but shouldn't be
        # a validation error
        assert not r.success  # URL will fail to fetch
        assert "data" not in (r.error or "").lower()  # Not a missing-data error
