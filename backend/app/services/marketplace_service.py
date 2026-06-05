"""Marketplace service — seed data and business logic."""

import json
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import MarketplaceListingModel

_SEED_LISTINGS = [
    {
        "name": "Lead Enrichment & CRM Auto-Router",
        "type": "template",
        "category": "Sales",
        "description": "Automatically enrich incoming leads with Clearbit/Apollo data and route to the right CRM pipeline by score, company size, and industry. #1 ROI workflow across n8n/Zapier/Make.",
        "integrations": ["clearbit", "hubspot", "salesforce"],
        "tags": ["leads", "crm", "enrichment", "sales"],
    },
    {
        "name": "AI Cold Email Personalization Engine",
        "type": "template",
        "category": "Sales",
        "description": "Pull prospects from Google Sheets, generate personalized emails using AI with company-specific context, and send via Gmail/SendGrid. Top-performing sales template.",
        "integrations": ["gmail", "sendgrid", "google-sheets"],
        "tags": ["email", "sales", "ai", "personalization"],
    },
    {
        "name": "Chat with Your Documents (RAG)",
        "type": "template",
        "category": "AI",
        "description": "Upload PDFs and documents, ask questions in natural language, get answers with source citations. LangChain's #1 most-downloaded template (31M+ downloads).",
        "integrations": ["openai", "pinecone", "qdrant"],
        "tags": ["rag", "documents", "ai", "chat"],
    },
    {
        "name": "Invoice & PDF Data Extraction Pipeline",
        "type": "template",
        "category": "Finance",
        "description": "Automatically extract line items, totals, dates, and vendor info from invoices and PDFs using AI. Push to QuickBooks or accounting software. Saves 5+ hours/week.",
        "integrations": ["quickbooks", "xero", "stripe"],
        "tags": ["finance", "invoices", "pdf", "extraction"],
    },
    {
        "name": "Social Media Cross-Post Scheduler",
        "type": "template",
        "category": "Marketing",
        "description": "Write once, publish everywhere. Automatically adapt and schedule content to LinkedIn, Twitter/X, Facebook, and TikTok with platform-specific formatting.",
        "integrations": ["linkedin", "twitter", "facebook", "tiktok"],
        "tags": ["social-media", "marketing", "scheduling", "cross-post"],
    },
    {
        "name": "AI Email Triage & Auto-Response",
        "type": "template",
        "category": "Support",
        "description": "Classify incoming emails by intent and urgency, route to the right team member, and draft AI responses for common requests. Fastest-growing n8n category.",
        "integrations": ["gmail", "outlook", "slack"],
        "tags": ["support", "email", "ai", "triage"],
    },
    {
        "name": "Abandoned Cart Recovery Automation",
        "type": "template",
        "category": "E-commerce",
        "description": "Detect abandoned carts in Shopify, wait 1 hour, check if order completed, then send a personalized recovery email via Klaviyo. Proven revenue recovery.",
        "integrations": ["shopify", "klaviyo", "stripe"],
        "tags": ["e-commerce", "cart-recovery", "email", "revenue"],
    },
    {
        "name": "Slack Notification Hub",
        "type": "template",
        "category": "Operations",
        "description": "Centralize all your tool notifications into Slack. Google Calendar events, form submissions, CRM updates, GitHub alerts — all in one organized channel.",
        "integrations": ["slack", "google-calendar", "github"],
        "tags": ["notifications", "slack", "operations", "hub"],
    },
    {
        "name": "Employee Onboarding Workflow",
        "type": "template",
        "category": "HR",
        "description": "When a new hire form is submitted: create a Notion page, send Slack welcome, email IT for equipment setup, and schedule 30-day check-in. Top Make.com template.",
        "integrations": ["notion", "slack", "gmail"],
        "tags": ["hr", "onboarding", "automation", "hiring"],
    },
    {
        "name": "AI Sales Call Analyzer",
        "type": "agent",
        "category": "Sales",
        "description": "Connect Gong or call transcripts, analyze for sentiment, key objections, competitor mentions, and action items. Push summaries to Slack. Gumloop featured agent.",
        "integrations": ["gong", "slack", "openai"],
        "tags": ["sales", "ai", "call-analysis", "sentiment"],
    },
]


async def seed_marketplace_listings(db: AsyncSession) -> dict:
    """Insert sample marketplace listings if none exist. Idempotent."""
    result = await db.execute(select(func.count(MarketplaceListingModel.id)))
    existing = result.scalar() or 0
    if existing > 0:
        return {"new": 0, "total": existing}

    # Use a synthetic system user ID for seed data
    system_user_id = "00000000-0000-0000-0000-000000000000"

    for data in _SEED_LISTINGS:
        listing = MarketplaceListingModel(
            id=str(uuid4()),
            name=data["name"],
            description=data["description"],
            owner_id=system_user_id,
            listing_type=data["type"],
            category_id=data["category"],
            price=0,
            is_published=True,
            integrations=json.dumps(data.get("integrations", [])),
            tags=json.dumps(data.get("tags", [])),
        )
        db.add(listing)

    return {"new": len(_SEED_LISTINGS), "total": len(_SEED_LISTINGS)}
