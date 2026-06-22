"""ESG Analysis section agent."""

from app.agents.base_agent import BaseSectionAgent


class ESGAnalysisAgent(BaseSectionAgent):
    section_key = "esg_analysis"
    system_prompt = """You are drafting the **ESG Analysis** section.
Evaluate Environmental, Social, and Governance factors:
- Environmental: Carbon footprint, waste management, regulatory compliance
- Social: Labor practices, community impact, supply chain standards
- Governance: Board composition, audit quality, related party transactions
- ESG rating (if available) and industry benchmarking
- Material ESG risks and their impact on creditworthiness
- ESG improvement plan and commitments
Use recognized ESG frameworks (GRI, SASB) where applicable."""
