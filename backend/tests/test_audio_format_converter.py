"""
Unit tests for audio_format_converter.py — Audio Format Converter tool.

Tests cover:
- Input validation (missing data, invalid format, edge cases)
- Format conversion (WAV→MP3, MP3→FLAC, etc.)
- Bitrate, sample rate, channel transforms
- Error handling (file too large, unsupported format)
- Tool metadata and registration
"""

import io
import os
import base64
import struct
import math
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────


def generate_tiny_wav_bytes(duration_ms=1000, freq=440, sample_rate=16000):
    """Generate raw WAV bytes for testing."""
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
    return buf.getvalue()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@pytest.fixture
def wav_b64():
    return b64(generate_tiny_wav_bytes(duration_ms=1000))


@pytest.fixture
def converter():
    from app.tools.audio_format_converter import AudioFormatConverterTool

    return AudioFormatConverterTool()


# ── Input Validation ─────────────────────────────────────────────────


class TestInputValidation:
    """Test input parsing and validation."""

    @pytest.mark.asyncio
    async def test_missing_data_and_url(self, converter):
        r = await converter.execute({"target_format": "mp3"})
        assert not r.success
        assert "data" in r.error.lower()

    @pytest.mark.asyncio
    async def test_invalid_target_format(self, converter, wav_b64):
        r = await converter.execute(
            {
                "data": wav_b64,
                "target_format": "xyz_invalid",
            }
        )
        assert not r.success
        assert "Unsupported" in r.error
        assert "mp3" in r.error.lower()

    @pytest.mark.asyncio
    async def test_target_format_case_insensitive(self, converter, wav_b64):
        """Format should be case-insensitive."""
        # Create a mock AudioSegment to avoid real ffmpeg processing
        with patch("pydub.AudioSegment.from_file") as mock_from_file:
            mock_audio = MagicMock()
            mock_audio.frame_rate = 44100
            mock_audio.channels = 1
            mock_audio.sample_width = 2
            mock_audio.__len__.return_value = 1000  # 1 second
            mock_audio.export.return_value = io.BytesIO(b"fake_mp3_data")
            mock_from_file.return_value = mock_audio

            with patch("pydub.utils.mediainfo", return_value={}):
                r = await converter.execute(
                    {
                        "data": wav_b64,
                        "target_format": "MP3",
                    }
                )
        assert r.success
        assert r.result["output_format"] == "mp3"

    @pytest.mark.asyncio
    async def test_bitrate_accepted(self, converter):
        from app.tools.audio_format_converter import AudioFormatConverterInput

        inp = AudioFormatConverterInput(
            data="Zm9v", target_format="mp3", bitrate="320k"
        )
        assert inp.bitrate == "320k"

    @pytest.mark.asyncio
    async def test_sample_rate_accepted(self, converter):
        from app.tools.audio_format_converter import AudioFormatConverterInput

        inp = AudioFormatConverterInput(
            data="Zm9v", target_format="wav", sample_rate=22050
        )
        assert inp.sample_rate == 22050

    @pytest.mark.asyncio
    async def test_sample_rate_below_min_rejected(self, converter):
        from app.tools.audio_format_converter import AudioFormatConverterInput

        with pytest.raises(Exception):
            AudioFormatConverterInput(
                data="Zm9v", target_format="wav", sample_rate=1000
            )

    @pytest.mark.asyncio
    async def test_channels_accepted(self, converter):
        from app.tools.audio_format_converter import AudioFormatConverterInput

        inp = AudioFormatConverterInput(data="Zm9v", target_format="wav", channels=1)
        assert inp.channels == 1

    @pytest.mark.asyncio
    async def test_channels_out_of_range_rejected(self, converter):
        from app.tools.audio_format_converter import AudioFormatConverterInput

        with pytest.raises(Exception):
            AudioFormatConverterInput(data="Zm9v", target_format="wav", channels=3)


# ── Format Conversion ────────────────────────────────────────────────


