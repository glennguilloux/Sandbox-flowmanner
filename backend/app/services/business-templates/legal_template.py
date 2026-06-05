"""
Legal Agent Template
Contract analysis, clause extraction, risk scoring
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ContractClause:
    """Extracted contract clause"""
    clause_type: str
    content: str
    position: int
    risk_level: RiskLevel = RiskLevel.LOW
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ContractAnalysis:
    """Complete contract analysis result"""
    document_id: str
    overall_risk: RiskLevel
    clauses: list[ContractClause]
    summary: str
    key_terms: dict[str, Any]
    red_flags: list[str]
    recommendations: list[str]


class LegalAgentTemplate:
    """Legal domain agent template"""
    
    PERSONALITY = """You are a Legal Analysis Specialist with expertise in:
- Contract law and compliance
- Risk assessment and mitigation
- Regulatory requirements
- Legal document review

Your role is to analyze legal documents, identify risks, and provide actionable recommendations.
Always be thorough, precise, and cite specific clauses when making observations."""
    
    TOOLS = [
        "document_processor",
        "clause_extractor",
        "risk_scorer",
        "compliance_checker"
    ]
    
    MEMORY_CONFIG = {
        "enable_long_term": True,
        "context_window": 16000,
        "remember_precedents": True
    }
    
    PROMPT_LIBRARY = {
        "contract_review": """Analyze this contract for:
1. Key terms and obligations
2. Risk factors (liability, termination, indemnification)
3. Compliance issues
4. Missing standard clauses
5. Recommendations for improvement

Contract text:
{contract_text}""",
        
        "clause_extraction": """Extract and categorize all clauses from this legal document:

Document:
{document_text}

For each clause, identify:
- Type (e.g., termination, liability, payment, confidentiality)
- Key parties affected
- Risk level
- Any ambiguous language""",
        
        "risk_assessment": """Assess the legal risk of the following:

{content}

Consider:
1. Regulatory compliance
2. Liability exposure
3. Enforceability
4. Precedent implications

