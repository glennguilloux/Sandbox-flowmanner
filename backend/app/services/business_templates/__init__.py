"""
Specialized Agent Templates (Phase E3)

Pre-configured agent templates for specific domains:
- Legal: contract analysis, clause extraction, risk scoring
- Finance: portfolio analysis, trend detection, report generation
- Support: ticket classification, response drafting, escalation rules
"""

from .finance_template import FinanceAgentTemplate
from .legal_template import LegalAgentTemplate
from .support_template import SupportAgentTemplate

__all__ = ["FinanceAgentTemplate", "LegalAgentTemplate", "SupportAgentTemplate"]
