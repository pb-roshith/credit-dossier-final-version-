"""Financial Analysis section agent."""

from app.agents.base_agent import BaseSectionAgent


class FinancialAnalysisAgent(BaseSectionAgent):
    section_key = "financial_analysis"
    system_prompt = """You are drafting the **Financial Analysis** section.
Analyze the borrower's financials across 3 years (or available period):
- Revenue trends and growth drivers
- EBITDA margins and profitability
- Balance sheet strength (net worth, debt levels)
- Working capital management
- Capital expenditure and investment patterns
Present data in tabular format. Highlight key trends and inflection points.
Use financial terminology precisely (CAGR, YoY, QoQ where relevant)."""
