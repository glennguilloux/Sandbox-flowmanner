"""
Unified Agent - Intent Classification Only
"""

import re
from typing import Any


class IntentClassifier:
    """Fast intent classification for routing"""

    @staticmethod
    def classify(message: str) -> dict[str, Any]:
        """
        Classify message intent

        Returns:
            {
                "intent": "comfyui" | "n8n" | "catalog" | "general",
                "action": "generate" | "execute" | "search" | "chat",
                "details": {...}
            }
        """
        message_lower = message.lower()

        # Catalog intents (check FIRST to avoid conflicts)
        catalog_keywords = [
            "find",
            "search",
            "recommend",
            "suggest",
            "what",
            "how",
            "help",
            "catalog",
            "workflows",
        ]
        if any(k in message_lower for k in catalog_keywords):
            # But exclude if it's clearly a generation request
            # Only exclude if generation keywords appear WITH generation verbs
            generation_keywords = ["generate", "create", "make"]
            if not any(k in message_lower for k in generation_keywords):
                return {
                    "intent": "catalog",
                    "action": "search",
                    "details": {
                        "query": message,
                        "type": (
                            "recommend" if "recommend" in message_lower or "suggest" in message_lower else "search"
                        ),
                    },
                }

        # ComfyUI intents
        comfyui_keywords = [
            "generate",
            "create",
            "image",
            "photo",
            "picture",
            "3d",
            "model",
            "hero",
            "product",
            "background",
        ]
        if any(k in message_lower for k in comfyui_keywords):
            return {
                "intent": "comfyui",
                "action": "generate",
                "details": {
                    "type": IntentClassifier._get_comfyui_type(message),
                    "prompt": message,
                    "style": IntentClassifier._get_style(message),
                },
            }

        # n8n intents
        n8n_keywords = [
            "execute",
            "run",
            "workflow",
            "automation",
            "trigger",
            "schedule",
            "digest",
            "archive",
        ]
        if any(k in message_lower for k in n8n_keywords):
            return {
                "intent": "n8n",
                "action": "execute",
                "details": {
                    "workflow_id": IntentClassifier._extract_workflow_id(message),
                    "parameters": IntentClassifier._extract_parameters(message),
                },
            }

        # Default to general chat
        return {"intent": "general", "action": "chat", "details": {}}

    @staticmethod
    def _get_comfyui_type(message: str) -> str:
        """Extract ComfyUI workflow type from message"""
        msg = message.lower()
        if "hero" in msg or "background" in msg:
            return "hero-background"
        elif "product" in msg or "shot" in msg:
            return "product-shot"
        elif "3d" in msg or "model" in msg:
            return "3d-model"
        else:
            return "general"

    @staticmethod
    def _get_style(message: str) -> str:
        """Extract style from message"""
        msg = message.lower()
        if "modern" in msg:
            return "modern"
        elif "minimal" in msg:
            return "minimal"
        elif "dark" in msg:
            return "dark"
        elif "vibrant" in msg:
            return "vibrant"
        elif "professional" in msg:
            return "professional"
        else:
            return "modern"

    @staticmethod
    def _extract_workflow_id(message: str) -> str | None:
        """Extract workflow ID from message"""
        # Look for patterns like "workflow 123", "id 456", "123"
        patterns = [r"workflow\s+(\w+)", r"id\s+(\w+)", r"(\d{3,})"]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    @staticmethod
    def _extract_parameters(message: str) -> dict[str, Any]:
        """Extract parameters from message"""
        params = {}

        # Look for email
        email_match = re.search(r"[\w\.-]+@[\w\.-]+", message)
        if email_match:
            params["email"] = email_match.group(0)

        # Look for time patterns
        if "8am" in message.lower() or "8 am" in message.lower():
            params["time"] = "08:00"
        elif "2am" in message.lower() or "2 am" in message.lower():
            params["time"] = "02:00"

        return params
