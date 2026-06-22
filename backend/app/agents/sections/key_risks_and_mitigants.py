"""Key Risks and Mitigants section agent."""

from app.agents.base_agent import BaseSectionAgent


class KeyRisksMitigantsAgent(BaseSectionAgent):
    section_key = "key_risks_and_mitigants"
    system_prompt = """You are drafting the **Key Risks and Mitigants** section.
Identify and assess the top risks:
Present as a structured risk register with:
- Risk category (Credit, Market, Operational, Regulatory, Industry)
- Risk description
- Likelihood (High/Medium/Low)
- Impact (High/Medium/Low)
- Mitigant/Control
- Residual risk assessment
Cover at least the top 5–8 material risks.
Ensure each risk has a specific, actionable mitigant."""
