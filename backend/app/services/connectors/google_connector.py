"""
Google Connector

Provides integration with Google APIs for:
- Drive: list, search, get, upload, download files
- Gmail: send, list, search, get emails
- Calendar: list, get, create, update, delete events
"""

import base64
import json
import logging
from email.mime.text import MIMEText
from typing import Any, Any

from .base import (
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)


class GoogleConnector(BaseConnector):
    """
    Google API connector for Drive, Gmail, and Calendar operations.

    Supports:
    - Google Drive: list, search, get, upload files and folders
    - Gmail: send, list, search, get emails
    - Google Calendar: list, get, create, update, delete events
    """

    CONNECTOR_TYPE = "google"

    # Google API quotas (per-user limits, conservative defaults)
    GOOGLE_RATE_LIMIT = RateLimitConfig(
        requests_per_second=5.0,
        requests_per_minute=200,
        requests_per_hour=10000,
        burst_size=15,
    )

    ACTIONS = [
        # Drive
        "drive_list_files",
        "drive_search_files",
        "drive_get_file",
        "drive_create_folder",
        "drive_upload_file",
        "drive_download_file",
        # Gmail
        "gmail_send",
        "gmail_list",
        "gmail_search",
        "gmail_get",
        # Calendar
        "calendar_list_events",
        "calendar_get_event",
        "calendar_create_event",
        "calendar_update_event",
        "calendar_delete_event",
    ]

    BASE_URLS = {
        "drive": "https://www.googleapis.com/drive/v3",
        "gmail": "https://gmail.googleapis.com/gmail/v1",
        "calendar": "https://www.googleapis.com/calendar/v3",
    }

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://www.googleapis.com"
        config.auth_type = config.auth_type or AuthType.OAUTH2
        config.rate_limit = config.rate_limit or self.GOOGLE_RATE_LIMIT
        config.headers = {
            **config.headers,
            "Accept": "application/json",
        }

        super().__init__(config)
        self._authenticated_email: str | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        """Validate Google token by calling the tokeninfo endpoint."""
        token = self.config.auth_config.get("access_token", "")
        if not token:
            return False

        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v1/tokeninfo",
                params={"access_token": token},
            )
            if resp.status_code == 200:
                data = resp.json()
                self._authenticated_email = data.get("email")
                return True

        return False

    # ── Utility ─────────────────────────────────────────────────────

    async def _execute_service_with_retry(
        self,
        method: str,
        endpoint: str,
        service: str = "drive",
        **kwargs,
    ) -> ConnectorResponse:
        """
        Execute a request against a Google service with full rate-limiting
        and retry logic from the base class.
        """
        prev_base = self.config.base_url
        self.config.base_url = self.BASE_URLS.get(service, self.BASE_URLS["drive"])
        try:
            return await self._execute_with_retry(method, endpoint, **kwargs)
        finally:
            self.config.base_url = prev_base

    async def execute_action(
        self,
        action: str,
        params: dict[str, Any],
    ) -> ConnectorResponse:
        """Execute a Google connector action."""

        action_handlers = {
            # Drive
            "drive_list_files": self._drive_list_files,
            "drive_search_files": self._drive_search_files,
            "drive_get_file": self._drive_get_file,
            "drive_create_folder": self._drive_create_folder,
            "drive_upload_file": self._drive_upload_file,
            "drive_download_file": self._drive_download_file,
            # Gmail
            "gmail_send": self._gmail_send,
            "gmail_list": self._gmail_list,
            "gmail_search": self._gmail_search,
            "gmail_get": self._gmail_get,
            # Calendar
            "calendar_list_events": self._calendar_list_events,
            "calendar_get_event": self._calendar_get_event,
            "calendar_create_event": self._calendar_create_event,
            "calendar_update_event": self._calendar_update_event,
            "calendar_delete_event": self._calendar_delete_event,
        }

        handler = action_handlers.get(action)
        if not handler:
            return ConnectorResponse(
                success=False,
                error=f"Unknown action: {action}",
                status_code=400,
            )

        return await handler(params)

    # ═══════════════════════════════════════════════════════════════
    #  Google Drive
    # ═══════════════════════════════════════════════════════════════

    async def _drive_list_files(self, params: dict[str, Any]) -> ConnectorResponse:
        """List files in Google Drive."""
        query_parts = ["trashed = false"]
        max_results = params.get("max_results", 100)
        page_token = None
        all_files: list[Any] = []

        if params.get("folder_id"):
            query_parts.append(f"'{params['folder_id']}' in parents")
        if params.get("mime_type"):
            query_parts.append(f"mimeType = '{params['mime_type']}'")

        while len(all_files) < max_results:
            query_params: dict[str, Any] = {
                "q": " and ".join(query_parts),
                "pageSize": min(100, max_results - len(all_files)),
                "fields": "nextPageToken, files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink)",
                "orderBy": params.get("order_by", "modifiedTime desc"),
            }
            if page_token:
                query_params["pageToken"] = page_token

            response = await self._execute_service_with_retry(
                "GET",
                "files",
                service="drive",
                params=query_params,
            )

            if not response.success:
                return response

            files = response.data.get("files", [])
            all_files.extend(files)

            page_token = response.data.get("nextPageToken")
            if not page_token:
                break

        return ConnectorResponse(
            success=True,
            data={"files": all_files, "total": len(all_files)},
            status_code=200,
        )

    async def _drive_search_files(self, params: dict[str, Any]) -> ConnectorResponse:
        """Search files by name in Google Drive."""
        query = params.get("query") or params.get("q")
        if not query:
            return ConnectorResponse(
                success=False,
                error="Missing required param: query",
                status_code=400,
            )

        query_parts = ["trashed = false", f"name contains '{query}'"]
        if params.get("mime_type"):
            query_parts.append(f"mimeType = '{params['mime_type']}'")

        query_params: dict[str, Any] = {
            "q": " and ".join(query_parts),
            "pageSize": params.get("max_results", 30),
            "fields": "files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink)",
            "orderBy": "modifiedTime desc",
        }

        return await self._execute_service_with_retry(
            "GET",
            "files",
            service="drive",
            params=query_params,
        )

    async def _drive_get_file(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get file metadata by ID."""
        file_id = params.get("file_id")
        if not file_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: file_id",
                status_code=400,
            )

        fields = params.get(
            "fields",
            "id, name, mimeType, size, createdTime, modifiedTime, webViewLink, parents",
        )

        return await self._execute_service_with_retry(
            "GET",
            f"files/{file_id}",
            service="drive",
            params={"fields": fields},
        )

    async def _drive_create_folder(self, params: dict[str, Any]) -> ConnectorResponse:
        """Create a folder in Google Drive."""
        name = params.get("name")
        if not name:
            return ConnectorResponse(
                success=False,
                error="Missing required param: name",
                status_code=400,
            )

        metadata: dict[str, Any] = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if params.get("parent_id"):
            metadata["parents"] = [params["parent_id"]]

        return await self._execute_service_with_retry(
            "POST",
            "files",
            service="drive",
            params={"fields": "id, name, mimeType, createdTime, webViewLink"},
            json_data=metadata,
        )

    async def _drive_upload_file(self, params: dict[str, Any]) -> ConnectorResponse:
        """Upload a file to Google Drive (small files via multipart)."""
        name = params.get("name")
        content = params.get("content")
        mime_type = params.get("mime_type", "application/octet-stream")

        if not all([name, content]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: name and content",
                status_code=400,
            )

        # Multipart upload boundary
        boundary = "google_connector_boundary"
        metadata = {"name": name}
        if params.get("parent_id"):
            metadata["parents"] = [params["parent_id"]]

        body = (
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {mime_type}\r\n"
            f"Content-Transfer-Encoding: base64\r\n\r\n"
            f"{base64.b64encode(content.encode() if isinstance(content, str) else content).decode()}\r\n"
            f"--{boundary}--"
        )

        headers = {
            "Content-Type": f"multipart/related; boundary={boundary}",
        }

        return await self._execute_service_with_retry(
            "POST",
            "files",
            service="drive",
            params={
                "uploadType": "multipart",
                "fields": "id, name, mimeType, size, webViewLink",
            },
            data=body,
            headers=headers,
        )

    async def _drive_download_file(self, params: dict[str, Any]) -> ConnectorResponse:
        """Download file content from Google Drive."""
        file_id = params.get("file_id")
        if not file_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: file_id",
                status_code=400,
            )

        # First get metadata to check mimeType
        meta = await self._drive_get_file({"file_id": file_id})
        if not meta.success:
            return meta

        mime_type = meta.data.get("mimeType", "")

        # For Google Docs/Sheets/Slides, export as appropriate format
        export_mime = None
        if mime_type.startswith("application/vnd.google-apps."):
            export_map = {
                "document": "text/plain",
                "spreadsheet": "text/csv",
                "presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            }
            for doc_type, exp_mime in export_map.items():
                if doc_type in mime_type:
                    export_mime = exp_mime
                    break

        if export_mime:
            return await self._execute_service_with_retry(
                "GET",
                f"files/{file_id}/export",
                service="drive",
                params={"mimeType": export_mime},
            )

        # Binary download
        return await self._execute_service_with_retry(
            "GET",
            f"files/{file_id}",
            service="drive",
            params={"alt": "media"},
        )

    # ═══════════════════════════════════════════════════════════════
    #  Gmail
    # ═══════════════════════════════════════════════════════════════

    async def _gmail_send(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send an email via Gmail."""
        to = params.get("to")
        subject = params.get("subject")
        body = params.get("body")

        if not all([to, subject, body]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: to, subject, and body",
                status_code=400,
            )

        # Build RFC 2822 message
        message = MIMEText(body, params.get("content_type", "plain"))
        message["to"] = to
        message["subject"] = subject
        if params.get("cc"):
            message["cc"] = params["cc"]
        if params.get("bcc"):
            message["bcc"] = params["bcc"]

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        return await self._execute_service_with_retry(
            "POST",
            "users/me/messages/send",
            service="gmail",
            json_data={"raw": raw},
        )

    async def _gmail_list(self, params: dict[str, Any]) -> ConnectorResponse:
        """List emails from Gmail inbox."""
        max_results = params.get("max_results", 20)

        query_params: dict[str, Any] = {
            "maxResults": min(max_results, 500),
            "labelIds": params.get("label_ids", ["INBOX"]),
        }
        if params.get("q"):
            query_params["q"] = params["q"]
        if params.get("page_token"):
            query_params["pageToken"] = params["page_token"]

        # First, list message IDs
        list_response = await self._execute_service_with_retry(
            "GET",
            "users/me/messages",
            service="gmail",
            params=query_params,
        )

        if not list_response.success:
            return list_response

        messages = list_response.data.get("messages", [])

        # Optionally fetch full message details
        if params.get("include_details", True) and messages:
            detailed = []
            for msg in messages[:max_results]:
                detail = await self._gmail_get({"message_id": msg["id"]})
                if detail.success:
                    detailed.append(detail.data)
                else:
                    detailed.append(msg)
            return ConnectorResponse(
                success=True,
                data={
                    "messages": detailed,
                    "next_page_token": list_response.data.get("nextPageToken"),
                    "result_size_estimate": list_response.data.get(
                        "resultSizeEstimate"
                    ),
                },
                status_code=200,
            )

        return list_response

    async def _gmail_search(self, params: dict[str, Any]) -> ConnectorResponse:
        """Search emails in Gmail."""
        q = params.get("q") or params.get("query")
        if not q:
            return ConnectorResponse(
                success=False,
                error="Missing required param: q (search query)",
                status_code=400,
            )

        return await self._gmail_list(
            {
                "q": q,
                "max_results": params.get("max_results", 20),
                "include_details": params.get("include_details", True),
            }
        )

    async def _gmail_get(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get a specific email by ID."""
        message_id = params.get("message_id")
        if not message_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: message_id",
                status_code=400,
            )

        fmt = params.get("format", "full")

        return await self._execute_service_with_retry(
            "GET",
            f"users/me/messages/{message_id}",
            service="gmail",
            params={"format": fmt},
        )

    # ═══════════════════════════════════════════════════════════════
    #  Google Calendar
    # ═══════════════════════════════════════════════════════════════

    async def _calendar_list_events(self, params: dict[str, Any]) -> ConnectorResponse:
        """List events from Google Calendar."""
        calendar_id = params.get("calendar_id", "primary")
        max_results = params.get("max_results", 50)

        query_params: dict[str, Any] = {
            "maxResults": min(max_results, 2500),
            "singleEvents": params.get("single_events", True),
            "orderBy": params.get("order_by", "startTime"),
        }
        if params.get("time_min"):
            query_params["timeMin"] = params["time_min"]
        if params.get("time_max"):
            query_params["timeMax"] = params["time_max"]
        if params.get("q"):
            query_params["q"] = params["q"]
        if params.get("page_token"):
            query_params["pageToken"] = params["page_token"]

        return await self._execute_service_with_retry(
            "GET",
            f"calendars/{calendar_id}/events",
            service="calendar",
            params=query_params,
        )

    async def _calendar_get_event(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get a specific calendar event."""
        calendar_id = params.get("calendar_id", "primary")
        event_id = params.get("event_id")

        if not event_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: event_id",
                status_code=400,
            )

        return await self._execute_service_with_retry(
            "GET",
            f"calendars/{calendar_id}/events/{event_id}",
            service="calendar",
        )

    async def _calendar_create_event(self, params: dict[str, Any]) -> ConnectorResponse:
        """Create a calendar event."""
        calendar_id = params.get("calendar_id", "primary")
        summary = params.get("summary")

        if not summary:
            return ConnectorResponse(
                success=False,
                error="Missing required param: summary",
                status_code=400,
            )

        event: dict[str, Any] = {"summary": summary}

        if params.get("description"):
            event["description"] = params["description"]
        if params.get("location"):
            event["location"] = params["location"]

        # Start/end times
        start = params.get("start")
        end = params.get("end")

        if start:
            if "dateTime" in start:
                event["start"] = {
                    "dateTime": start["dateTime"],
                    "timeZone": start.get("timeZone", "UTC"),
                }
            elif "date" in start:
                event["start"] = {"date": start["date"]}
        if end:
            if "dateTime" in end:
                event["end"] = {
                    "dateTime": end["dateTime"],
                    "timeZone": end.get("timeZone", "UTC"),
                }
            elif "date" in end:
                event["end"] = {"date": end["date"]}

        if params.get("attendees"):
            event["attendees"] = [{"email": e} for e in params["attendees"]]
        if params.get("reminders"):
            event["reminders"] = params["reminders"]

        return await self._execute_service_with_retry(
            "POST",
            f"calendars/{calendar_id}/events",
            service="calendar",
            json_data=event,
        )

    async def _calendar_update_event(self, params: dict[str, Any]) -> ConnectorResponse:
        """Update an existing calendar event."""
        calendar_id = params.get("calendar_id", "primary")
        event_id = params.get("event_id")

        if not event_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: event_id",
                status_code=400,
            )

        event: dict[str, Any] = {}
        for field in (
            "summary",
            "description",
            "location",
            "start",
            "end",
            "attendees",
            "reminders",
        ):
            if field in params:
                event[field] = params[field]

        return await self._execute_service_with_retry(
            "PATCH",
            f"calendars/{calendar_id}/events/{event_id}",
            service="calendar",
            json_data=event,
        )

    async def _calendar_delete_event(self, params: dict[str, Any]) -> ConnectorResponse:
        """Delete a calendar event."""
        calendar_id = params.get("calendar_id", "primary")
        event_id = params.get("event_id")

        if not event_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: event_id",
                status_code=400,
            )

        return await self._execute_service_with_retry(
            "DELETE",
            f"calendars/{calendar_id}/events/{event_id}",
            service="calendar",
        )

    def get_stats(self) -> dict[str, Any]:
        """Get connector statistics including Google-specific info."""
        stats = super().get_stats()
        stats.update({"authenticated_email": self._authenticated_email})
        return stats
