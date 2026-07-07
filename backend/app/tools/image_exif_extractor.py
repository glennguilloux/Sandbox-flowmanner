"""
File Handling Tools — Image EXIF Extractor.

image_exif_extractor  → extract EXIF metadata from image files
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS
from pydantic import Field

from app.tools._file_utils import resolve_input
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _convert_gps_to_decimal(gps_info: tuple, gps_ref: str) -> float | None:
    """Convert GPS DMS tuple (degrees, minutes, seconds) to decimal degrees."""
    try:
        degrees, minutes, seconds = gps_info
        decimal = float(degrees) + float(minutes) / 60.0 + float(seconds) / 3600.0
        if gps_ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except (TypeError, ValueError):
        return None


def _extract_exif(image: Image.Image) -> dict[str, Any]:
    """Extract all EXIF data from a PIL image into a structured dict."""
    exif_data = image.getexif()
    if not exif_data:
        return {}

    result: dict[str, Any] = {}
    gps_data: dict[str, Any] = {}

    for tag_id, value in exif_data.items():
        tag_name = TAGS.get(tag_id, str(tag_id))

        if tag_name == "GPSInfo":
            for gps_tag_id, gps_value in value.items():
                gps_tag_name = GPSTAGS.get(gps_tag_id, str(gps_tag_id))
                gps_data[gps_tag_name] = gps_value
        elif isinstance(value, bytes):
            try:
                result[tag_name] = value.decode("ascii", errors="replace").strip("\x00")
            except Exception:
                result[tag_name] = f"<binary, {len(value)} bytes>"
        else:
            result[tag_name] = value

    # Convert GPS coordinates to decimal if present
    if gps_data:
        gps_result: dict[str, Any] = dict(gps_data)
        if "GPSLatitude" in gps_data and "GPSLatitudeRef" in gps_data:
            gps_result["decimal_latitude"] = _convert_gps_to_decimal(
                gps_data["GPSLatitude"], gps_data["GPSLatitudeRef"]
            )
        if "GPSLongitude" in gps_data and "GPSLongitudeRef" in gps_data:
            gps_result["decimal_longitude"] = _convert_gps_to_decimal(
                gps_data["GPSLongitude"], gps_data["GPSLongitudeRef"]
            )
        if "GPSAltitude" in gps_data:
            alt = gps_data["GPSAltitude"]
            gps_result["altitude_meters"] = float(alt) if isinstance(alt, int | float) else alt

        result["gps"] = gps_result

    return result


_READABLE_EXIF_FIELDS = [
    "Make",
    "Model",
    "DateTimeOriginal",
    "DateTimeDigitized",
    "Software",
    "Artist",
    "Copyright",
    "ImageDescription",
    "Orientation",
    "XResolution",
    "YResolution",
    "ResolutionUnit",
    "ExposureTime",
    "FNumber",
    "ISOSpeedRatings",
    "FocalLength",
    "Flash",
    "WhiteBalance",
    "ColorSpace",
    "MeteringMode",
    "ExposureProgram",
    "SceneCaptureType",
    "LensMake",
    "LensModel",
]

# ---------------------------------------------------------------------------
# image_exif_extractor
# ---------------------------------------------------------------------------


class ImageExifExtractorInput(ToolInput):
    data: str | None = Field(
        None,
        description="Base64-encoded image content (optional if 'url' is provided)",
    )
    url: str | None = Field(
        None,
        description="URL to fetch the image from (optional if 'data' is provided)",
    )
    extract_thumbnail: bool = Field(
        False,
        description="Extract the embedded EXIF thumbnail as base64 if present in IFD1",
    )


class ImageExifExtractorTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="image_exif_extractor",
            visibility="opt_in",
            required_scopes=[],
            name="Image EXIF Extractor",
            description="Extract EXIF metadata, GPS coordinates, and device info from images",
            category="file-handling",
            input_schema=ImageExifExtractorInput.schema_extra(),
            tags=["image", "exif", "metadata", "gps", "file-handling"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ImageExifExtractorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        try:
            img_bytes = await resolve_input(validated.data, validated.url, label="image")
        except ValueError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Failed to read image: {e}")

        try:
            image = Image.open(io.BytesIO(img_bytes))

            result: dict[str, Any] = {
                "format": image.format or "unknown",
                "mode": image.mode,
                "width": image.width,
                "height": image.height,
                "file_size_bytes": len(img_bytes),
                "is_animated": getattr(image, "is_animated", False),
                "n_frames": getattr(image, "n_frames", 1),
            }

            # EXIF extraction
            exif = _extract_exif(image)
            if exif:
                result["exif"] = exif
                result["has_exif"] = True
            else:
                result["has_exif"] = False

            # Extract commonly used fields into a flat dict
            relevant: dict[str, Any] = {}
            for field in _READABLE_EXIF_FIELDS:
                if field in exif:
                    relevant[field] = exif[field]
            if relevant:
                result["camera_info"] = relevant

            # EXIF thumbnail from IFD1 (not the main image thumbnail)
            if validated.extract_thumbnail:
                try:
                    # IFD1 is where the embedded thumbnail lives
                    if hasattr(image, "_getexif") and image._getexif():
                        raw_exif = image._getexif()
                        # The thumbnail is stored as bytes at key 0x0201 in IFD1
                        # PIL exposes it via get_thumbnail() on some formats
                        thumb = image._getexif().get(0x0201)
                        if isinstance(thumb, bytes):
                            result["thumbnail_base64"] = base64.b64encode(thumb).decode("ascii")
                            result["thumbnail_size_bytes"] = len(thumb)
                except Exception:
                    logger.debug("exif_thumbnail_failed", exc_info=True)

            image.close()
            return ToolResult.success_result(tool_id=self.tool_id, result=result)

        except Exception as e:
            logger.exception("image_exif_extractor failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

register_tool(ImageExifExtractorTool())
