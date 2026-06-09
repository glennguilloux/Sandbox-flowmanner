"""
AWS S3 Uploader — Agent-callable tool for S3 object operations.

aws_s3_uploader → upload, download, list, and manage S3 objects with presigned URLs.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

from pydantic import Field

from app.tools.base import (
    BaseTool,
    ToolInput,
    ToolMetadata,
    ToolResult,
    is_placeholder,
    register_tool,
)

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-1"))
DEFAULT_EXPIRES = int(os.getenv("S3_URL_EXPIRES", "3600"))


S3_ACTIONS: tuple[str, ...] = (
    "upload_file",
    "download_file",
    "list_objects",
    "generate_presigned_url",
    "delete_object",
    "get_bucket_info",
    "copy_object",
)


# ── Input ───────────────────────────────────────────────────────────


class AwsS3UploaderInput(ToolInput):
    action: str = Field(
        ...,
        description=(
            "S3 operation: 'upload_file', 'download_file', 'list_objects', "
            "'generate_presigned_url', 'delete_object', 'get_bucket_info', 'copy_object'"
        ),
    )
    bucket: str = Field(
        ...,
        description="S3 bucket name.",
    )
    key: str | None = Field(
        None,
        description="S3 object key (path) for the file within the bucket.",
    )
    data: str | None = Field(
        None,
        description="Base64-encoded file data for upload_file.",
    )
    destination_key: str | None = Field(
        None,
        description="Destination object key for copy_object.",
    )
    prefix: str | None = Field(
        None,
        description="Prefix filter for list_objects (e.g., 'images/').",
    )
    max_keys: int | None = Field(
        50,
        description="Maximum number of objects to return for list_objects (default: 50, max: 1000).",
    )
    expires: int | None = Field(
        DEFAULT_EXPIRES,
        description="Expiration time in seconds for presigned URLs (default: 3600).",
    )
    content_type: str | None = Field(
        None,
        description="MIME content type for upload_file (e.g., 'image/png').",
    )


# ── Tool ────────────────────────────────────────────────────────────


class AwsS3UploaderTool(BaseTool):
    """Upload, download, and manage S3 objects with presigned URL support."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="aws_s3_uploader",
            name="AWS S3 Uploader",
            description=(
                "Upload, download, list, and manage files in AWS S3 buckets. "
                "Supports presigned URL generation for secure temporary access. "
                "Requires AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and optionally "
                "AWS_DEFAULT_REGION env vars."
            ),
            category="developer-tools",
            input_schema=AwsS3UploaderInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "result": {"type": "object"},
                },
            },
            tags=["aws", "s3", "storage", "cloud", "developer"],
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = AwsS3UploaderInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(self.tool_id, f"Invalid input: {e}")

        if not AWS_ACCESS_KEY or not AWS_SECRET_KEY:
            return ToolResult.error_result(
                self.tool_id,
                "AWS credentials not configured. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY env vars.",
            )

        if is_placeholder(AWS_ACCESS_KEY) or is_placeholder(AWS_SECRET_KEY):
            return ToolResult.error_result(
                self.tool_id,
                "AWS credentials contain a placeholder. "
                "Replace placeholder in .env with real AWS_ACCESS_KEY_ID and "
                "AWS_SECRET_ACCESS_KEY values "
                "(from https://console.aws.amazon.com/iam → Users → Security credentials).",
            )

        if validated.action not in S3_ACTIONS:
            return ToolResult.error_result(
                self.tool_id,
                f"Unknown action '{validated.action}'. Use one of: {', '.join(S3_ACTIONS)}",
            )

        result = await self._execute_action(validated)
        return ToolResult.success_result(self.tool_id, result)

    # ── helpers ────────────────────────────────────────────────────

    def _get_client(self):
        """Get a boto3 S3 client (lazy import to avoid crash on missing boto3)."""
        import boto3

        return boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY,
            region_name=AWS_REGION,
        )

    async def _run_s3(self, func, *args, **kwargs) -> Any:
        """Run a synchronous boto3 call in a thread to avoid blocking the event loop."""
        import asyncio

        return await asyncio.to_thread(func, *args, **kwargs)

    def _summarize_object(self, obj: dict[str, Any]) -> dict[str, Any]:
        """Extract key fields from an S3 object descriptor."""
        return {
            "key": obj.get("Key"),
            "size": obj.get("Size"),
            "last_modified": str(obj.get("LastModified", "")),
            "etag": (obj.get("ETag", "") or "").strip('"'),
            "storage_class": obj.get("StorageClass", "STANDARD"),
        }

    # ── actions ────────────────────────────────────────────────────

    async def _execute_action(self, v: AwsS3UploaderInput) -> dict[str, Any]:
        action = v.action
        if action == "upload_file":
            return await self._upload_file(v)
        elif action == "download_file":
            return await self._download_file(v)
        elif action == "list_objects":
            return await self._list_objects(v)
        elif action == "generate_presigned_url":
            return await self._generate_url(v)
        elif action == "delete_object":
            return await self._delete_object(v)
        elif action == "get_bucket_info":
            return await self._get_bucket_info(v)
        elif action == "copy_object":
            return await self._copy_object(v)
        return {"error": f"Action '{action}' not implemented"}

    async def _upload_file(self, v: AwsS3UploaderInput) -> dict[str, Any]:
        if not v.key:
            return {"action": "upload_file", "error": "key is required for upload_file"}

        if not v.data:
            return {
                "action": "upload_file",
                "error": "data is required (base64-encoded file content)",
            }

        try:
            file_bytes = base64.b64decode(v.data)
        except Exception as e:
            return {"action": "upload_file", "error": f"Invalid base64 data: {e}"}

        extra_args: dict[str, Any] = {}
        if v.content_type:
            extra_args["ContentType"] = v.content_type

        try:
            s3 = self._get_client()
            await self._run_s3(
                s3.put_object,
                Bucket=v.bucket,
                Key=v.key,
                Body=file_bytes,
                **extra_args,
            )

            # Generate a presigned URL for immediate access
            url = await self._run_s3(
                s3.generate_presigned_url,
                "get_object",
                Params={"Bucket": v.bucket, "Key": v.key},
                ExpiresIn=v.expires or DEFAULT_EXPIRES,
            )

            return {
                "action": "upload_file",
                "bucket": v.bucket,
                "key": v.key,
                "size_bytes": len(file_bytes),
                "content_type": v.content_type,
                "presigned_url": url,
                "url_expires_seconds": v.expires or DEFAULT_EXPIRES,
            }

        except Exception as e:
            logger.exception("S3 upload failed: %s", e)
            return {"action": "upload_file", "error": f"S3 upload failed: {e}"}

    async def _download_file(self, v: AwsS3UploaderInput) -> dict[str, Any]:
        if not v.key:
            return {"action": "download_file", "error": "key is required"}

        try:
            s3 = self._get_client()
            resp = await self._run_s3(s3.get_object, Bucket=v.bucket, Key=v.key)
            body = await self._run_s3(resp["Body"].read)
            content_type = resp.get("ContentType", "application/octet-stream")
            data_b64 = base64.b64encode(body).decode("ascii")

            return {
                "action": "download_file",
                "bucket": v.bucket,
                "key": v.key,
                "size_bytes": len(body),
                "content_type": content_type,
                "data": data_b64[:1000] + ("..." if len(data_b64) > 1000 else ""),
                "data_full_length": len(data_b64),
                "note": "data is base64-encoded. Full data available via presigned URL or truncated for display.",
            }

        except Exception as e:
            logger.exception("S3 download failed: %s", e)
            return {"action": "download_file", "error": f"S3 download failed: {e}"}

    async def _list_objects(self, v: AwsS3UploaderInput) -> dict[str, Any]:
        try:
            s3 = self._get_client()
            list_kwargs: dict[str, Any] = {
                "Bucket": v.bucket,
                "MaxKeys": min(v.max_keys or 50, 1000),
            }
            if v.prefix:
                list_kwargs["Prefix"] = v.prefix

            resp = await self._run_s3(s3.list_objects_v2, **list_kwargs)

            contents = resp.get("Contents", [])
            return {
                "action": "list_objects",
                "bucket": v.bucket,
                "prefix": v.prefix,
                "objects": [self._summarize_object(obj) for obj in contents],
                "count": len(contents),
                "is_truncated": resp.get("IsTruncated", False),
                "next_token": resp.get("NextContinuationToken"),
            }

        except Exception as e:
            logger.exception("S3 list_objects failed: %s", e)
            return {"action": "list_objects", "error": f"S3 list failed: {e}"}

    async def _generate_url(self, v: AwsS3UploaderInput) -> dict[str, Any]:
        if not v.key:
            return {"action": "generate_presigned_url", "error": "key is required"}

        try:
            s3 = self._get_client()
            expires = v.expires or DEFAULT_EXPIRES
            url = await self._run_s3(
                s3.generate_presigned_url,
                "get_object",
                Params={"Bucket": v.bucket, "Key": v.key},
                ExpiresIn=expires,
            )

            return {
                "action": "generate_presigned_url",
                "bucket": v.bucket,
                "key": v.key,
                "presigned_url": url,
                "expires_seconds": expires,
                "expires_at_hint": f"URL valid for {expires}s from generation time",
            }

        except Exception as e:
            logger.exception("S3 presigned URL failed: %s", e)
            return {
                "action": "generate_presigned_url",
                "error": f"Failed to generate URL: {e}",
            }

    async def _delete_object(self, v: AwsS3UploaderInput) -> dict[str, Any]:
        if not v.key:
            return {"action": "delete_object", "error": "key is required"}

        try:
            s3 = self._get_client()
            await self._run_s3(s3.delete_object, Bucket=v.bucket, Key=v.key)

            return {
                "action": "delete_object",
                "bucket": v.bucket,
                "key": v.key,
                "deleted": True,
            }

        except Exception as e:
            logger.exception("S3 delete_object failed: %s", e)
            return {"action": "delete_object", "error": f"S3 delete failed: {e}"}

    async def _get_bucket_info(self, v: AwsS3UploaderInput) -> dict[str, Any]:
        try:
            s3 = self._get_client()

            # Get bucket location
            loc_resp = await self._run_s3(s3.get_bucket_location, Bucket=v.bucket)
            region = loc_resp.get("LocationConstraint") or "us-east-1"

            # Count total objects (approximate via list)
            list_resp = s3.list_objects_v2(Bucket=v.bucket, MaxKeys=1)
            total_objects = list_resp.get("KeyCount", 0)

            return {
                "action": "get_bucket_info",
                "bucket": v.bucket,
                "region": region,
                "note": "Bucket exists and is accessible. Full size requires additional API calls.",
            }

        except Exception as e:
            logger.exception("S3 bucket_info failed: %s", e)
            return {"action": "get_bucket_info", "error": f"Bucket info failed: {e}"}

    async def _copy_object(self, v: AwsS3UploaderInput) -> dict[str, Any]:
        if not v.key:
            return {"action": "copy_object", "error": "key (source) is required"}
        if not v.destination_key:
            return {"action": "copy_object", "error": "destination_key is required"}

        try:
            s3 = self._get_client()
            copy_source = {"Bucket": v.bucket, "Key": v.key}
            await self._run_s3(
                s3.copy_object,
                Bucket=v.bucket,
                Key=v.destination_key,
                CopySource=copy_source,
            )

            return {
                "action": "copy_object",
                "bucket": v.bucket,
                "source_key": v.key,
                "destination_key": v.destination_key,
                "copied": True,
            }

        except Exception as e:
            logger.exception("S3 copy_object failed: %s", e)
            return {"action": "copy_object", "error": f"S3 copy failed: {e}"}


# ── Register ────────────────────────────────────────────────────────

register_tool(AwsS3UploaderTool())
