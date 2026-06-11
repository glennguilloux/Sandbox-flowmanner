"""
API & SaaS Integration Tools — Google Workspace Hub.

google_workspace_hub → Unified access to Gmail, Calendar, and Drive resources.
"""

from __future__ import annotations

import base64
import logging
import os
from email.mime.text import MIMEText

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class GoogleWorkspaceHubInput(ToolInput):
    action: str = Field(
        ...,
        description="Action: 'list_emails', 'get_email', 'send_email', "
        "'list_events', 'create_event', 'list_files', 'search_drive'",
    )
    # Email fields
    to: str | None = Field(None, description="Recipient email address")
    subject: str | None = Field(None, description="Email subject")
    body: str | None = Field(None, description="Email body text")
    email_id: str | None = Field(None, description="Gmail message ID")
    query: str | None = Field(None, description="Gmail search query or Drive search query")
    # Calendar fields
    calendar_id: str = Field("primary", description="Calendar ID (default: 'primary')")
    event_summary: str | None = Field(None, description="Event title/summary")
    event_start: str | None = Field(None, description="Start date/time (ISO 8601)")
    event_end: str | None = Field(None, description="End date/time (ISO 8601)")
    event_description: str | None = Field(None, description="Event description")
    # Drive fields
    file_id: str | None = Field(None, description="Drive file ID")
    mime_type: str | None = Field(None, description="MIME type filter for Drive search")
    # Common
    max_results: int = Field(20, ge=1, le=100)
    credentials_json: str | None = Field(
        None, description="Google service account JSON or OAuth credentials JSON string"
    )


class GoogleWorkspaceHubTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="google_workspace_hub",
            name="Google Workspace Hub",
            description="Unified access to Gmail, Calendar, and Drive resources",
            category="api-integrations",
            input_schema=GoogleWorkspaceHubInput.schema_extra(),
            tags=["google", "gmail", "calendar", "drive", "workspace", "integration"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def _get_access_token(self, credentials_json: str | None) -> str:
        """Get an OAuth2 access token from service account or refresh token."""
        import json
        import time

        # Try service account
        creds_str = credentials_json or os.getenv("GOOGLE_CREDENTIALS", "")
        if not creds_str:
            raise ValueError("No Google credentials. Set GOOGLE_CREDENTIALS or pass credentials_json.")

        creds = json.loads(creds_str)

        # Service account JWT
        if "client_email" in creds and "private_key" in creds:
            import jwt as pyjwt

            now = int(time.time())
            payload = {
                "iss": creds["client_email"],
                "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/drive.readonly",
                "aud": "https://oauth2.googleapis.com/token",
                "exp": now + 3600,
                "iat": now,
            }
            assertion = pyjwt.encode(payload, creds["private_key"], algorithm="RS256")

            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                        "assertion": assertion,
                    },
                )
                if r.status_code != 200:
                    raise ValueError(f"Failed to get access token: {r.text}")
                return r.json()["access_token"]

        # User OAuth refresh token
        if "refresh_token" in creds:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": creds.get("client_id", os.getenv("GOOGLE_CLIENT_ID", "")),
                        "client_secret": creds.get("client_secret", os.getenv("GOOGLE_CLIENT_SECRET", "")),
                        "refresh_token": creds["refresh_token"],
                        "grant_type": "refresh_token",
                    },
                )
                if r.status_code != 200:
                    raise ValueError(f"Failed to refresh token: {r.text}")
                return r.json()["access_token"]

        raise ValueError("Invalid credentials format. Need service account JSON or OAuth refresh_token.")

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = GoogleWorkspaceHubInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        try:
            access_token = await self._get_access_token(validated.credentials_json)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Auth failed: {e}")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        action = validated.action.lower().strip()

        try:
            async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
                if action == "list_emails":
                    return await self._list_emails(client, validated)
                elif action == "get_email":
                    return await self._get_email(client, validated)
                elif action == "send_email":
                    return await self._send_email(client, validated)
                elif action == "list_events":
                    return await self._list_events(client, validated)
                elif action == "create_event":
                    return await self._create_event(client, validated)
                elif action == "list_files":
                    return await self._list_files(client, validated)
                elif action == "search_drive":
                    return await self._search_drive(client, validated)
                else:
                    return ToolResult.error_result(tool_id=self.tool_id, error=f"Unknown action: {action}")
        except Exception as e:
            logger.exception("google_workspace_hub failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _list_emails(self, client: httpx.AsyncClient, v) -> ToolResult:
        params: dict = {"maxResults": v.max_results}
        if v.query:
            params["q"] = v.query
        r = await client.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", params=params)
        if r.status_code != 200:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Gmail API error: {r.status_code}")
        data = r.json()
        messages = data.get("messages", [])
        # Get details for each
        emails = []
        for msg in messages[: min(v.max_results, 10)]:
            detail = await client.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}")
            if detail.status_code == 200:
                d = detail.json()
                headers = {h["name"]: h["value"] for h in d.get("payload", {}).get("headers", [])}
                snippet = d.get("snippet", "")
                emails.append(
                    {
                        "id": d["id"],
                        "thread_id": d.get("threadId"),
                        "subject": headers.get("Subject", ""),
                        "from": headers.get("From", ""),
                        "date": headers.get("Date", ""),
                        "snippet": snippet,
                    }
                )
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "list_emails",
                "count": len(emails),
                "emails": emails,
            },
        )

    async def _get_email(self, client: httpx.AsyncClient, v) -> ToolResult:
        if not v.email_id:
            return ToolResult.error_result(tool_id=self.tool_id, error="email_id required")
        r = await client.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{v.email_id}",
            params={"format": "full"},
        )
        if r.status_code != 200:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Gmail API error: {r.status_code}")
        d = r.json()
        headers = {h["name"]: h["value"] for h in d.get("payload", {}).get("headers", [])}
        # Extract body
        body = ""
        parts = d.get("payload", {}).get("parts", [])
        if parts:
            for part in parts:
                if part.get("mimeType") == "text/plain":
                    body_data = part.get("body", {}).get("data", "")
                    if body_data:
                        body = base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")
        elif d.get("payload", {}).get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(d["payload"]["body"]["data"] + "==").decode("utf-8", errors="replace")
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "get_email",
                "id": d["id"],
                "subject": headers.get("Subject"),
                "from": headers.get("From"),
                "date": headers.get("Date"),
                "body": body[:5000],
            },
        )

    async def _send_email(self, client: httpx.AsyncClient, v) -> ToolResult:
        if not v.to or not v.subject or not v.body:
            return ToolResult.error_result(tool_id=self.tool_id, error="to, subject, and body required")
        msg = MIMEText(v.body)
        msg["to"] = v.to
        msg["subject"] = v.subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        r = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            json={"raw": raw},
        )
        if r.status_code != 200:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Gmail API error: {r.status_code} {r.text[:200]}",
            )
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={"action": "send_email", "ok": True, "id": r.json().get("id")},
        )

    async def _list_events(self, client: httpx.AsyncClient, v) -> ToolResult:
        r = await client.get(
            f"https://www.googleapis.com/calendar/v3/calendars/{v.calendar_id}/events",
            params={
                "maxResults": v.max_results,
                "orderBy": "startTime",
                "singleEvents": "true",
                "timeMin": v.event_start or "2024-01-01T00:00:00Z",
            },
        )
        if r.status_code != 200:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Calendar API error: {r.status_code}")
        data = r.json()
        events = [
            {
                "id": e["id"],
                "summary": e.get("summary"),
                "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date")),
                "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date")),
                "location": e.get("location"),
            }
            for e in data.get("items", [])
        ]
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={"action": "list_events", "count": len(events), "events": events},
        )

    async def _create_event(self, client: httpx.AsyncClient, v) -> ToolResult:
        if not v.event_summary or not v.event_start or not v.event_end:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="event_summary, event_start, and event_end required",
            )
        payload: dict = {
            "summary": v.event_summary,
            "start": {"dateTime": v.event_start},
            "end": {"dateTime": v.event_end},
        }
        if v.event_description:
            payload["description"] = v.event_description
        r = await client.post(
            f"https://www.googleapis.com/calendar/v3/calendars/{v.calendar_id}/events",
            json=payload,
        )
        if r.status_code != 200:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Calendar API error: {r.status_code} {r.text[:200]}",
            )
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={"action": "create_event", "ok": True, "id": r.json().get("id")},
        )

    async def _list_files(self, client: httpx.AsyncClient, v) -> ToolResult:
        params: dict = {
            "pageSize": v.max_results,
            "fields": "files(id,name,mimeType,size,webViewLink,modifiedTime)",
        }
        r = await client.get("https://www.googleapis.com/drive/v3/files", params=params)
        if r.status_code != 200:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Drive API error: {r.status_code}")
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={"action": "list_files", "files": r.json().get("files", [])},
        )

    async def _search_drive(self, client: httpx.AsyncClient, v) -> ToolResult:
        if not v.query:
            return ToolResult.error_result(tool_id=self.tool_id, error="query required")
        q_parts = [f"name contains '{v.query}'"]
        if v.mime_type:
            q_parts.append(f"mimeType='{v.mime_type}'")
        params = {
            "q": " and ".join(q_parts),
            "pageSize": v.max_results,
            "fields": "files(id,name,mimeType,size,webViewLink,modifiedTime)",
        }
        r = await client.get("https://www.googleapis.com/drive/v3/files", params=params)
        if r.status_code != 200:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Drive API error: {r.status_code}")
        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "search_drive",
                "query": v.query,
                "count": len(r.json().get("files", [])),
                "files": r.json().get("files", []),
            },
        )


register_tool(GoogleWorkspaceHubTool())
