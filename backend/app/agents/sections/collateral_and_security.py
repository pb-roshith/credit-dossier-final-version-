"""Collateral and Security section agent."""

from app.agents.base_agent import BaseSectionAgent


class CollateralSecurityAgent(BaseSectionAgent):
    section_key = "collateral_and_security"
    system_prompt = """You are drafting the **Collateral and Security** section.
Detail the security package:
- Primary security (nature, value, valuation date)
- Collateral security (nature, value, margin)
- Security cover ratio computation
- Guarantee details (personal/corporate)
- Insurance coverage requirements
- Charge creation (type — hypothecation, mortgage, pledge)
- Valuation methodology and independent valuer details
Present security cover in tabular format."""
