"""Industry Analysis section agent."""

from app.agents.base_agent import BaseSectionAgent


class IndustryAnalysisAgent(BaseSectionAgent):
    section_key = "industry_analysis"
    system_prompt = """You are drafting the **Industry Analysis** section.
Provide a comprehensive industry view covering:
- Industry size, growth trends, and outlook
- Key demand-supply drivers
- Competitive landscape and Porter's analysis
- Regulatory environment
- Where the borrower sits within the industry cycle
- Peer comparison (if data available)
Use formal analytical language with data-backed assertions."""
