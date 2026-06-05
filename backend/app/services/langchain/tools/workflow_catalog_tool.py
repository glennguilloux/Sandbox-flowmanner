"""
LangChain Tool: Workflow Catalog Agent
Search and recommend workflows from the catalog
"""

import json
import os

import requests
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class CatalogRequest(BaseModel):
    """Request model for catalog operations"""

    action: str = Field(
        ..., description="Action: search, recommend, describe, categories"
    )
    query: str | None = Field(None, description="Search query or workflow ID")
    category: str | None = Field(None, description="Filter by category")
    limit: int | None = Field(5, description="Max results to return")


class CatalogClient:
    """Client for Workflow Catalog API"""

    def __init__(self):
        self.base_url = os.getenv("BACKEND_API_URL", "http://backend:5000/api")

    def search_workflows(
        self, query: str, category: str = None, limit: int = 5
    ) -> list[dict]:
        """Search workflows by query"""
        try:
            response = requests.get(
                f"{self.base_url}/catalog",
                params={"search": query, "category": category, "limit": limit},
                timeout=10,
            )
            response.raise_for_status()
            return response.json().get("workflows", [])
        except Exception as e:
            # Fallback to local search if API fails
            return self._local_search(query, category, limit)

    def recommend_workflows(self, intent: str, limit: int = 5) -> list[dict]:
        """Get workflow recommendations based on intent"""
        try:
            response = requests.post(
                f"{self.base_url}/catalog/recommend",
                json={"intent": intent, "limit": limit},
                timeout=10,
            )
            response.raise_for_status()
            return response.json().get("recommendations", [])
        except Exception:
            # Intent-based local recommendations
            return self._intent_recommend(intent, limit)

    def describe_workflow(self, workflow_id: str) -> dict:
        """Get detailed workflow description"""
        try:
            response = requests.get(
                f"{self.base_url}/catalog/{workflow_id}", timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return self._local_describe(workflow_id)

    def list_categories(self) -> list[dict]:
        """List all categories"""
        try:
            response = requests.get(f"{self.base_url}/catalog/categories", timeout=10)
            response.raise_for_status()
            return response.json().get("categories", [])
        except Exception:
            return self._local_categories()

    def _local_search(
        self, query: str, category: str = None, limit: int = 5
    ) -> list[dict]:
        """Local fallback search"""
        workflows = self._get_local_workflows()

        query_lower = query.lower() if query else ""

        results = []
        for wf in workflows:
            if category and wf.get("category") != category:
                continue

            if query_lower:
                text = f"{wf.get('name', '')} {wf.get('description', '')} {' '.join(wf.get('tags', []))}".lower()
                if query_lower in text:
                    results.append(wf)
            else:
                results.append(wf)

        return results[:limit]

    def _intent_recommend(self, intent: str, limit: int = 5) -> list[dict]:
        """Recommend based on intent"""
        workflows = self._get_local_workflows()
        intent_lower = intent.lower()

        # Intent to category mapping
        intent_map = {
            "image": ["Visual"],
            "photo": ["Visual"],
            "3d": ["Visual"],
            "generate": ["Visual"],
            "create": ["Visual"],
            "social": ["Automation"],
            "schedule": ["Automation"],
            "auto": ["Automation"],
            "daily": ["Automation"],
            "digest": ["Automation"],
            "audio": ["Audio"],
            "voice": ["Audio"],
            "data": ["Data"],
            "sync": ["Data"],
            "support": ["Support"],
            "help": ["Support"],
        }

        recommended_categories = []
        for key, categories in intent_map.items():
            if key in intent_lower:
                recommended_categories.extend(categories)

        if not recommended_categories:
            recommended_categories = ["Visual", "Automation"]

        results = [
            wf for wf in workflows if wf.get("category") in recommended_categories
        ]

        return results[:limit]

    def _local_describe(self, workflow_id: str) -> dict:
        """Local fallback description"""
        workflows = self._get_local_workflows()
        for wf in workflows:
            if wf.get("id") == workflow_id:
                return wf
        return {"error": "Workflow not found"}

    def _local_categories(self) -> list[dict]:
        """Local categories"""
        workflows = self._get_local_workflows()
        categories = {}

        for wf in workflows:
            cat = wf.get("category", "Other")
            categories[cat] = categories.get(cat, 0) + 1

        return [{"name": cat, "count": count} for cat, count in categories.items()]

    def _get_local_workflows(self) -> list[dict]:
        """Get local workflow catalog"""
        return [
            {
                "id": "visual-3d-hero",
                "name": "3D Hero Background Generator",
                "description": "Generate professional 3D hero backgrounds for websites and presentations",
                "category": "Visual",
                "tags": ["3d", "hero", "background", "website"],
                "complexity": "simple",
                "estimated_time": "30 seconds",
                "inputs": ["description", "style"],
                "outputs": ["image_url"],
                "source": "comfyui",
            },
            {
                "id": "visual-product-shot",
                "name": "Product Photography Studio",
                "description": "Generate high-quality product shots for e-commerce",
                "category": "Visual",
                "tags": ["product", "photo", "ecommerce", "studio"],
                "complexity": "simple",
                "estimated_time": "30 seconds",
                "inputs": ["product_name", "style"],
                "outputs": ["image_url"],
                "source": "comfyui",
            },
            {
                "id": "visual-3d-model",
                "name": "3D Model Generator",
                "description": "Create 3D model images for games and visualizations",
                "category": "Visual",
                "tags": ["3d", "model", "game", "asset"],
                "complexity": "simple",
                "estimated_time": "45 seconds",
                "inputs": ["description", "style"],
                "outputs": ["image_url"],
                "source": "comfyui",
            },
            {
                "id": "auto-social-media",
                "name": "Social Media Automation",
                "description": "Automatically post content to social media platforms",
                "category": "Automation",
                "tags": ["social", "auto", "post", "schedule"],
                "complexity": "medium",
                "estimated_time": "2 minutes",
                "inputs": ["content", "platforms", "schedule"],
                "outputs": ["status"],
                "source": "n8n",
            },
            {
                "id": "auto-daily-digest",
                "name": "Daily Digest Generator",
                "description": "Generate and send daily workflow reports via email",
                "category": "Automation",
                "tags": ["daily", "digest", "report", "email"],
                "complexity": "simple",
                "estimated_time": "1 minute",
                "inputs": ["email", "time"],
                "outputs": ["report"],
                "source": "n8n",
            },
            {
                "id": "audio-voice-assistant",
                "name": "Voice Assistant Integration",
                "description": "Text-to-speech for AI responses",
                "category": "Audio",
                "tags": ["voice", "tts", "audio", "assistant"],
                "complexity": "simple",
                "estimated_time": "10 seconds",
                "inputs": ["text", "voice"],
                "outputs": ["audio_url"],
                "source": "vibevoice",
            },
            {
                "id": "data-sync",
                "name": "Cross-Platform Data Sync",
                "description": "Synchronize data across multiple platforms",
                "category": "Data",
                "tags": ["data", "sync", "database", "integration"],
                "complexity": "complex",
                "estimated_time": "5 minutes",
                "inputs": ["source", "destination", "sync_type"],
                "outputs": ["status"],
                "source": "n8n",
            },
            {
                "id": "support-ai-agent",
                "name": "AI Customer Support Agent",
                "description": "Automated customer support with AI",
                "category": "Support",
                "tags": ["support", "ai", "customer", "help"],
                "complexity": "medium",
                "estimated_time": "1 minute",
                "inputs": ["query", "context"],
                "outputs": ["response"],
                "source": "n8n",
            },
        ]


# Main function
def workflow_catalog(
    action: str, query: str = None, category: str = None, limit: int = 5
) -> str:
    """
    Search and recommend workflows from the catalog.

    Actions:
    - search: Search workflows by query
    - recommend: Get recommendations based on intent
    - describe: Get detailed workflow info
    - categories: List all categories

    Examples:
    - "Find workflows for images" -> workflow_catalog("search", "image")
    - "Recommend something for automation" -> workflow_catalog("recommend", "automation")
    - "What is visual-3d-hero?" -> workflow_catalog("describe", "visual-3d-hero")
    - "What categories exist?" -> workflow_catalog("categories")

    Returns: JSON string with results
    """
    client = CatalogClient()

    try:
        if action == "search":
            results = client.search_workflows(query, category, limit)
            return json.dumps(
                {"success": True, "count": len(results), "workflows": results}, indent=2
            )

        elif action == "recommend":
            results = client.recommend_workflows(query or "general", limit)
            return json.dumps(
                {"success": True, "count": len(results), "recommendations": results},
                indent=2,
            )

        elif action == "describe":
            if not query:
                return json.dumps(
                    {"success": False, "error": "query required for describe"}
                )

            result = client.describe_workflow(query)
            return json.dumps({"success": True, "workflow": result}, indent=2)

        elif action == "categories":
            results = client.list_categories()
            return json.dumps({"success": True, "categories": results}, indent=2)

        else:
            return json.dumps({"success": False, "error": f"Unknown action: {action}"})

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


# LangChain tool wrapper
@tool
def workflow_catalog_tool(
    action: str, query: str = None, category: str = None, limit: int = 5
) -> str:
    """
    Search and recommend workflows from the catalog.

    Actions:
    - search: Search workflows by query
    - recommend: Get recommendations based on intent
    - describe: Get detailed workflow info
    - categories: List all categories

    Examples:
    - "Find workflows for images" -> workflow_catalog_tool("search", "image")
    - "Recommend something for automation" -> workflow_catalog_tool("recommend", "automation")
    - "What is visual-3d-hero?" -> workflow_catalog_tool("describe", "visual-3d-hero")
    - "What categories exist?" -> workflow_catalog_tool("categories")

    Returns: JSON string with results
    """
    return workflow_catalog(action, query, category, limit)


# Convenience functions
def search_workflows(query: str, limit: int = 5) -> str:
    """
    Search for workflows by keyword.

    Example:
    - "Find image workflows" -> search_workflows("image")
    - "Show me automation" -> search_workflows("automation")
    """
    return workflow_catalog("search", query, limit=limit)


def recommend_workflows(intent: str, limit: int = 3) -> str:
    """
    Get workflow recommendations based on your intent.

    Example:
    - "What should I use for social media?" -> recommend_workflows("social media")
    - "I need to generate images" -> recommend_workflows("generate images")
    """
    return workflow_catalog("recommend", intent, limit=limit)


def describe_workflow(workflow_id: str) -> str:
    """
    Get detailed information about a workflow.

    Example:
    - "What does visual-3d-hero do?" -> describe_workflow("visual-3d-hero")
    """
    return workflow_catalog("describe", workflow_id)
