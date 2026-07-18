"""
Email Connector

Provides integration with email services via SMTP/IMAP for:
- Sending emails (SMTP)
- Reading emails (IMAP)
- Managing folders
- Email search and filtering
"""

import asyncio
import contextlib
import email
import imaplib
import logging
import smtplib
from email import encoders
from email.header import decode_header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from .base import (
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    ConnectorStatus,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)


class EmailConnector(BaseConnector):
    """
    Email connector for SMTP/IMAP operations.

    Supports:
    - Sending emails via SMTP
    - Reading emails via IMAP
    - Managing folders
    - Searching and filtering
    """

    CONNECTOR_TYPE = "email"

    # Email rate limits (conservative)
    EMAIL_RATE_LIMIT = RateLimitConfig(
        requests_per_second=2.0,
        requests_per_minute=60,
        requests_per_hour=500,
        burst_size=10,
    )

    ACTIONS = [
        "send_email",
        "send_email_with_attachment",
        "list_emails",
        "get_email",
        "search_emails",
        "delete_email",
        "move_email",
        "mark_read",
        "mark_unread",
        "list_folders",
        "create_folder",
        "delete_folder",
        "get_unread_count",
    ]

    def __init__(self, config: ConnectorConfig):
        config.auth_type = config.auth_type or AuthType.BASIC_AUTH
        config.rate_limit = config.rate_limit or self.EMAIL_RATE_LIMIT

        super().__init__(config)

        # SMTP/IMAP configuration from auth_config
        self._smtp_host = config.auth_config.get("smtp_host", "smtp.gmail.com")
        self._smtp_port = config.auth_config.get("smtp_port", 587)
        self._imap_host = config.auth_config.get("imap_host", "imap.gmail.com")
        self._imap_port = config.auth_config.get("imap_port", 993)
        self._use_ssl = config.auth_config.get("use_ssl", True)
        self._use_tls = config.auth_config.get("use_tls", True)
        self._username = config.auth_config.get("username", "")
        self._password = config.auth_config.get("password", "")

        self._smtp_connection: smtplib.SMTP | None = None
        self._imap_connection: imaplib.IMAP4_SSL | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def connect(self) -> bool:
        """Initialize SMTP and IMAP connections"""
        try:
            # Test SMTP connection
            loop = asyncio.get_event_loop()

            def _connect_smtp():
                if self._use_ssl:
                    smtp = smtplib.SMTP_SSL(self._smtp_host, self._smtp_port)
                else:
                    smtp = smtplib.SMTP(self._smtp_host, self._smtp_port)
                    if self._use_tls:
                        smtp.starttls()
                smtp.login(self._username, self._password)
                return smtp

            self._smtp_connection = await loop.run_in_executor(None, _connect_smtp)

            # Test IMAP connection
            def _connect_imap():
                imap = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
                imap.login(self._username, self._password)
                return imap

            self._imap_connection = await loop.run_in_executor(None, _connect_imap)

            self._status = ConnectorStatus.ACTIVE
            return True

        except Exception as e:
            self._last_error = str(e)
            self._status = ConnectorStatus.ERROR
            logger.error("Failed to connect email: %s", e)
            return False

    async def disconnect(self) -> None:
        """Close SMTP and IMAP connections"""
        loop = asyncio.get_event_loop()

        if self._smtp_connection:
            with contextlib.suppress(Exception):
                await loop.run_in_executor(None, self._smtp_connection.quit)
            self._smtp_connection = None

        if self._imap_connection:
            with contextlib.suppress(Exception):
                await loop.run_in_executor(None, self._imap_connection.logout)
            self._imap_connection = None

        self._status = ConnectorStatus.INACTIVE

    async def _validate_credentials(self) -> bool:
        """Validate email credentials by testing connection"""
        return self._smtp_connection is not None and self._imap_connection is not None

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        """Execute an email action"""

        action_handlers = {
            "send_email": self._send_email,
            "send_email_with_attachment": self._send_email_with_attachment,
            "list_emails": self._list_emails,
            "get_email": self._get_email,
            "search_emails": self._search_emails,
            "delete_email": self._delete_email,
            "move_email": self._move_email,
            "mark_read": self._mark_read,
            "mark_unread": self._mark_unread,
            "list_folders": self._list_folders,
            "create_folder": self._create_folder,
            "delete_folder": self._delete_folder,
            "get_unread_count": self._get_unread_count,
        }

        handler = action_handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)

        return await handler(params)

    def _decode_header_value(self, value: str) -> str:
        """Decode email header value"""
        if not value:
            return ""

        decoded_parts = decode_header(value)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                result.append(part)
        return "".join(result)

    def _parse_email_message(self, msg: email.message.Message) -> dict[str, Any]:
        """Parse email message into dictionary"""
        result = {
            "subject": self._decode_header_value(msg.get("Subject", "")),
            "from": self._decode_header_value(msg.get("From", "")),
            "to": self._decode_header_value(msg.get("To", "")),
            "cc": self._decode_header_value(msg.get("Cc", "")),
            "date": msg.get("Date", ""),
            "message_id": msg.get("Message-ID", ""),
            "body": "",
            "html": "",
            "attachments": [],
        }

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    # Handle attachment
                    filename = part.get_filename()
                    if filename:
                        result["attachments"].append(  # type: ignore[attr-defined]
                            {
                                "filename": self._decode_header_value(filename),
                                "content_type": content_type,
                                "size": len(part.get_payload(decode=True) or b""),
                            }
                        )
                elif content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        result["body"] += payload.decode("utf-8", errors="replace")  # type: ignore[operator,union-attr]
                elif content_type == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        result["html"] += payload.decode("utf-8", errors="replace")  # type: ignore[operator,union-attr]
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                content_type = msg.get_content_type()
                if content_type == "text/html":
                    result["html"] = payload.decode("utf-8", errors="replace")  # type: ignore[union-attr]
                else:
                    result["body"] = payload.decode("utf-8", errors="replace")  # type: ignore[union-attr]

        return result

    async def _send_email(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send an email"""
        to = params.get("to")
        subject = params.get("subject", "")
        body = params.get("body", "")
        html = params.get("html")
        cc = params.get("cc")
        bcc = params.get("bcc")
        reply_to = params.get("reply_to")

        if not to:
            return ConnectorResponse(success=False, error="Missing required param: to", status_code=400)

        try:
            loop = asyncio.get_event_loop()

            def _send():
                if html:
                    msg = MIMEMultipart("alternative")
                    msg.attach(MIMEText(body, "plain"))
                    msg.attach(MIMEText(html, "html"))
                else:
                    msg = MIMEText(body)

                msg["Subject"] = subject
                msg["From"] = self._username
                msg["To"] = to if isinstance(to, str) else ", ".join(to)

                if cc:
                    msg["Cc"] = cc if isinstance(cc, str) else ", ".join(cc)
                if bcc:
                    msg["Bcc"] = bcc if isinstance(bcc, str) else ", ".join(bcc)
                if reply_to:
                    msg["Reply-To"] = reply_to

                recipients = [to] if isinstance(to, str) else to
                if cc:
                    recipients.extend([cc] if isinstance(cc, str) else cc)
                if bcc:
                    recipients.extend([bcc] if isinstance(bcc, str) else bcc)

                if not self._smtp_connection:
                    raise Exception("SMTP not connected")

                self._smtp_connection.sendmail(self._username, recipients, msg.as_string())
                return True

            await loop.run_in_executor(None, _send)

            return ConnectorResponse(
                success=True,
                data={"message": "Email sent successfully", "to": to},
                status_code=200,
            )

        except Exception as e:
            logger.error("Failed to send email: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _send_email_with_attachment(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send an email with attachments"""
        to = params.get("to")
        subject = params.get("subject", "")
        body = params.get("body", "")
        html = params.get("html")
        attachments = params.get("attachments", [])  # List of {filename, content, content_type}

        if not to:
            return ConnectorResponse(success=False, error="Missing required param: to", status_code=400)

        try:
            loop = asyncio.get_event_loop()

            def _send():
                msg = MIMEMultipart()
                msg["Subject"] = subject
                msg["From"] = self._username
                msg["To"] = to if isinstance(to, str) else ", ".join(to)

                # Attach body
                if html:
                    msg.attach(MIMEText(body, "plain"))
                    msg.attach(MIMEText(html, "html"))
                else:
                    msg.attach(MIMEText(body))

                # Attach files
                for attachment in attachments:
                    filename = attachment.get("filename", "attachment")
                    content = attachment.get("content", "")
                    content_type = attachment.get("content_type", "application/octet-stream")

                    if isinstance(content, str):
                        content = content.encode()

                    part = MIMEBase(*content_type.split("/", 1))
                    part.set_payload(content)
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                    msg.attach(part)

                if not self._smtp_connection:
                    raise Exception("SMTP not connected")

                recipients = [to] if isinstance(to, str) else to
                self._smtp_connection.sendmail(self._username, recipients, msg.as_string())
                return True

            await loop.run_in_executor(None, _send)

            return ConnectorResponse(
                success=True,
                data={"message": "Email with attachments sent successfully", "to": to},
                status_code=200,
            )

        except Exception as e:
            logger.error("Failed to send email with attachment: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _list_emails(self, params: dict[str, Any]) -> ConnectorResponse:
        """List emails from a folder"""
        folder = params.get("folder", "INBOX")
        limit = params.get("limit", 50)
        offset = params.get("offset", 0)

        try:
            loop = asyncio.get_event_loop()

            def _list():
                if not self._imap_connection:
                    raise Exception("IMAP not connected")

                self._imap_connection.select(folder)
                status, messages = self._imap_connection.search(None, "ALL")

                if status != "OK":
                    return []

                email_ids = messages[0].split()
                email_ids = email_ids[::-1]  # Most recent first

                results = []
                for email_id in email_ids[offset : offset + limit]:
                    status, msg_data = self._imap_connection.fetch(email_id, "(RFC822.HEADER)")
                    if status == "OK":
                        raw_email = msg_data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        results.append(
                            {
                                "id": email_id.decode(),
                                "subject": self._decode_header_value(msg.get("Subject", "")),
                                "from": self._decode_header_value(msg.get("From", "")),
                                "date": msg.get("Date", ""),
                                "unread": "\\Seen" not in str(msg.get("Flags", "")),
                            }
                        )

                return results

            results = await loop.run_in_executor(None, _list)

            return ConnectorResponse(
                success=True,
                data={"emails": results, "folder": folder, "count": len(results)},
                status_code=200,
            )

        except Exception as e:
            logger.error("Failed to list emails: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_email(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get a specific email"""
        email_id = params.get("email_id")
        folder = params.get("folder", "INBOX")

        if not email_id:
            return ConnectorResponse(success=False, error="Missing required param: email_id", status_code=400)

        try:
            loop = asyncio.get_event_loop()

            def _get():
                if not self._imap_connection:
                    raise Exception("IMAP not connected")

                self._imap_connection.select(folder)
                status, msg_data = self._imap_connection.fetch(email_id.encode(), "(RFC822)")

                if status != "OK":
                    return None

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                return self._parse_email_message(msg)

            result = await loop.run_in_executor(None, _get)

            if result:
                return ConnectorResponse(success=True, data=result, status_code=200)
            else:
                return ConnectorResponse(success=False, error="Email not found", status_code=404)

        except Exception as e:
            logger.error("Failed to get email: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _search_emails(self, params: dict[str, Any]) -> ConnectorResponse:
        """Search emails"""
        folder = params.get("folder", "INBOX")
        query = params.get("query", "")
        from_email = params.get("from")
        to_email = params.get("to")
        subject = params.get("subject")
        since = params.get("since")  # Date string
        before = params.get("before")  # Date string
        unread_only = params.get("unread_only", False)
        limit = params.get("limit", 50)

        try:
            loop = asyncio.get_event_loop()

            def _search():
                if not self._imap_connection:
                    raise Exception("IMAP not connected")

                self._imap_connection.select(folder)

                # Build search criteria
                criteria = []
                if query:
                    criteria.append(f'BODY "{query}"')
                if from_email:
                    criteria.append(f'FROM "{from_email}"')
                if to_email:
                    criteria.append(f'TO "{to_email}"')
                if subject:
                    criteria.append(f'SUBJECT "{subject}"')
                if since:
                    criteria.append(f"SINCE {since}")
                if before:
                    criteria.append(f"BEFORE {before}")
                if unread_only:
                    criteria.append("UNSEEN")

                search_query = " ".join(criteria) if criteria else "ALL"

                status, messages = self._imap_connection.search(None, search_query)

                if status != "OK":
                    return []

                email_ids = messages[0].split()
                email_ids = email_ids[::-1][:limit]

                results = []
                for email_id in email_ids:
                    status, msg_data = self._imap_connection.fetch(email_id, "(RFC822.HEADER)")
                    if status == "OK":
                        raw_email = msg_data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        results.append(
                            {
                                "id": email_id.decode(),
                                "subject": self._decode_header_value(msg.get("Subject", "")),
                                "from": self._decode_header_value(msg.get("From", "")),
                                "date": msg.get("Date", ""),
                            }
                        )

                return results

            results = await loop.run_in_executor(None, _search)

            return ConnectorResponse(
                success=True,
                data={"emails": results, "count": len(results)},
                status_code=200,
            )

        except Exception as e:
            logger.error("Failed to search emails: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _delete_email(self, params: dict[str, Any]) -> ConnectorResponse:
        """Delete an email"""
        email_id = params.get("email_id")
        folder = params.get("folder", "INBOX")

        if not email_id:
            return ConnectorResponse(success=False, error="Missing required param: email_id", status_code=400)

        try:
            loop = asyncio.get_event_loop()

            def _delete():
                if not self._imap_connection:
                    raise Exception("IMAP not connected")

                self._imap_connection.select(folder)
                self._imap_connection.store(email_id.encode(), "+FLAGS", "\\Deleted")
                self._imap_connection.expunge()
                return True

            await loop.run_in_executor(None, _delete)

            return ConnectorResponse(success=True, data={"message": "Email deleted"}, status_code=200)

        except Exception as e:
            logger.error("Failed to delete email: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _move_email(self, params: dict[str, Any]) -> ConnectorResponse:
        """Move an email to another folder"""
        email_id = params.get("email_id")
        source_folder = params.get("source_folder", "INBOX")
        dest_folder = params.get("dest_folder")

        if not email_id or not dest_folder:
            return ConnectorResponse(
                success=False,
                error="Missing required params: email_id and dest_folder",
                status_code=400,
            )

        try:
            loop = asyncio.get_event_loop()

            def _move():
                if not self._imap_connection:
                    raise Exception("IMAP not connected")

                self._imap_connection.select(source_folder)
                self._imap_connection.copy(email_id.encode(), dest_folder)
                self._imap_connection.store(email_id.encode(), "+FLAGS", "\\Deleted")
                self._imap_connection.expunge()
                return True

            await loop.run_in_executor(None, _move)

            return ConnectorResponse(
                success=True,
                data={"message": f"Email moved to {dest_folder}"},
                status_code=200,
            )

        except Exception as e:
            logger.error("Failed to move email: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _mark_read(self, params: dict[str, Any]) -> ConnectorResponse:
        """Mark an email as read"""
        email_id = params.get("email_id")
        folder = params.get("folder", "INBOX")

        if not email_id:
            return ConnectorResponse(success=False, error="Missing required param: email_id", status_code=400)

        try:
            loop = asyncio.get_event_loop()

            def _mark():
                if not self._imap_connection:
                    raise Exception("IMAP not connected")

                self._imap_connection.select(folder)
                self._imap_connection.store(email_id.encode(), "+FLAGS", "\\Seen")
                return True

            await loop.run_in_executor(None, _mark)

            return ConnectorResponse(success=True, data={"message": "Email marked as read"}, status_code=200)

        except Exception as e:
            logger.error("Failed to mark email as read: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _mark_unread(self, params: dict[str, Any]) -> ConnectorResponse:
        """Mark an email as unread"""
        email_id = params.get("email_id")
        folder = params.get("folder", "INBOX")

        if not email_id:
            return ConnectorResponse(success=False, error="Missing required param: email_id", status_code=400)

        try:
            loop = asyncio.get_event_loop()

            def _mark():
                if not self._imap_connection:
                    raise Exception("IMAP not connected")

                self._imap_connection.select(folder)
                self._imap_connection.store(email_id.encode(), "-FLAGS", "\\Seen")
                return True

            await loop.run_in_executor(None, _mark)

            return ConnectorResponse(
                success=True,
                data={"message": "Email marked as unread"},
                status_code=200,
            )

        except Exception as e:
            logger.error("Failed to mark email as unread: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _list_folders(self, params: dict[str, Any]) -> ConnectorResponse:
        """List all folders"""
        try:
            loop = asyncio.get_event_loop()

            def _list():
                if not self._imap_connection:
                    raise Exception("IMAP not connected")

                status, folders = self._imap_connection.list()

                if status != "OK":
                    return []

                result = []
                for folder in folders:
                    if folder:
                        parts = folder.decode().split('"/')
                        if len(parts) >= 3:
                            result.append(
                                {
                                    "name": parts[-1].strip('"'),
                                    "flags": parts[0].strip(),
                                }
                            )

                return result

            results = await loop.run_in_executor(None, _list)

            return ConnectorResponse(success=True, data={"folders": results}, status_code=200)

        except Exception as e:
            logger.error("Failed to list folders: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _create_folder(self, params: dict[str, Any]) -> ConnectorResponse:
        """Create a new folder"""
        folder_name = params.get("name")

        if not folder_name:
            return ConnectorResponse(success=False, error="Missing required param: name", status_code=400)

        try:
            loop = asyncio.get_event_loop()

            def _create():
                if not self._imap_connection:
                    raise Exception("IMAP not connected")

                self._imap_connection.create(folder_name)
                return True

            await loop.run_in_executor(None, _create)

            return ConnectorResponse(
                success=True,
                data={"message": f"Folder '{folder_name}' created"},
                status_code=200,
            )

        except Exception as e:
            logger.error("Failed to create folder: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _delete_folder(self, params: dict[str, Any]) -> ConnectorResponse:
        """Delete a folder"""
        folder_name = params.get("name")

        if not folder_name:
            return ConnectorResponse(success=False, error="Missing required param: name", status_code=400)

        try:
            loop = asyncio.get_event_loop()

            def _delete():
                if not self._imap_connection:
                    raise Exception("IMAP not connected")

                self._imap_connection.delete(folder_name)
                return True

            await loop.run_in_executor(None, _delete)

            return ConnectorResponse(
                success=True,
                data={"message": f"Folder '{folder_name}' deleted"},
                status_code=200,
            )

        except Exception as e:
            logger.error("Failed to delete folder: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_unread_count(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get count of unread emails"""
        folder = params.get("folder", "INBOX")

        try:
            loop = asyncio.get_event_loop()

            def _count():
                if not self._imap_connection:
                    raise Exception("IMAP not connected")

                self._imap_connection.select(folder)
                status, messages = self._imap_connection.search(None, "UNSEEN")

                if status != "OK":
                    return 0

                return len(messages[0].split())

            count = await loop.run_in_executor(None, _count)

            return ConnectorResponse(
                success=True,
                data={"unread_count": count, "folder": folder},
                status_code=200,
            )

        except Exception as e:
            logger.error("Failed to get unread count: %s", e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    def get_stats(self) -> dict[str, Any]:
        """Get connector statistics"""
        stats = super().get_stats()
        stats.update(
            {
                "smtp_host": self._smtp_host,
                "imap_host": self._imap_host,
                "username": self._username,
            }
        )
        return stats
