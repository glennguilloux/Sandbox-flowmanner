"""IO models — modality-agnostic kernel interface (H5.3 / Ω spec VII.12).

IOMessage:   Unified message that traverses the kernel. The kernel is
             modality-agnostic — it consumes and produces IOMessage,
             never text/audio/code directly.

Modality:    Enum of supported input/output modalities.

IOBlob:      Binary blob with MIME type (audio, image, video).

IORender:    Typed render output for a specific modality.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

# ── Modality ────────────────────────────────────────────────────────

class Modality(str, Enum):
    """Supported I/O modalities. The kernel routes to the right renderer."""
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    CODE = "code"
    DOCUMENT = "document"
    TABLE = "table"
    FILE = "file"


# ── IOBlob ──────────────────────────────────────────────────────────

class IOBlob(BaseModel):
    """Binary blob with MIME type.

    Used for audio, image, video, and other binary modalities.
    """
    mime_type: str
    data: bytes | None = None
    url: str | None = None
    duration_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ── IOMessage ───────────────────────────────────────────────────────

class IOMessage(BaseModel):
    """Unified message that the kernel consumes and produces.

    The kernel never sees text directly — it sees IOMessage with
    a Modality renderer.  This is the Ω spec's IOStream model.

    A message can contain multiple renders for different modalities
    (e.g., text + audio for voice responses).
    """
    id: UUID = Field(default_factory=uuid4)
    role: Literal["user", "assistant", "system", "tool"] = "user"
    renders: list[IORender] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── IORender ────────────────────────────────────────────────────────

class IORender(BaseModel):
    """A render output for a specific modality.

    The kernel produces one or more IORenders per response.
    The UI renders each one using the appropriate component:
    - TEXT → text bubble
    - AUDIO → audio player / TTS button
    - CODE → CodeCell
    - DOCUMENT → document preview
    - TABLE → table renderer
    - IMAGE → image preview
    """
    modality: Modality
    content: str | None = None        # For text, code (source)
    language: str | None = None       # For code modality (python, js, etc.)
    blob: IOBlob | None = None        # For audio, image (binary data)
    document: DocumentRender | None = None  # For document modality
    table: TableRender | None = None  # For table modality
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Document / Table renders ────────────────────────────────────────

class DocumentRender(BaseModel):
    """Render for document uploads (PDF, CSV, JSON)."""
    filename: str
    mime_type: str
    page_count: int | None = None
    text_content: str = ""
    structured_data: Any = None
    parse_error: str | None = None


class TableRender(BaseModel):
    """Render for tabular data."""
    columns: list[str]
    rows: list[list[Any]]
    total_rows: int
    source: str = ""  # "csv", "json", "pdf"


# ── Voice / Audio models ────────────────────────────────────────────

class VoiceTranscribeRequest(BaseModel):
    """Request to transcribe audio to text."""
    audio_data: str | None = Field(None, description="Base64-encoded audio")
    audio_url: str | None = Field(None, description="URL to audio file")
    language: str | None = None
    model: str = "whisper-1"


class VoiceTranscribeResponse(BaseModel):
    """Response from voice transcription."""
    text: str
    language: str | None = None
    duration_seconds: float = 0.0
    segments: list[dict[str, Any]] = Field(default_factory=list)


class VoiceSynthesizeRequest(BaseModel):
    """Request to synthesize text to speech."""
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs Rachel


class VoiceSynthesizeResponse(BaseModel):
    """Response from TTS synthesis."""
    audio_url: str | None = None
    audio_base64: str | None = None
    format: str = "mp3"
    duration_seconds: float = 0.0
    voice_id: str = ""


# ── Document parse models ───────────────────────────────────────────

class DocumentParseRequest(BaseModel):
    """Request to parse a document."""
    file_url: str | None = None
    file_data: str | None = Field(None, description="Base64-encoded file")
    filename: str = ""
    mime_type: str = ""


class DocumentParseResponse(BaseModel):
    """Response from document parsing."""
    filename: str
    mime_type: str
    text_content: str = ""
    structured_data: Any = None
    page_count: int | None = None
    error: str | None = None


# ── Code cell models ────────────────────────────────────────────────

class CodeExecuteRequest(BaseModel):
    """Request to execute a code cell."""
    code: str = Field(..., min_length=1)
    language: str = "python"
    timeout_seconds: int = Field(30, ge=1, le=120)


class CodeExecuteResponse(BaseModel):
    """Response from code execution."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    return_code: int = -1
    execution_time_ms: float = 0.0
    error: str | None = None
