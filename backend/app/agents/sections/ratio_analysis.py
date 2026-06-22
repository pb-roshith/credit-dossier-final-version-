"""Ratio Analysis section agent."""

from app.agents.base_agent import BaseSectionAgent


class RatioAnalysisAgent(BaseSectionAgent):
    section_key = "ratio_analysis"
    system_prompt = """You are drafting the **Ratio Analysis** section.
Present and analyze key financial ratios across periods:
- Leverage ratios: Debt/Equity, Debt/EBITDA, Net Debt/EBITDA
- Coverage ratios: Interest Coverage, DSCR, Fixed Charge Coverage
- Liquidity ratios: Current Ratio, Quick Ratio
- Profitability ratios: ROE, ROA, EBITDA Margin, PAT Margin
- Efficiency ratios: Inventory Days, Debtor Days, Creditor Days
Format as a table with trend arrows. Explain deviations from benchmarks."""
