"""Biotech Domain AI Assistant"""

from typing import Any

from ..base_domain_agent import BaseDomainAgent


class BiotechAgent(BaseDomainAgent):
    """
    Biotech-specific AI assistant for drug discovery,
    clinical trials, and regulatory affairs.
    """

    domain_name = "biotech"
    domain_icon = "🧬"
    domain_color = "#7ED321"
    domain_description = (
        "Biotech assistant for drug discovery, clinical trials, and regulatory affairs"
    )

    def get_system_prompt(self) -> str:
        return """You are a specialized biotech AI assistant with expertise in:

- Drug discovery and development pipelines
- Clinical trial design and analysis
- Regulatory affairs (FDA, EMA, PMDA)
- Pharmacology and toxicology
- Genomics and precision medicine
- Biomanufacturing and CMC
- Medical writing and documentation

Guidelines:
1. Always cite clinical data sources and study references
2. Highlight safety considerations and contraindications
3. Clarify regulatory requirements by jurisdiction
4. Present evidence-based conclusions with confidence levels
5. Note when additional preclinical/clinical data is needed

Remember: You provide informational assistance for research purposes. 
Always recommend consulting with qualified medical and regulatory professionals 
for clinical and regulatory decisions."""

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "trial_designer",
                "description": "Design clinical trial protocols",
                "parameters": {
                    "indication": "string",
                    "phase": "I|II|III",
                    "population": "dict",
                },
            },
            {
                "name": "regulatory_analyzer",
                "description": "Analyze regulatory requirements and pathways",
                "parameters": {
                    "product_type": "drug|biologic|device",
                    "jurisdiction": "FDA|EMA|PMDA",
                    "indication": "string",
                },
            },
            {
                "name": "literature_search",
                "description": "Search biomedical literature databases",
                "parameters": {
                    "query": "string",
                    "databases": ["PubMed", "ClinicalTrials.gov", "FDA"],
                },
            },
        ]

    def process_response(self, response: str) -> dict[str, Any]:
        return {
            "response": response,
            "domain": self.domain_name,
            "disclaimer": "This is for research purposes only. Consult qualified medical and regulatory professionals for clinical decisions.",
            "references_required": True,
        }

    def get_capabilities(self) -> list[str]:
        return [
            "Clinical trial design",
            "Regulatory pathway analysis",
            "Drug discovery support",
            "Literature review",
            "Safety profile assessment",
            "CMC documentation",
        ]

    async def run(self, query: str, context: dict[str, Any] = None) -> dict[str, Any]:
        """Execute a biotech query"""
        result = await super().run(query, context)
        result["disclaimer"] = (
            "This is for research purposes only. Consult qualified medical and regulatory professionals for clinical decisions."
        )
        result["capabilities"] = self.get_capabilities()
        return result
