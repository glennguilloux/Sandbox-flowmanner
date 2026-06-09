"""Google Drive integration adapter — 4 actions using Drive API v3."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from app.integrations.adapters.base import BaseIntegrationAdapter
from app.models.integration_models import UserOAuthApp, UserOAuthConnection

logger = logging.getLogger(__name__)

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# 10 MB file-size cap — we refuse to download anything larger.
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 485 760


class GoogleDriveAdapter(BaseIntegrationAdapter):
    """Adapter for Google Drive actions using stored OAuth tokens.

    Actions:
        - ``list_files``: List files in the user's Drive with optional query.
        - ``create_doc``: Create a new Google Doc (optionally with content).
        - ``search_files``: Search files by name or content using Drive query syntax.
        - ``read_file``: Read the contents of a file (text / Google Doc export).
    """

    provider = "google_drive"

    # ── Action dispatch ────────────────────────────────────────────────────

    async def _execute_action(
        self,
        action: str,
        params: dict[str, Any],
        access_token: str,
    ) -> dict[str, Any]:
        match action:
            case "list_files":
                return await self._list_files(params, access_token)
            case "create_doc":
                return await self._create_doc(params, access_token)
            case "search_files":
                return await self._search_files(params, access_token)
            case "read_file":
                return await self._read_file(params, access_token)
            case _:
                return {
                    "success": False,
                    "error": f"Unknown Google Drive action: {action}",
                }

    # ── Headers helper ─────────────────────────────────────────────────────

    @staticmethod
    def _headers(access_token: str) -> dict:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    # ── Action: list_files ─────────────────────────────────────────────────

    async def _list_files(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """List files in the user's Drive.

        Optional params: ``query`` (Drive query string), ``page_size``
        (default 50, max 100).
        """
        page_size = min(int(params.get("page_size", 50)), 100)
        query_str = params.get("query")

        query_params: dict = {
            "pageSize": page_size,
            "fields": "nextPageToken,files(id,name,mimeType,size,webViewLink,modifiedTime)",
        }
        if query_str:
            query_params["q"] = query_str

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{DRIVE_API_BASE}/files",
                params=query_params,
                headers=self._headers(access_token),
            )
            return _parse_drive_response(resp)

    # ── Action: create_doc ─────────────────────────────────────────────────

    async def _create_doc(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """Create a new Google Doc.

        Required params: ``title``
        Optional params: ``folder_id``, ``content`` (initial body text).
        """
        title = params.get("title")
        if not title:
            return {"success": False, "error": "Missing required param: title"}

        # Step 1 — create the empty document via metadata-only insert
        metadata: dict[str, Any] = {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
        }

        # Place inside a folder if requested
        if params.get("folder_id"):
            metadata["parents"] = [params["folder_id"]]

        # Use multipart upload: JSON metadata + optional text content
        boundary = "__flowmanner_boundary__"
        parts: list[str] = []
        parts.append(f"--{boundary}")
        parts.append("Content-Type: application/json; charset=UTF-8")
        parts.append("")
        parts.append(json.dumps(metadata))
        parts.append(f"--{boundary}")
        parts.append("Content-Type: text/plain; charset=UTF-8")
        parts.append("")
        parts.append(params.get("content", ""))
        parts.append(f"--{boundary}--")

        body = "\r\n".join(parts)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                content=body.encode("utf-8"),
                headers={
                    **self._headers(access_token),
                    "Content-Type": f"multipart/related; boundary={boundary}",
                },
            )
            return _parse_drive_response(resp)

    # ── Action: search_files ───────────────────────────────────────────────

    async def _search_files(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """Search files by name or content.

        Required params: ``query`` (Drive query string, e.g.
        ``name contains 'report'``).
        Optional params: ``page_size`` (default 30, max 100).
        """
        query_str = params.get("query")
        if not query_str:
            return {"success": False, "error": "Missing required param: query"}

        page_size = min(int(params.get("page_size", 30)), 100)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{DRIVE_API_BASE}/files",
                params={
                    "q": query_str,
                    "pageSize": page_size,
                    "fields": "nextPageToken,files(id,name,mimeType,size,webViewLink,modifiedTime)",
                },
                headers=self._headers(access_token),
            )
            return _parse_drive_response(resp)

    # ── Action: read_file ──────────────────────────────────────────────────

    async def _read_file(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """Read a file's contents.

        Required params: ``file_id``
        Files larger than 10 MB are refused.

        Returns metadata *and* the decoded content.
        """
        file_id = params.get("file_id")
        if not file_id:
            return {"success": False, "error": "Missing required param: file_id"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Fetch metadata to check size
            meta_resp = await client.get(
                f"{DRIVE_API_BASE}/files/{file_id}",
                params={"fields": "id,name,mimeType,size"},
                headers=self._headers(access_token),
            )
            if meta_resp.status_code >= 400:
                return _parse_drive_response(meta_resp)

            try:
                meta = meta_resp.json()
            except Exception:
                return {
                    "success": False,
                    "error": f"Drive returned non-JSON metadata (HTTP {meta_resp.status_code})",
                }

            size_str = meta.get("size")
            if size_str:
                file_bytes = int(size_str)
                if file_bytes > _MAX_FILE_BYTES:
                    return {
                        "success": False,
                        "error": (
                            f"File is {file_bytes} bytes — exceeds the {_MAX_FILE_BYTES}-byte download limit"
                        ),
                    }

            # 2. Download file content
            content_resp = await client.get(
                f"{DRIVE_API_BASE}/files/{file_id}",
                params={"alt": "media"},
                headers=self._headers(access_token),
            )
            if content_resp.status_code >= 400:
                return _parse_drive_response(content_resp)

            content_bytes = content_resp.content
            # Try to decode as UTF-8 text; fall back to base64 for binary
            try:
                text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                text = base64.b64encode(content_bytes).decode("ascii")
                meta["encoding"] = "base64"

            return {
                "success": True,
                "response": {
                    "metadata": meta,
                    "content": text,
                    "size": len(content_bytes),
                },
            }

    # ── Token refresh (Google OAuth 2.0) ───────────────────────────────────

    async def _refresh_token(self, connection: UserOAuthConnection) -> str | None:
        """Refresh the Google OAuth access token.

        Google supports the standard OAuth 2.0 refresh_token grant.
        """
        refresh_token = connection.get_refresh_token()
        if not refresh_token:
            logger.warning(
                "No refresh token available for Google Drive connection %s",
                connection.id,
            )
            return None

        try:
            from sqlalchemy import select

            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(UserOAuthApp).where(
                        UserOAuthApp.id == connection.app_id,
                        UserOAuthApp.is_active == True,
                    )
                )
                app = result.scalars().first()
                if not app:
                    return None

                client_id = app.get_client_id()
                client_secret = app.get_client_secret()

                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        GOOGLE_TOKEN_URL,
                        data={
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "grant_type": "refresh_token",
                            "refresh_token": refresh_token,
                        },
                    )

                    if resp.status_code >= 400:
                        logger.warning(
                            "Google token refresh HTTP %s: %s",
                            resp.status_code,
                            resp.text[:200],
                        )
                        return None

                    data = resp.json()
                    new_access = data.get("access_token")
                    if not new_access:
                        error = data.get("error", "unknown")
                        logger.warning("Google token refresh failed: %s", error)
                        return None

                    from app.integrations.oauth import encrypt_token

                    db_conn = await db.merge(connection)
                    db_conn.encrypted_access_token = encrypt_token(new_access)
                    # Google may rotate refresh tokens
                    if data.get("refresh_token"):
                        db_conn.encrypted_refresh_token = encrypt_token(
                            data["refresh_token"]
                        )
                    await db.commit()
                    return new_access

        except Exception as e:
            logger.error("Google token refresh failed: %s", e)

        return None


# ── Response parser ───────────────────────────────────────────────────────────


def _parse_drive_response(resp: httpx.Response) -> dict[str, Any]:
    """Parse a Google Drive API response and return a structured result."""
    try:
        data = resp.json()
    except Exception:
        return {
            "success": False,
            "error": f"Drive returned non-JSON response (HTTP {resp.status_code})",
        }

    if resp.status_code < 400:
        return {
            "success": True,
            "response": data,
        }

    # Google error response
    error_info = data.get("error", {})
    if isinstance(error_info, dict):
        error_msg = error_info.get(
            "message", f"Drive API error (HTTP {resp.status_code})"
        )
        # Extract the error reason from the errors array for better matching
        errors_list = error_info.get("errors")
        if errors_list and isinstance(errors_list, list) and len(errors_list) > 0:
            reason = (
                errors_list[0].get("reason")
                if isinstance(errors_list[0], dict)
                else None
            )
            if reason:
                # Pass the camelCase reason string to _drive_error_code for matching
                error_code = reason
            else:
                error_code = error_info.get("code", resp.status_code)
        else:
            error_code = error_info.get("code", resp.status_code)
    else:
        error_msg = str(data)
        error_code = resp.status_code

    # Detect auth errors for token refresh
    if resp.status_code == 401:
        return {"success": False, "error": "token_expired", "error_detail": error_msg}

    return {
        "success": False,
        "error": error_msg,
        "error_code": _drive_error_code(error_code, error_msg),
    }


def _drive_error_code(status_or_code: int | str, message: str) -> str:
    """Distill a stable error code from Google Drive's response."""
    # Google error codes can be numeric HTTP or named codes
    known: dict = {
        "notFound": "not_found",
        "fileNotFound": "file_not_found",
        "insufficientFilePermissions": "permission_denied",
        "rateLimitExceeded": "rate_limited",
        "quotaExceeded": "quota_exceeded",
        "userRateLimitExceeded": "rate_limited",
        "dailyLimitExceeded": "quota_exceeded",
    }

    code_str = str(status_or_code).lower()
    msg_lower = message.lower()

    # Sort by key length descending so longer keys (e.g. "fileNotFound")
    # are matched before shorter substrings (e.g. "notFound").
    for key in sorted(known, key=len, reverse=True):
        if key.lower() in code_str or key.lower() in msg_lower:
            return known[key]

    # Fallback: match common English message patterns against known error codes.
    # The camelCase keys above work when the API returns a reason string, but
    # sometimes only an English error message is available.
    message_patterns: list[tuple[str, str]] = [
        ("permission", "permission_denied"),
        ("insufficient", "permission_denied"),
        ("rate limit", "rate_limited"),
        ("quota", "quota_exceeded"),
        ("not found", "file_not_found"),
    ]
    for pattern, error_code in message_patterns:
        if pattern in msg_lower:
            return error_code

    if isinstance(status_or_code, int):
        return f"http_{status_or_code}"
    return code_str
