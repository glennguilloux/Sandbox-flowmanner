"""
Support Agent Template
Ticket classification, response drafting, escalation rules
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TicketCategory(str, Enum):
    TECHNICAL = "technical"
    BILLING = "billing"
    ACCOUNT = "account"
    FEATURE_REQUEST = "feature_request"
    BUG_REPORT = "bug_report"
    GENERAL = "general"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class SupportTicket:
    """A support ticket"""
    ticket_id: str
    subject: str
    description: str
    category: TicketCategory
    priority: Priority
    suggested_response: str
    escalation_needed: bool
    related_articles: list[str]


class SupportAgentTemplate:
    """Support domain agent template"""
    
    PERSONALITY = """You are a Customer Support Specialist with expertise in:
- Ticket classification and routing
- Response drafting and personalization
- Escalation decision-making
- Knowledge base utilization

Your role is to efficiently handle support requests, provide accurate responses, and know when to escalate.
Always be helpful, empathetic, and solution-oriented."""
    
    TOOLS = [
        "ticket_classifier",
        "response_drafter",
        "knowledge_base",
        "escalation_manager",
        "sentiment_analyzer"
    ]
    
    MEMORY_CONFIG = {
        "enable_long_term": True,
        "context_window": 4000,
        "remember_customer_history": True
    }
    
    PROMPT_LIBRARY = {
        "classify_ticket": """Classify this support ticket:

Subject: {subject}
Description: {description}

Determine:
1. Category (technical, billing, account, feature_request, bug_report, general)
2. Priority (low, medium, high, urgent)
3. Estimated resolution time
4. Required expertise""",
        
        "draft_response": """Draft a response to this support ticket:

Ticket: {ticket_info}
Customer History: {customer_history}
Knowledge Base Articles: {kb_articles}

Guidelines:
- Be empathetic and professional
- Provide clear, actionable steps
- Anticipate follow-up questions
- Include relevant resources""",
        
        "escalation_check": """Determine if this ticket needs escalation:

{ticket_info}

Consider:
1. Complexity beyond first-line support
2. VIP customer status
3. Time-sensitive issue
4. Customer sentiment
5. Previous resolution attempts

Respond with ESCALATE or RESOLVE and reasoning."""
    }
    
    def __init__(self):
        self.name = "Support Agent"
        self.domain = "support"
    
    def get_config(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "personality": self.PERSONALITY,
            "tools": self.TOOLS,
            "memory_config": self.MEMORY_CONFIG,
            "prompt_library": self.PROMPT_LIBRARY
        }