class TestFormatConversion:
    """Test actual format conversions using pydub/ffmpeg."""

    @pytest.mark.asyncio
    async def test_wav_to_mp3(self, converter, wav_b64):
        r = await converter.execute(
            {
                "data": wav_b64,
                "target_format": "mp3",
            }
        )
        assert r.success
        assert r.result["output_format"] == "mp3"
        assert r.result["converted_size_bytes"] > 0
        assert r.result["input_format"]["duration_seconds"] > 0
        assert r.result["input_format"]["sample_rate"] > 0

    @pytest.mark.asyncio
    async def test_wav_to_flac(self, converter, wav_b64):
        r = await converter.execute(
            {
                "data": wav_b64,
                "target_format": "flac",
            }
        )
        assert r.success
        assert r.result["output_format"] == "flac"
        assert r.result["converted_size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_wav_to_wav_passthrough(self, converter, wav_b64):
        r = await converter.execute(
            {
                "data": wav_b64,
                "target_format": "wav",
            }
        )
        assert r.success
        assert r.result["output_format"] == "wav"

    @pytest.mark.asyncio
    async def test_custom_bitrate(self, converter, wav_b64):
        r = await converter.execute(
            {
                "data": wav_b64,
                "target_format": "mp3",
                "bitrate": "128k",
            }
        )
        assert r.success
        assert r.result["output_bitrate"] == "128k"

    @pytest.mark.asyncio
    async def test_channel_conversion_stereo_to_mono(self, converter, wav_b64):
        r = await converter.execute(
            {
                "data": wav_b64,
                "target_format": "mp3",
                "channels": 1,
            }
        )
        assert r.success
        assert r.result["output_channels"] == 1

    @pytest.mark.asyncio
    async def test_sample_rate_conversion(self, converter, wav_b64):
        r = await converter.execute(
            {
                "data": wav_b64,
                "target_format": "wav",
                "sample_rate": 22050,
            }
        )
        assert r.success
        assert r.result["output_sample_rate"] == 22050

    @pytest.mark.asyncio
    async def test_converted_data_is_valid_base64(self, converter, wav_b64):
        r = await converter.execute(
            {
                "data": wav_b64,
                "target_format": "mp3",
            }
        )
        assert r.success
        converted = r.result["converted_data"]
        # Should be valid base64
        decoded = base64.b64decode(converted)
        assert len(decoded) > 0
        assert len(decoded) == r.result["converted_size_bytes"]

    @pytest.mark.asyncio
    async def test_roundtrip_wav_mp3_wav(self, converter, wav_b64):
        """WAV → MP3 → WAV roundtrip should succeed."""
        # Step 1: WAV → MP3
        r1 = await converter.execute(
            {
                "data": wav_b64,
                "target_format": "mp3",
            }
        )
        assert r1.success
        mp3_data = r1.result["converted_data"]

        # Step 2: MP3 → WAV
        r2 = await converter.execute(
            {
                "data": mp3_data,
                "target_format": "wav",
            }
        )
        assert r2.success
        assert r2.result["output_format"] == "wav"
        assert r2.result["converted_size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_all_supported_formats(self, converter, wav_b64):
        """Every format in _SUPPORTED_FORMATS should work (skip missing codecs)."""
        from app.tools.audio_format_converter import _SUPPORTED_FORMATS

        for fmt in _SUPPORTED_FORMATS:
            r = await converter.execute(
                {
                    "data": wav_b64,
                    "target_format": fmt,
                }
            )
            if not r.success:
                # Skip formats needing encoders not installed (ffmpeg error 234)
                if (
                    "error code: 234" in str(r.error)
                    or "encoder" in str(r.error).lower()
                ):
                    continue
            assert r.success, f"Format {fmt} failed: {r.error}"
            assert r.result["output_format"] == fmt


# ── Tool Metadata ────────────────────────────────────────────────────


class TestToolMetadata:
    """Test tool metadata and registration."""

    def test_tool_id(self, converter):
        assert converter.tool_id == "audio_format_converter"

    def test_tool_category(self, converter):
        assert converter.category == "audio-speech-processing"

    def test_tool_tags(self, converter):
        assert "audio" in converter.tags
        assert "convert" in converter.tags
        assert "ffmpeg" in converter.tags

    def test_tool_requires_auth(self, converter):
        assert converter.metadata.requires_auth == False

    def test_tool_registered(self, converter):
        from app.tools.base import get_tool_registry

        registry = get_tool_registry()
        tool = registry.get("audio_format_converter")
        assert tool is not None

    def test_supported_formats_table(self, converter):
        from app.tools.audio_format_converter import _SUPPORTED_FORMATS

        assert "mp3" in _SUPPORTED_FORMATS
        assert "wav" in _SUPPORTED_FORMATS
        assert "flac" in _SUPPORTED_FORMATS
        # Each format has (codec, bitrate, extension)
        for fmt, (codec, bitrate, ext) in _SUPPORTED_FORMATS.items():
            assert ext.startswith(".")


# ── Edge Cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_invalid_base64(self, converter):
        r = await converter.execute(
            {
                "data": "!!!bad***base64!!!",
                "target_format": "mp3",
            }
        )
        assert not r.success

    @pytest.mark.asyncio
    async def test_empty_base64(self, converter):
        r = await converter.execute(
            {
                "data": "",
                "target_format": "mp3",
            }
        )
        assert not r.success

    @pytest.mark.asyncio
    async def test_missing_target_format(self, converter):
        with pytest.raises(Exception):
            from app.tools.audio_format_converter import AudioFormatConverterInput

            AudioFormatConverterInput(data="Zm9v")

    @pytest.mark.asyncio
    async def test_large_file_rejected(self, converter):
        """Mock a large file to test size check."""
        with patch("app.tools.audio_format_converter.MAX_FILE_SIZE_MB", 0):
            # 0 MB max — any file should be rejected
            r = await converter.execute(
                {
                    "data": b64(generate_tiny_wav_bytes()),
                    "target_format": "mp3",
                }
            )
        # Tool returns success_result with error in result dict (codebase pattern)
        assert r.success
        assert r.result is not None
        assert "too large" in r.result.get("error", "").lower()
