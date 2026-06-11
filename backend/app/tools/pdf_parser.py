"""
File Handling Tools — PDF Parser.

pdf_parser  → extract text, tables, and metadata from PDF documents
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from typing import Any

from pydantic import Field

from app.tools._file_utils import resolve_input
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# pdf_parser
# ---------------------------------------------------------------------------


class PdfParserInput(ToolInput):
    data: str | None = Field(
        None,
        description="Base64-encoded PDF content (optional if 'url' is provided)",
    )
    url: str | None = Field(
        None,
        description="URL to fetch the PDF from (optional if 'data' is provided)",
    )
    include_tables: bool = Field(
        True,
        description="Attempt to detect and extract tables from the PDF",
    )
    include_metadata: bool = Field(
        True,
        description="Include PDF document metadata (title, author, etc.)",
    )
    max_pages: int = Field(
        0,
        description="Maximum pages to parse (0 = all pages)",
    )


class PdfParserTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="pdf_parser",
            name="PDF Parser",
            description="Extract text, tables, and metadata from PDF documents",
            category="file-handling",
            input_schema=PdfParserInput.schema_extra(),
            tags=["pdf", "extract", "text", "tables", "file-handling"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = PdfParserInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        try:
            pdf_bytes = await resolve_input(validated.data, validated.url, label="PDF")
        except ValueError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Failed to read PDF: {e}")

        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            import fitz  # pymupdf

            doc = fitz.open(tmp_path)
            total_pages = doc.page_count
            max_p = validated.max_pages if validated.max_pages > 0 else total_pages
            pages: list[dict[str, Any]] = []
            total_text = ""

            for page_num in range(min(max_p, total_pages)):
                page = doc[page_num]
                page_text = page.get_text("text") or ""
                total_text += page_text

                page_data: dict[str, Any] = {
                    "page_number": page_num + 1,
                    "text": page_text,
                    "char_count": len(page_text),
                    "width": page.rect.width,
                    "height": page.rect.height,
                    "rotation": page.rotation,
                }

                # Table detection
                if validated.include_tables:
                    tables = page.find_tables()
                    if tables and tables.tables:
                        extracted_tables: list[dict[str, Any]] = []
                        for tbl in tables.tables:
                            cells = tbl.extract() if tbl.extract() else []
                            extracted_tables.append(
                                {
                                    "rows": tbl.row_count,
                                    "columns": tbl.col_count,
                                    "cells": [[cell.strip() if cell else "" for cell in row] for row in cells],
                                }
                            )
                        page_data["tables"] = extracted_tables

                pages.append(page_data)

            # Capture metadata BEFORE closing the document
            doc_meta: dict[str, Any] = {}
            if validated.include_metadata:
                meta = doc.metadata or {}
                doc_meta = {
                    "title": meta.get("title", ""),
                    "author": meta.get("author", ""),
                    "subject": meta.get("subject", ""),
                    "creator": meta.get("creator", ""),
                    "producer": meta.get("producer", ""),
                    "format": meta.get("format", ""),
                    "creation_date": meta.get("creationDate", ""),
                    "modification_date": meta.get("modDate", ""),
                }

            doc.close()

            result: dict[str, Any] = {
                "total_pages": total_pages,
                "pages_parsed": len(pages),
                "pages": pages,
                "full_text": total_text,
                "total_chars": len(total_text),
            }

            if validated.include_metadata:
                result["metadata"] = doc_meta

            return ToolResult.success_result(tool_id=self.tool_id, result=result)

        except Exception as e:
            logger.exception("pdf_parser failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

register_tool(PdfParserTool())
