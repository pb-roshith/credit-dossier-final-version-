"""Covenants and Conditions section agent."""

from app.agents.base_agent import BaseSectionAgent


class CovenantsConditionsAgent(BaseSectionAgent):
    section_key = "covenants_and_conditions"
    system_prompt = """You are drafting the **Covenants and Conditions** section.
Specify covenant framework:
- Financial covenants (with thresholds and testing frequency)
  - Minimum net worth, Maximum leverage, Minimum DSCR, etc.
- Non-financial covenants
  - Information covenants (financial submissions schedule)
  - Negative covenants (restrictions on borrowing, guarantees, dividends)
  - Affirmative covenants (maintenance of business, insurance)
- Conditions precedent to disbursement
- Conditions subsequent
Present in a structured table with testing frequency."""
