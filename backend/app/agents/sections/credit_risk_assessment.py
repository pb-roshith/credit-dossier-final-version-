"""Credit Risk Assessment section agent."""

from app.agents.base_agent import BaseSectionAgent


class CreditRiskAssessmentAgent(BaseSectionAgent):
    section_key = "credit_risk_assessment"
    system_prompt = """You are drafting the **Credit Risk Assessment** section.
Provide a comprehensive risk assessment:
- Internal credit rating and methodology
- Key risk drivers and their probability
- Probability of Default (PD) assessment
- Loss Given Default (LGD) considerations
- Expected Loss computation
- Risk-weighted asset implications
- Rating migration analysis
Be precise with risk terminology. Present risk grade with justification."""
