"""Cash Flow Analysis section agent."""

from app.agents.base_agent import BaseSectionAgent


class CashFlowAnalysisAgent(BaseSectionAgent):
    section_key = "cash_flow_analysis"
    system_prompt = """You are drafting the **Cash Flow Analysis** section.
Analyze the borrower's cash flows:
- Operating cash flow quality and sustainability
- Free cash flow generation
- Investing activities and capex patterns
- Financing flows (debt raised/repaid, dividends)
- DSCR computation and adequacy
- Projected cash flows vs. repayment schedule
Highlight cash flow adequacy relative to debt servicing obligations."""
