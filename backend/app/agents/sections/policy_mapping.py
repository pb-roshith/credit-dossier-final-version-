"""Policy Mapping section agent."""

from app.agents.base_agent import BaseSectionAgent


class PolicyMappingAgent(BaseSectionAgent):
    section_key = "policy_mapping"
    system_prompt = """You are drafting the **Policy Mapping** section.
Map the proposal against the bank's credit policy:
- Exposure norms and single-borrower limits
- Sector exposure caps
- Rating-based eligibility
- Minimum margin requirements
- Documentation standards
- Any policy deviations with justification
- Regulatory compliance (RBI guidelines, Basel norms)
Flag deviations clearly with mitigation plans. Use a compliance checklist format."""
