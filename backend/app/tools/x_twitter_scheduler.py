"""
Social Media & Content Publishing Tools — X/Twitter Scheduler.

x_twitter_scheduler → Draft, schedule, and publish posts or threads to X
    using the X API v2 with OAuth 1.0a User Context.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from pydantic import Field

try:
    from requests_oauthlib import OAuth1Session
except ImportError:
    OAuth1Session = None  # type: ignore[assignment]

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, is_placeholder, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET", "")
X_BASE_URL = "https://api.twitter.com/2"

TWITTER_TIMEOUT = int(os.getenv("TWITTER_TIMEOUT", "30"))

MAX_THREAD_LENGTH = int(os.getenv("TWITTER_MAX_THREAD_LENGTH", "20"))
MAX_TWEET_LENGTH = 280

# In-memory schedule store (production should use DB/Redis)
_scheduled_tweets: dict[str, dict[str, Any]] = {}


# ── Input ─────────────────────────────────────────────────────────────


class XTwitterSchedulerInput(ToolInput):
    message: str = Field(
        ...,
        description="Content to post. For threads, use '|||' as tweet separator.",
    )
    schedule_at: str | None = Field(
        None,
        description="ISO 8601 datetime to schedule post (e.g. '2026-06-01T14:00:00Z'). Posts immediately if unset.",
    )
    reply_to_tweet_id: str | None = Field(
        None,
        description="Tweet ID to reply to (optional)",
    )
    dry_run: bool = Field(
        False,
        description="If true, validate and preview without posting",
    )


class XTwitterSchedulerStatusInput(ToolInput):
    """Check status of a scheduled tweet."""
    schedule_id: str = Field(..., description="Schedule ID returned by the scheduler")


# ── Tool: Scheduler ───────────────────────────────────────────────────


class XTwitterSchedulerTool(BaseTool):
    """Draft, schedule, and publish posts or threads to X via API v2."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="x_twitter_scheduler",
            name="X/Twitter Scheduler",
            description=(
                "Draft, schedule, and publish posts or threads to X (Twitter) "
                "using the X API v2. Supports threaded posts, reply-to, "
                "scheduled publishing, and dry-run previews."
            ),
            category="social-media-content-publishing",
            input_schema=XTwitterSchedulerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["social", "twitter", "x", "schedule", "publish"],
            requires_auth=True,
            timeout_seconds=TWITTER_TIMEOUT + 15,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = XTwitterSchedulerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if not validated.message.strip():
            return ToolResult.error_result(
                tool_id=self.tool_id, error="Message must not be empty"
            )

        try:
            result = await self._publish_or_schedule(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("x_twitter_scheduler failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _publish_or_schedule(
        self, validated: XTwitterSchedulerInput
    ) -> dict[str, Any]:
        """Split message into thread, validate, and publish or schedule."""
        # Split into thread parts
        tweets = [t.strip() for t in validated.message.split("|||") if t.strip()]
        if not tweets:
            return {"error": "No valid tweet content after splitting"}

        if len(tweets) > MAX_THREAD_LENGTH:
            return {
                "error": f"Thread too long: {len(tweets)} tweets (max {MAX_THREAD_LENGTH})"
            }

        # Validate each tweet length
        for i, tweet in enumerate(tweets):
            if len(tweet) > MAX_TWEET_LENGTH:
                return {
                    "error": f"Tweet {i+1} exceeds {MAX_TWEET_LENGTH} characters "
                    f"({len(tweet)} chars)"
                }

        preview = {
            "tweet_count": len(tweets),
            "total_characters": sum(len(t) for t in tweets),
            "is_thread": len(tweets) > 1,
            "tweets": [
                {"index": i, "text": t[:100] + ("..." if len(t) > 100 else ""), "length": len(t)}
                for i, t in enumerate(tweets)
            ],
        }

        if validated.dry_run:
            return {"status": "dry_run", "preview": preview}

        # Scheduling
        if validated.schedule_at:
            return await self._schedule(validated, tweets, preview)

        # Publish now — check credentials first
        if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
            return {
                "status": "not_configured",
                "message": (
                    "X API credentials not configured. Set X_API_KEY, X_API_SECRET, "
                    "X_ACCESS_TOKEN, and X_ACCESS_SECRET environment variables. "
                    "Preview available below."
                ),
                "preview": preview,
            }

        if any(is_placeholder(v) for v in [X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
            return {
                "status": "not_configured",
                "message": (
                    "X API credentials contain a placeholder. "
                    "Replace placeholder in .env with real X_API_KEY, X_API_SECRET, "
                    "X_ACCESS_TOKEN, and X_ACCESS_SECRET values "
                    "(from https://developer.x.com → Projects & Apps → Keys and tokens). "
                    "Preview available below."
                ),
                "preview": preview,
            }

        if OAuth1Session is None:
            return {
                "status": "error",
                "error": "requests_oauthlib is not installed. Install with: pip install requests_oauthlib",
                "preview": preview,
            }

        return await self._publish_thread(tweets, validated.reply_to_tweet_id, preview)

    async def _schedule(
        self,
        validated: XTwitterSchedulerInput,
        tweets: list[str],
        preview: dict,
    ) -> dict[str, Any]:
        """Store tweet for later publishing."""
        try:
            scheduled_time = datetime.fromisoformat(
                validated.schedule_at.replace("Z", "+00:00")
            )
        except ValueError as e:
            return {"error": f"Invalid schedule_at format: {e}"}

        if scheduled_time <= datetime.now(UTC):
            return {"error": "schedule_at must be in the future"}

        schedule_id = f"sched_{int(scheduled_time.timestamp())}_{len(tweets)}tweets"
        _scheduled_tweets[schedule_id] = {
            "tweets": tweets,
            "scheduled_at": validated.schedule_at,
            "reply_to": validated.reply_to_tweet_id,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "scheduled",
        }

        return {
            "status": "scheduled",
            "schedule_id": schedule_id,
            "scheduled_at": validated.schedule_at,
            "preview": preview,
            "note": "Scheduled tweets are stored in memory and will be lost on restart. "
            "Use Celery Beat for production scheduling.",
        }

    async def _publish_thread(
        self,
        tweets: list[str],
        reply_to: str | None,
        preview: dict,
    ) -> dict[str, Any]:
        """Publish a thread to X API v2."""
        posted: list[dict] = []
        in_reply_to = reply_to

        for i, text in enumerate(tweets):
            try:
                tweet = await self._post_tweet(text, in_reply_to)
                posted.append({"index": i, "tweet_id": tweet["id"], "text": text})
                in_reply_to = tweet["id"]
            except Exception as e:
                logger.error(f"Failed to post tweet {i}: {e}")
                return {
                    "status": "partial",
                    "error": f"Failed at tweet {i}: {e}",
                    "posted": posted,
                    "remaining": len(tweets) - len(posted),
                    "preview": preview,
                }

        return {
            "status": "published",
            "tweets": posted,
            "thread_id": posted[0]["tweet_id"] if posted else None,
            "preview": preview,
        }

    async def _post_tweet(self, text: str, reply_to: str | None = None) -> dict:
        """Post a single tweet via X API v2."""
        oauth = OAuth1Session(
            X_API_KEY,
            client_secret=X_API_SECRET,
            resource_owner_key=X_ACCESS_TOKEN,
            resource_owner_secret=X_ACCESS_SECRET,
        )

        payload: dict[str, Any] = {"text": text}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}

        # Use httpx-compatible approach via run_in_executor for blocking OAuth1
        loop = asyncio.get_running_loop()

        def _post():
            resp = oauth.post(f"{X_BASE_URL}/tweets", json=payload)
            if resp.status_code not in (200, 201):
                try:
                    err = resp.json()
                    raise Exception(
                        f"X API error {resp.status_code}: {err.get('detail', resp.text)}"
                    )
                except (json.JSONDecodeError, KeyError):
                    raise Exception(f"X API error {resp.status_code}: {resp.text}")
            return resp.json()["data"]

        return await loop.run_in_executor(None, _post)


# ── Tool: Schedule Status ─────────────────────────────────────────────


class XTwitterSchedulerStatusTool(BaseTool):
    """Check the status of a previously scheduled tweet."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="x_twitter_scheduler_status",
            name="X/Twitter Schedule Status",
            description="Check the status of a scheduled X/Twitter post.",
            category="social-media-content-publishing",
            input_schema=XTwitterSchedulerStatusInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["social", "twitter", "schedule", "status"],
            requires_auth=False,
            timeout_seconds=10,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = XTwitterSchedulerStatusInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        sched = _scheduled_tweets.get(validated.schedule_id)
        if not sched:
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "schedule_id": validated.schedule_id,
                    "found": False,
                    "message": "No scheduled tweet found with this ID (may have been published or expired)",
                },
            )

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "schedule_id": validated.schedule_id,
                "found": True,
                "status": sched["status"],
                "scheduled_at": sched["scheduled_at"],
                "tweet_count": len(sched["tweets"]),
                "created_at": sched["created_at"],
            },
        )


# ── Register ──────────────────────────────────────────────────────────

register_tool(XTwitterSchedulerTool())
register_tool(XTwitterSchedulerStatusTool())
