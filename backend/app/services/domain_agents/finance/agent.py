"""Finance Domain AI Assistant"""

from typing import Any

from ..base_domain_agent import BaseDomainAgent


class FinanceAgent(BaseDomainAgent):
    """
    Finance-specific AI assistant for financial analysis,
    investment research, and regulatory compliance.
    """

    domain_name = "finance"
    domain_icon = "💰"
    domain_color = "#F5A623"
    domain_description = "Finance assistant for analysis, investments, and compliance"

    def get_system_prompt(self) -> str:
        return """You are a specialized finance AI assistant with expertise in:

- Financial statement analysis and valuation
- Investment research and portfolio management
- Risk assessment and management
- Regulatory compliance (SEC, FINRA, Basel III)
- Market analysis and forecasting
- Corporate finance and M&A
- Quantitative finance and modeling

Guidelines:
1. Always cite data sources and methodologies used
2. Highlight key assumptions and limitations in analyses
3. Present both bullish and bearish scenarios when relevant
4. Include sensitivity analyses for projections
5. Clarify that this is informational, not investment advice

Remember: You provide informational assistance, not financial advice. 
Always recommend consulting with a licensed financial advisor for investment decisions."""

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "financial_analyzer",
                "description": "Analyze financial statements and compute key ratios",
                "parameters": {
                    "statements": "dict",
                    "analysis_type": "ratio|dcf|comparable",
                },
            },
            {
                "name": "risk_assessor",
                "description": "Assess financial and market risks",
                "parameters": {
                    "portfolio": "dict",
                    "risk_metrics": ["var", "sharpe", "beta", "volatility"],
                },
            },
            {
                "name": "compliance_checker",
                "description": "Check compliance against financial regulations",
                "parameters": {
                    "document": "string",
                    "regulations": ["SEC", "FINRA", "Basel", "MiFID"],
                },
            },
        ]

    def process_response(self, response: str) -> dict[str, Any]:
        return {
            "response": response,
            "domain": self.domain_name,
            "disclaimer": "This is informational only. Consult a licensed financial advisor for investment decisions.",
            "data_sources_required": True,
        }

    def get_capabilities(self) -> list[str]:
        return [
            "Financial statement analysis",
            "Investment research",
            "Risk assessment",
            "Valuation modeling",
            "Regulatory compliance",
            "Market analysis",
        ]

    async def run(self, query: str, context: dict[str, Any] = None) -> dict[str, Any]:
        """Execute a finance query"""
        result = await super().run(query, context)
        result["disclaimer"] = (
            "This is informational only. Consult a licensed financial advisor for investment decisions."
        )
        result["capabilities"] = self.get_capabilities()
        return result
