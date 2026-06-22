"""Qualitative Assessment section agent."""

from app.agents.base_agent import BaseSectionAgent


class QualitativeAssessmentAgent(BaseSectionAgent):
    section_key = "qualitative_assessment"
    system_prompt = """You are drafting the **Qualitative Assessment** section.
Evaluate qualitative factors:
- Management quality and governance standards
- Corporate governance framework
- Succession planning
- Business continuity arrangements
- Reputation and market standing
- Regulatory compliance track record
- Key management personnel assessment
Use a structured scorecard approach where possible."""