Provide a risk score (1-10) and justification."""
    }
    
    def __init__(self):
        self.name = "Legal Agent"
        self.domain = "legal"
    
    def get_config(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "personality": self.PERSONALITY,
            "tools": self.TOOLS,
            "memory_config": self.MEMORY_CONFIG,
            "prompt_library": self.PROMPT_LIBRARY
        }
    
    async def analyze_contract(self, contract_text: str) -> ContractAnalysis:
        """Analyze a contract using the LLM infrastructure."""
        error_msg = None
        try:
            from app.services.model_router import get_model_router

            router = get_model_router()

            # Build analysis prompt
            system_prompt = self.PERSONALITY
            user_prompt = self.PROMPT_LIBRARY["contract_review"].format(
                contract_text=contract_text[:8000]  # Truncate for token limits
            )

            result = await router.route_request(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model_id="deepseek-v4-flash",
            )

            if result.get("success"):
                response_text = result.get("response", "")
                # Parse LLM response into structured analysis
                return self._parse_analysis_response(contract_text[:50], response_text)
            else:
                error_msg = f"LLM returned success=false: {result.get('response', 'no response')[:200]}"

        except ImportError:
            error_msg = "LLM infrastructure not available for contract analysis"
            logger.warning(error_msg)
        except Exception as e:
            error_msg = f"Contract analysis failed: {e}"
            logger.error(error_msg)

        # Fallback: extract what we can with basic text parsing
        extracted = self._basic_extract_info(contract_text)
        return ContractAnalysis(
            document_id=extracted.get("document_id", contract_text[:50].strip() or "unknown"),
            overall_risk=RiskLevel.MEDIUM,
            clauses=extracted.get("clauses", []),
            summary=(
                f"Analysis incomplete — {error_msg or 'unknown error'}. "
                f"Basic text extraction found {len(extracted.get('clauses', []))} clause(s), "
                f"{len(extracted.get('key_terms', {}))} key term(s)."
            ),
            key_terms=extracted.get("key_terms", {}),
            red_flags=extracted.get("red_flags", []),
            recommendations=[
                "Enable LLM infrastructure for full contract analysis",
                "Review the extracted terms manually for accuracy",
            ],
        )

    def _parse_analysis_response(
        self, doc_id: str, response: str
    ) -> ContractAnalysis:
        """Parse LLM response into structured ContractAnalysis."""
        try:
            # Strip markdown code fences that LLMs commonly wrap JSON in
            clean = re.sub(r'```(?:json)?\s*\n?', '', response)
            clean = re.sub(r'\n?\s*```', '', clean)
            # Try JSON parsing first
            data = json.loads(clean)
            return ContractAnalysis(
                document_id=doc_id,
                overall_risk=RiskLevel(data.get("overall_risk", "medium")),
                clauses=[
                    ContractClause(
                        clause_type=c.get("type", "unknown"),
                        content=c.get("content", ""),
                        position=c.get("position", 0),
                        risk_level=RiskLevel(c.get("risk_level", "low")),
                        issues=c.get("issues", []),
                        recommendations=c.get("recommendations", []),
                    )
                    for c in data.get("clauses", [])
                ],
                summary=data.get("summary", "Analysis completed"),
                key_terms=data.get("key_terms", {}),
                red_flags=data.get("red_flags", []),
                recommendations=data.get("recommendations", []),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            # Fall back to text-based parsing
            return ContractAnalysis(
                document_id=doc_id,
                overall_risk=RiskLevel.MEDIUM,
                clauses=[],
                summary=response[:500],
                key_terms={},
                red_flags=[],
                recommendations=[],
            )

    def _basic_extract_info(self, contract_text: str) -> dict[str, Any]:
        """Extract basic info from contract text using regex & keyword matching.

        Used as a fallback when the primary LLM analysis fails.
        Returns a dict compatible with ContractAnalysis fields.
        """
        result: dict[str, Any] = {
            "document_id": contract_text[:50].strip() or "unknown",
            "clauses": [],
            "key_terms": {},
            "red_flags": [],
        }

        if not contract_text or not contract_text.strip():
            result["red_flags"].append("Contract text is empty — no information could be extracted")
            return result

        # --- Parties ---
        # Pattern: "between [Party A] (the \"X\") and [Party B] (the \"Y\")"
        # Also: "Agreement made by and between ... and ..."
        parties = []
        party_patterns = [
            r"between\s+(.+?)(?:\s+\([\"'](.+?)[\"']\))?\s+and\s+(.+?)(?:\s+\([\"'](.+?)[\"']\))?[\s\.]",
            r"by and between\s+(.+?)(?:\s+\([\"'](.+?)[\"']\))?\s+and\s+(.+?)(?:\s+\([\"'](.+?)[\"']\))?[\s\.]",
            r"(?:Party|party)\s+A[:\s]+(.+)",
            r"(?:Party|party)\s+B[:\s]+(.+)",
        ]
        for pat in party_patterns:
            match = re.search(pat, contract_text, re.IGNORECASE)
            if match:
                groups = [g for g in match.groups() if g]
                parties.extend(groups)
        if parties:
            unique_parties = list(dict.fromkeys(p.strip() for p in parties if p.strip()))
            result["key_terms"]["parties"] = unique_parties[:6]  # cap at 6
        else:
            # Broader fallback: look for company-like names near "agreement"
            company_hits = re.findall(
                r'(?:^|\n)\s*([A-Z][A-Za-z0-9\s,\.&]+(?:Inc\.?|LLC|Ltd\.?|Corp\.?|GmbH|PLC|Pty\s+Ltd|Limited|Company|Corporation|Co\.))',
                contract_text[:2000],
            )
            if company_hits:
                result["key_terms"]["potential_parties"] = [h.strip() for h in company_hits[:4]]

        # --- Dates ---
        dates = {}
        # Effective Date
        eff_match = re.search(
            r"(?:Effective|Execution|Commencement)\s*[Dd]ate[:\s]*([A-Z][a-z]+ \d{1,2},?\s*\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            contract_text,
        )
        if eff_match:
            dates["effective_date"] = eff_match.group(1).strip()

        # Termination / Expiration
        term_match = re.search(
            r"(?:Termination|Expiration|End)\s*[Dd]ate[:\s]*([A-Z][a-z]+ \d{1,2},?\s*\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            contract_text,
        )
        if term_match:
            dates["termination_date"] = term_match.group(1).strip()

        # Generic date mentions (ISO or US format)
        iso_dates = re.findall(r"\d{4}-\d{2}-\d{2}", contract_text)
        us_dates = re.findall(r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}", contract_text)
        if not dates.get("effective_date") and us_dates:
            dates["mentioned_date"] = us_dates[0].strip()

        if dates:
            result["key_terms"]["dates"] = dates

        # --- Key Sections / Clauses ---
        clauses = []
        section_keywords = [
            "term", "termination", "payment", "confidentiality", "indemnification",
            "liability", "warranty", "governing law", "jurisdiction", "dispute",
            "assignment", "force majeure", "non-compete", "non-solicit",
            "intellectual property", "data protection", "privacy", "audit",
            "insurance", "representation", "covenant", "default", "remedy",
        ]
        seen_sections = set()
        for keyword in section_keywords:
            # Match section headings like "3. Term" or "Term and Termination" or "Section 5: Payment"
            pattern = re.compile(
                r"(?:^|\n)\s*(?:\d+\.?\s*|Section\s+\d+[\.:]\s*|Article\s+\d+[\.:]\s*)?" +
                re.escape(keyword) +
                r"(?:\s+and\s+\w+)?[\s:\.]",
                re.IGNORECASE,
            )
            match = pattern.search(contract_text)
            if match and keyword not in seen_sections:
                seen_sections.add(keyword)
                start = match.start()
                # Grab the surrounding paragraph (~200 chars after heading)
                snippet_start = max(0, match.end())
                snippet = contract_text[snippet_start:snippet_start + 200].strip()
                snippet = re.sub(r"\s+", " ", snippet)[:200]

                clauses.append(ContractClause(
                    clause_type=keyword.title(),
                    content=snippet,
                    position=start,
                    risk_level=RiskLevel.LOW,
                    issues=[],
                    recommendations=[],
                ))

        result["clauses"] = clauses

        # --- Monetary amounts ---
        amounts = re.findall(
            r"\$[\d,]+(?:\.\d{2})?(?:\s*(?:thousand|million|billion|k|m|b))?\s*(?:USD|EUR|GBP)?(?:\s*per\s+(?:year|month|annum|unit))?",
            contract_text,
            re.IGNORECASE,
        )
        if amounts:
            result["key_terms"]["monetary_amounts"] = [a.strip() for a in amounts[:10]]

        # --- Governing Law ---
        gl_match = re.search(
            r"governing\s+law[:\s]+(?:the\s+)?(?:laws\s+of\s+)?([A-Z][A-Za-z\s]+?)(?:\.|;|$)",
            contract_text,
            re.IGNORECASE,
        )
        if gl_match:
            result["key_terms"]["governing_law"] = gl_match.group(1).strip()

        # --- Red Flags (basic heuristics) ---
        red_flag_patterns = [
            (r"\bconfidential\b", "Document marked as confidential"),
            (r"\bnon[- ]?compete\b", "Contains non-compete clause — verify enforceability"),
            (r"\bindemnif", "Indemnification clause present — review liability scope"),
            (r"(?:unlimited|uncapped)\s+(?:liability|indemnif)", "Unlimited liability clause — high-risk"),
            (r"auto[- ]?renew", "Automatic renewal clause — may extend without notice"),
            (r"(?:waive|waiver)\s+(?:jury|trial)", "Jury trial waiver — limits legal recourse"),
            (r"binding\s+arbitration", "Binding arbitration clause — limits litigation rights"),
            (r"force\s+majeure", "Force majeure clause — verify scope"),
            (r"entire\s+agreement", "Entire agreement / merger clause — may limit claims"),
        ]
        for pat, label in red_flag_patterns:
            if re.search(pat, contract_text, re.IGNORECASE) and label not in result["red_flags"]:
                result["red_flags"].append(label)

        return result
