"""Legal Domain AI Assistant"""

from typing import Any

from ..base_domain_agent import BaseDomainAgent


class LegalAgent(BaseDomainAgent):
    """
    Legal-specific AI assistant for contract analysis, compliance,
    legal research, and document review.
    """
    
    domain_name = "legal"
    domain_icon = "⚖️"
    domain_color = "#4A90E2"
    domain_description = "Legal assistant for contracts, compliance, and legal research"
    
    def get_system_prompt(self) -> str:
        return """You are a specialized legal AI assistant with expertise in:

- Contract analysis and review
- Regulatory compliance (GDPR, HIPAA, SOX, etc.)
- Legal research and case law
- Intellectual property matters
- Corporate governance
- Risk assessment and mitigation

Guidelines:
1. Always cite relevant laws, regulations, or case precedents when applicable
2. Highlight potential risks and liabilities in contracts
3. Suggest specific clauses or amendments when reviewing documents
4. Clarify jurisdiction-specific considerations
5. Recommend consulting with a licensed attorney for binding legal advice

Remember: You provide informational assistance, not legal advice. Always recommend 
professional legal counsel for critical decisions."""
    
    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "contract_analyzer",
                "description": "Analyze contracts for risks, missing clauses, and compliance issues",
                "parameters": {
                    "contract_text": "string",
                    "analysis_type": "risk|compliance|completeness"
                }
            },
            {
                "name": "legal_research",
                "description": "Search legal databases for relevant case law and statutes",
                "parameters": {
                    "query": "string",
                    "jurisdiction": "string",
                    "date_range": "optional string"
                }
            },
            {
                "name": "compliance_checker",
                "description": "Check compliance against specific regulations",
                "parameters": {
                    "document": "string",
                    "regulations": ["GDPR", "HIPAA", "SOX", "PCI-DSS"]
                }
            }
        ]
    
    def process_response(self, response: str) -> dict[str, Any]:
        return {
            "response": response,
            "domain": self.domain_name,
            "disclaimer": "This is informational only. Consult a licensed attorney for legal advice.",
            "citations_required": True,
        }
    
    def get_capabilities(self) -> list[str]:
        return [
            "Contract analysis and review",
            "Regulatory compliance checking",
            "Legal research assistance",
            "Risk assessment",
            "Clause drafting suggestions",
            "Jurisdiction-specific guidance",
        ]
    
    async def run(self, query: str, context: dict[str, Any] = None) -> dict[str, Any]:
        """Execute a legal query"""
        result = await super().run(query, context)
        result["disclaimer"] = "This is informational only. Consult a licensed attorney for legal advice."
        result["capabilities"] = self.get_capabilities()
        return result
