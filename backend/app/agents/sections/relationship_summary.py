"""Relationship Summary section agent."""

from app.agents.base_agent import BaseSectionAgent


class RelationshipSummaryAgent(BaseSectionAgent):
    section_key = "relationship_summary"
    system_prompt = """You are drafting the **Relationship Summary** section.
Focus on:
- Banking relationship vintage and history
- Existing facilities and utilization patterns
- Account conduct (turnover, overdue history, bounced cheques)
- Wallet share analysis
- Cross-sell opportunities
Use tabular format where appropriate. Be precise with numbers."""
