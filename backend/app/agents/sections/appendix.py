"""Appendix section agent."""

from app.agents.base_agent import BaseSectionAgent


class AppendixAgent(BaseSectionAgent):
    section_key = "appendix"
    system_prompt = """You are drafting the **Appendix** section.
Compile supporting information:
- Detailed financial statements (if provided)
- Ratio computation worksheets
- Organogram / group structure diagram descriptions
- Key regulatory approvals and licenses
- Site visit observations (if available)
- Credit bureau report summary
- Any other supporting documentation
Organize clearly with numbered appendix items."""
