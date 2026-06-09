"""
LangChain Tool: Workflow Catalog Agent - Production Ready
Search and recommend workflows from the catalog

Production Features:
- Connection pooling with requests.Session
- Retry logic with exponential backoff
- Structured logging
- Fallback to local catalog if API fails
- Custom exceptions
"""

import json
import logging
import os

import requests
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================


class CatalogConfig:
    """Configuration for catalog client"""

    BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://backend:5000/api")
    TIMEOUT = int(os.getenv("CATALOG_TIMEOUT", "10"))
    MAX_RETRIES = int(os.getenv("CATALOG_MAX_RETRIES", "2"))

    @classmethod
    def validate(cls):
        """Validate configuration"""
        if not cls.BACKEND_API_URL:
            logger.warning("BACKEND_API_URL not set, using default")

        logger.info('Catalog config validated - API URL: %s', cls.BACKEND_API_URL)


try:
    CatalogConfig.validate()
except Exception as e:
    logger.warning('Catalog configuration issue: %s', e)

# ==================== CUSTOM EXCEPTIONS ====================


class CatalogError(Exception):
    """Base exception for catalog operations"""

    pass


class CatalogConnectionError(CatalogError):
    """Connection to catalog API failed"""

    pass


# ==================== VALIDATION MODELS ====================


class CatalogRequest(BaseModel):
    """Request model for catalog operations"""

    action: str = Field(
        ..., description="Action: search, recommend, describe, categories"
    )
    query: str | None = Field(None, description="Search query or workflow ID")
    category: str | None = Field(None, description="Filter by category")
    limit: int | None = Field(5, description="Max results to return")


# ==================== HTTP CLIENT ====================


class HTTPClient:
    """HTTP client with connection pooling and retry logic"""

    def __init__(self, base_url: str, timeout: int = 10, max_retries: int = 2):
        self.base_url = base_url
        self.timeout = timeout

        self.session = requests.Session()

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"],
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy, pool_connections=3, pool_maxsize=3
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        logger.info('HTTP client initialized for catalog')

    def get(self, endpoint: str, params: dict | None = None) -> requests.Response:
        """GET request with retry logic"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            raise CatalogConnectionError(f"Request to {url} timed out")
        except requests.exceptions.ConnectionError:
            raise CatalogConnectionError(f"Cannot connect to {url}")
        except Exception as e:
            raise CatalogError(f"GET request failed: {e}")

    def post(self, endpoint: str, json_data: dict | None = None) -> requests.Response:
        """POST request with retry logic"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.post(url, json=json_data, timeout=self.timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            raise CatalogConnectionError(f"Request to {url} timed out")
        except requests.exceptions.ConnectionError:
            raise CatalogConnectionError(f"Cannot connect to {url}")
        except Exception as e:
            raise CatalogError(f"POST request failed: {e}")

    def close(self):
        """Close session"""
        if self.session:
            self.session.close()


# ==================== CATALOG CLIENT ====================


