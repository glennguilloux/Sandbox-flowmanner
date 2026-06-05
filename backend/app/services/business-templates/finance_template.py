"""
Finance Agent Template
Portfolio analysis, trend detection, report generation
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"


@dataclass
class PortfolioPosition:
    """A position in a portfolio"""

    symbol: str
    quantity: float
    avg_cost: float
    current_price: float
    market_value: float
    gain_loss: float
    gain_loss_percent: float


@dataclass
class PortfolioAnalysis:
    """Complete portfolio analysis"""

    total_value: float
    total_gain_loss: float
    positions: list[PortfolioPosition]
    allocation: dict[str, float]
    risk_metrics: dict[str, Any]
    recommendations: list[str]


class FinanceAgentTemplate:
    """Finance domain agent template"""

    PERSONALITY = """You are a Financial Analysis Specialist with expertise in:
- Portfolio management and analysis
- Market trend detection
- Risk assessment and management
- Financial reporting and forecasting

Your role is to analyze financial data, identify trends, and provide data-driven recommendations.
Always be analytical, objective, and support conclusions with data."""

    TOOLS = [
        "market_data",
        "portfolio_analyzer",
        "trend_detector",
        "risk_calculator",
        "report_generator",
    ]

    MEMORY_CONFIG = {
        "enable_long_term": True,
        "context_window": 8000,
        "remember_market_conditions": True,
    }

    PROMPT_LIBRARY = {
        "portfolio_analysis": """Analyze this portfolio:

{portfolio_data}

Provide:
1. Overall performance assessment
2. Risk analysis
3. Diversification evaluation
4. Recommendations for optimization""",
        "trend_detection": """Analyze the following market data for trends:

{market_data}

Identify:
1. Current trend direction
2. Key support/resistance levels
3. Momentum indicators
4. Potential reversal signals""",
        "financial_report": """Generate a financial report based on:

{financial_data}

Include:
1. Executive summary
2. Key metrics and KPIs
3. Period-over-period comparison
4. Outlook and recommendations""",
    }

    def __init__(self):
        self.name = "Finance Agent"
        self.domain = "finance"

    def get_config(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "personality": self.PERSONALITY,
            "tools": self.TOOLS,
            "memory_config": self.MEMORY_CONFIG,
            "prompt_library": self.PROMPT_LIBRARY,
        }
