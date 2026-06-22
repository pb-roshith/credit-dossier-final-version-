"""Facility Structure section agent."""

from app.agents.base_agent import BaseSectionAgent


class FacilityStructureAgent(BaseSectionAgent):
    section_key = "facility_structure"
    system_prompt = """You are drafting the **Facility Structure** section.
Detail the proposed facility:
- Facility type and purpose
- Sanctioned limit and sub-limits
- Tenure and availability period
- Pricing and fees (interest rate, processing fee, commitment fee)
- Drawdown schedule and conditions precedent
- Repayment schedule (amortization table if applicable)
- End-use monitoring plan
Present in a structured term-sheet format."""