class CatalogClient:
    """Production-ready workflow catalog client"""

    def __init__(self):
        self.config = CatalogConfig
        self.http_client = HTTPClient(
            base_url=self.config.BACKEND_API_URL,
            timeout=self.config.TIMEOUT,
            max_retries=self.config.MAX_RETRIES,
        )
        logger.info('CatalogClient initialized for %s', self.config.BACKEND_API_URL)

    def search_workflows(
        self, query: str, category: str | None = None, limit: int = 5
    ) -> list[dict]:
        """Search workflows by query with fallback"""
        logger.info('Searching workflows - query: %s, category: %s, limit: %s', query, category, limit)

        try:
            response = self.http_client.get(
                "/catalog",
                params={"search": query, "category": category, "limit": limit},
            )
            workflows = response.json().get("workflows", [])
            logger.info('API search returned %s workflows', len(workflows))
            return workflows

        except CatalogConnectionError as e:
            logger.warning('API search failed, using fallback: %s', e)
            return self._local_search(query, category, limit)
        except Exception as e:
            logger.error('Unexpected error in search: %s', e)
            return self._local_search(query, category, limit)

    def recommend_workflows(self, intent: str, limit: int = 5) -> list[dict]:
        """Get workflow recommendations based on intent"""
        logger.info('Recommending workflows - intent: %s, limit: %s', intent, limit)

        try:
            response = self.http_client.post(
                "/catalog/recommend", json_data={"intent": intent, "limit": limit}
            )
            recommendations = response.json().get("recommendations", [])
            logger.info('API recommendations returned %s workflows', len(recommendations))
            return recommendations

        except CatalogConnectionError as e:
            logger.warning('API recommendations failed, using fallback: %s', e)
            return self._intent_recommend(intent, limit)
        except Exception as e:
            logger.error('Unexpected error in recommendations: %s', e)
            return self._intent_recommend(intent, limit)

    def describe_workflow(self, workflow_id: str) -> dict:
        """Get detailed workflow description"""
        logger.info('Describing workflow - id: %s', workflow_id)

        try:
            response = self.http_client.get(f"/catalog/{workflow_id}")
            return response.json()

        except CatalogConnectionError as e:
            logger.warning('API describe failed, using fallback: %s', e)
            return self._local_describe(workflow_id)
        except Exception as e:
            logger.error('Unexpected error in describe: %s', e)
            return self._local_describe(workflow_id)

    def list_categories(self) -> list[dict]:
        """List all categories"""
        logger.info("Listing categories")

        try:
            response = self.http_client.get("/catalog/categories")
            categories = response.json().get("categories", [])
            logger.info('API returned %s categories', len(categories))
            return categories

        except CatalogConnectionError as e:
            logger.warning('API categories failed, using fallback: %s', e)
            return self._local_categories()
        except Exception as e:
            logger.error('Unexpected error in categories: %s', e)
            return self._local_categories()

    # ==================== LOCAL FALLBACKS ====================

    def _local_search(
        self, query: str, category: str | None = None, limit: int = 5
    ) -> list[dict]:
        """Local fallback search"""
        workflows = self._get_local_workflows()
        query_lower = query.lower() if query else ""

        # Extract keywords from query (remove common words)
        if query_lower:
            common_words = {"find", "search", "for", "workflows", "show", "me", "all"}
            keywords = [
                w for w in query_lower.split() if w not in common_words and len(w) > 2
            ]
        else:
            keywords = []

        results = []
        for wf in workflows:
            if category and wf.get("category") != category:
                continue

            if keywords:
                text = f"{wf.get('name', '')} {wf.get('description', '')} {' '.join(wf.get('tags', []))}".lower()
                # Match if ANY keyword is in the text
                if any(kw in text for kw in keywords):
                    results.append(wf)
            else:
                results.append(wf)

        logger.info('Local search returned %s workflows', len(results[:limit]))
        return results[:limit]

    def _intent_recommend(self, intent: str, limit: int = 5) -> list[dict]:
        """Recommend based on intent"""
        workflows = self._get_local_workflows()
        intent_lower = intent.lower()

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

        logger.info('Intent-based recommendations: %s workflows', len(results[:limit]))
        return results[:limit]

    def _local_describe(self, workflow_id: str) -> dict:
        """Local fallback description"""
        workflows = self._get_local_workflows()
        for wf in workflows:
            if wf.get("id") == workflow_id:
                logger.info('Found workflow in local catalog: %s', workflow_id)
                return wf
        logger.warning('Workflow not found in local catalog: %s', workflow_id)
        return {"error": "Workflow not found"}

    def _local_categories(self) -> list[dict]:
        """Local categories"""
        workflows = self._get_local_workflows()
        categories = {}

        for wf in workflows:
            cat = wf.get("category", "Other")
            categories[cat] = categories.get(cat, 0) + 1

        result = [{"name": cat, "count": count} for cat, count in categories.items()]
        logger.info('Local categories: %s', len(result))
        return result

    def _get_local_workflows(self) -> list[dict]:
        """Get local workflow catalog (embedded fallback)"""
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

    def close(self):
        """Close HTTP client"""
        self.http_client.close()


# ==================== MAIN FUNCTION ====================


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
        logger.error('workflow_catalog failed: %s', e)
        return json.dumps({"success": False, "error": str(e)}, indent=2)
    finally:
        client.close()


# ==================== LANGCHAIN TOOL WRAPPER ====================


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


# ==================== CONVENIENCE FUNCTIONS ====================


def search_workflows(query: str, limit: int = 5) -> str:
    """Search for workflows by keyword"""
    return workflow_catalog("search", query, limit=limit)


def recommend_workflows(intent: str, limit: int = 3) -> str:
    """Get workflow recommendations based on your intent"""
    return workflow_catalog("recommend", intent, limit=limit)


def describe_workflow(workflow_id: str) -> str:
    """Get detailed information about a workflow"""
    return workflow_catalog("describe", workflow_id)
