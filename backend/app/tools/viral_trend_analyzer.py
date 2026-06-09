"""
Social Media & Content Publishing Tools — Viral Trend Analyzer (DIFFERENTIATOR).

viral_trend_analyzer → Analyze current trending topics across social
    platforms using web data and LLM analysis. ⭐ DIFFERENTIATOR
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
TREND_TIMEOUT = int(os.getenv("TREND_TIMEOUT", "60"))
TREND_LLM_MODEL = os.getenv("TREND_LLM_MODEL", "gpt-4o-mini")


# ── Input ─────────────────────────────────────────────────────────────


class ViralTrendAnalyzerInput(ToolInput):
    platforms: list[str] | None = Field(
        None,
        description="Platforms to analyze: 'twitter', 'tiktok', 'youtube', "
        "'reddit', 'linkedin', 'news'. Defaults to all except Instagram.",
    )
    topic: str | None = Field(
        None,
        description="Specific topic or keyword to analyze trends for",
    )
    region: str = Field(
        "US",
        description="Country code for regional trends (e.g. 'US', 'GB', 'JP')",
    )
    max_results: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum number of trends to return",
    )
    analyze_sentiment: bool = Field(
        True,
        description="Whether to include sentiment analysis for each trend",
    )
    suggest_content: bool = Field(
        False,
        description="Whether to suggest content ideas for identified trends",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class ViralTrendAnalyzerTool(BaseTool):
    """Analyze trending topics across platforms with AI insights. ⭐ DIFFERENTIATOR"""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="viral_trend_analyzer",
            name="Viral Trend Analyzer",
            description=(
                "Analyze current trending topics across social platforms and news. "
                "Uses web data aggregation and LLM analysis to identify viral patterns, "
                "sentiment, and content opportunities. ⭐ DIFFERENTIATOR"
            ),
            category="social-media-content-publishing",
            input_schema=ViralTrendAnalyzerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=[
                "social",
                "trends",
                "viral",
                "analysis",
                "sentiment",
                "analytics",
                "differentiator",
            ],
            requires_auth=True,
            timeout_seconds=TREND_TIMEOUT + 30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ViralTrendAnalyzerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.max_results < 1 or validated.max_results > 50:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="max_results must be between 1 and 50",
            )

        try:
            result = await self._analyze(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except Exception as e:
            logger.exception("viral_trend_analyzer failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _analyze(self, validated: ViralTrendAnalyzerInput) -> dict[str, Any]:
        """Gather trend data from platforms and analyze via LLM."""
        platforms = validated.platforms or [
            "twitter",
            "tiktok",
            "youtube",
            "reddit",
            "linkedin",
            "news",
        ]

        # Gather trend data from each platform
        platform_data: dict[str, Any] = {}
        for platform in platforms:
            try:
                platform_data[platform] = await self._fetch_platform_trends(
                    platform, validated.topic, validated.region
                )
            except Exception as e:
                logger.warning('Failed to fetch %s trends: %s', platform, e)
                platform_data[platform] = {"error": str(e), "trends": []}

        # Analyze via LLM
        if not OPENAI_API_KEY:
            return {
                "status": "partial",
                "platform_data": platform_data,
                "analysis": {
                    "summary": (
                        "LLM analysis unavailable: OPENAI_API_KEY not configured. Raw platform data provided below."
                    ),
                    "top_trends": [],
                    "sentiment_summary": "N/A",
                    "recommendations": [],
                },
                "engine": "data-only",
            }

        analysis = await self._analyze_trends_with_llm(platform_data, validated)

        return {
            "status": "complete",
            "query": {
                "topic": validated.topic,
                "region": validated.region,
                "platforms": platforms,
            },
            "platform_data": platform_data,
            "analysis": analysis,
            "engine": "llm-enhanced",
        }

    async def _fetch_platform_trends(
        self, platform: str, topic: str | None, region: str
    ) -> dict[str, Any]:
        """Scrape trend data from a platform's public endpoints."""
        # All data is gathered from public, non-authenticated endpoints
        async with httpx.AsyncClient(timeout=TREND_TIMEOUT) as client:
            if platform == "reddit":
                return await self._fetch_reddit_trends(client, topic)
            elif platform == "news":
                return await self._fetch_news_trends(client, topic, region)
            elif platform == "twitter":
                return await self._fetch_twitter_trends(client, region)
            elif platform == "youtube":
                return await self._fetch_youtube_trends(client, region)
            elif platform == "tiktok":
                return await self._fetch_tiktok_trends(client, topic)
            elif platform == "linkedin":
                return await self._fetch_linkedin_trends(client, topic)
            return {"error": f"Unknown platform: {platform}"}

    async def _fetch_reddit_trends(
        self, client: httpx.AsyncClient, topic: str | None
    ) -> dict[str, Any]:
        """Fetch trending posts from Reddit."""
        subreddit = "all"
        if topic:
            subreddit = topic.replace(" ", "")

        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
        resp = await client.get(
            url, headers={"User-Agent": "Flowmanner/1.0"}, follow_redirects=True
        )
        if resp.status_code != 200:
            return {"error": f"Reddit returned {resp.status_code}"}

        data = resp.json()
        posts = []
        for post in data.get("data", {}).get("children", []):
            pdata = post["data"]
            posts.append(
                {
                    "title": pdata.get("title", ""),
                    "subreddit": pdata.get("subreddit", ""),
                    "score": pdata.get("score", 0),
                    "num_comments": pdata.get("num_comments", 0),
                    "url": f"https://reddit.com{pdata.get('permalink', '')}",
                    "created_utc": pdata.get("created_utc", 0),
                }
            )

        return {
            "source": "reddit",
            "trends": posts[:15],
            "total_fetched": len(posts),
        }

    async def _fetch_news_trends(
        self, client: httpx.AsyncClient, topic: str | None, region: str
    ) -> dict[str, Any]:
        """Fetch trending news headlines."""
        # Use NewsAPI-like approach with public RSS feeds
        feeds = {
            "US": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
            "GB": "https://feeds.bbci.co.uk/news/rss.xml",
            "JP": "https://www3.nhk.or.jp/rss/news/cat0.xml",
        }
        feed_url = feeds.get(region, feeds["US"])

        resp = await client.get(feed_url, follow_redirects=True)
        if resp.status_code != 200:
            return {"error": f"News feed returned {resp.status_code}"}

        # Simple XML parsing for RSS (defusedxml not required — these are trusted feeds)
        import xml.etree.ElementTree as ET

        root = ET.fromstring(resp.text)
        items = []
        for item in root.iter("item"):
            items.append(
                {
                    "title": (item.findtext("title") or "").strip(),
                    "link": (item.findtext("link") or "").strip(),
                    "description": (item.findtext("description") or "")[:200].strip(),
                }
            )

        if topic:
            items = [
                i
                for i in items
                if topic.lower()
                in (i.get("title", "") + i.get("description", "")).lower()
            ]

        return {
            "source": f"news-{region}",
            "trends": items[:15],
            "total_fetched": len(items),
        }

    async def _fetch_twitter_trends(
        self, client: httpx.AsyncClient, region: str
    ) -> dict[str, Any]:
        """Note: Twitter trends require API v1.1 which is restricted."""
        return {
            "source": "twitter",
            "trends": [],
            "note": (
                "X/Twitter trending API (v1.1) requires Elevated access and is not "
                "available for automated scraping. Use the X/Twitter Scheduler tool's "
                "API credentials for authenticated trend access."
            ),
        }

    async def _fetch_youtube_trends(
        self, client: httpx.AsyncClient, region: str
    ) -> dict[str, Any]:
        """Fetch YouTube trending videos via public RSS feed."""
        region_code = region.lower()
        url = f"https://www.youtube.com/feeds/videos.xml?gl={region_code}"

        resp = await client.get(url, follow_redirects=True)
        if resp.status_code != 200:
            return {"error": f"YouTube feed returned {resp.status_code}"}

        import xml.etree.ElementTree as ET

        root = ET.fromstring(resp.text)
        ns = {"yt": "http://www.youtube.com/xml/schemas/2015"}
        items = []
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            items.append(
                {
                    "title": (
                        entry.findtext("{http://www.w3.org/2005/Atom}title") or ""
                    ).strip(),
                    "link": entry.find("{http://www.w3.org/2005/Atom}link").get(
                        "href", ""
                    ),
                    "channel": (
                        entry.findtext(
                            "{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name"
                        )
                        or ""
                    ).strip(),
                }
            )

        return {
            "source": "youtube",
            "trends": items[:15],
            "total_fetched": len(items),
        }

    async def _fetch_tiktok_trends(
        self, client: httpx.AsyncClient, topic: str | None
    ) -> dict[str, Any]:
        """TikTok trends via public RSS-style endpoint (limited)."""
        return {
            "source": "tiktok",
            "trends": [],
            "note": (
                "TikTok trending data requires their Research API or unofficial "
                "scraping tools. Use topic-specific hashtag research manually."
            ),
        }

    async def _fetch_linkedin_trends(
        self, client: httpx.AsyncClient, topic: str | None
    ) -> dict[str, Any]:
        """LinkedIn trends via public pulse/content (limited)."""
        return {
            "source": "linkedin",
            "trends": [],
            "note": (
                "LinkedIn trending content is API-gated. Use news + Reddit data "
                "as a proxy for professional content trends."
            ),
        }

    async def _analyze_trends_with_llm(
        self,
        platform_data: dict[str, Any],
        validated: ViralTrendAnalyzerInput,
    ) -> dict[str, Any]:
        """Send aggregated trend data to LLM for analysis."""
        # Build a concise data summary for the LLM
        data_summary_parts: list[str] = []
        total_trends = 0
        for platform, pdata in platform_data.items():
            trends = pdata.get("trends", [])
            total_trends += len(trends)
            if trends and not pdata.get("note"):
                titles = [t.get("title", t.get("headline", "")) for t in trends[:5]]
                data_summary_parts.append(
                    f"**{platform.capitalize()}**:\n"
                    + "\n".join(f"- {t}" for t in titles)
                )
            elif pdata.get("note"):
                data_summary_parts.append(
                    f"**{platform.capitalize()}**: {pdata.get('note')}"
                )

        if not data_summary_parts:
            return {
                "summary": "No trend data available from any platform.",
                "top_trends": [],
                "sentiment_summary": "N/A",
                "recommendations": [],
            }

        system_prompt = (
            "You are a viral trend analyst. Analyze the following social media "
            "and news trends. Return a JSON object with these fields:\n"
            '- "summary": 2-3 sentence overview of the trend landscape\n'
            '- "top_trends": array of {title, platform, momentum_score (1-10), '
            "audience_size_estimate, relevant_hashtags: [string]}\n"
            '- "sentiment_summary": overall sentiment of the trending topics\n'
            '- "recommendations": array of {trend, action, content_idea} '
            "for content creators"
        )

        if validated.suggest_content:
            system_prompt += ", include specific content creation ideas for each trend"
        else:
            system_prompt += ", omit detailed content ideas"

        user_prompt = (
            f"Platform: {', '.join(validated.platforms or ['all'])}\n"
            f"Region: {validated.region}\n"
            f"Focus topic: {validated.topic or 'general'}\n"
            f"Max results: {validated.max_results}\n\n"
            "=== TREND DATA ===\n\n" + "\n\n".join(data_summary_parts)
        )

        async with httpx.AsyncClient(timeout=TREND_TIMEOUT) as client:
            resp = await client.post(
                f"{OPENAI_BASE_URL.rstrip('/')}/v1/chat/completions",
                json={
                    "model": TREND_LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]

        try:
            analysis = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re

            match = re.search(r"\{[\s\S]*\}", content)
            if match:
                try:
                    analysis = json.loads(match.group())
                except json.JSONDecodeError:
                    analysis = {
                        "summary": content,
                        "top_trends": [],
                        "sentiment_summary": "N/A",
                        "recommendations": [],
                    }
            else:
                analysis = {
                    "summary": content,
                    "top_trends": [],
                    "sentiment_summary": "N/A",
                    "recommendations": [],
                }

        analysis["total_trends_analyzed"] = total_trends
        analysis["platforms_analyzed"] = list(platform_data.keys())
        return analysis


# ── Register ──────────────────────────────────────────────────────────

register_tool(ViralTrendAnalyzerTool())
