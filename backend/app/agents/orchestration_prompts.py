"""
Orchestration Prompts — fixed system prompt + 16 section-specific user prompts.

The orchestration agent is a single Mistral Agent (mistral-large-latest) with a
fixed system prompt. For each section, a dynamic user prompt is sent that describes
what documents and data the section needs.

The agent analyzes MCP document summaries and returns a structured JSON strategy
that the section agent uses to guide its library search.
"""

from __future__ import annotations

# ── Fixed System Prompt (set as agent instructions at creation) ──────────

ORCHESTRATION_SYSTEM_PROMPT = """\
You are a Credit Dossier Document Orchestrator at a leading commercial bank.

ROLE:
You analyze available document summaries and determine which documents are most
relevant for generating a specific section of a credit pitch book.

WORKFLOW:
1. Read the SECTION REQUIREMENTS to understand what data the section needs.
2. Analyze the AVAILABLE DOCUMENT SUMMARIES to identify relevant sources.
3. Match documents to the section's specific data requirements.
4. Output a structured JSON strategy.

OUTPUT FORMAT — Return ONLY a valid JSON object, nothing else:
{
    "recommended_documents": [
        {"title": "<document name>", "relevance": "<why needed>", "priority": "high|medium|low"}
    ],
    "priority_data_points": ["<specific data point 1>", "<specific data point 2>"],
    "search_queries": ["<search query for library>", "<another search query>"],
    "confidence": <float 0.0 to 1.0>,
    "gaps": ["<missing data type 1>", "<missing data type 2>"],
    "strategy_summary": "<2-3 sentence strategy for the section agent>"
}

RULES:
1. Only recommend documents that GENUINELY contain relevant data for the section.
2. Rank by relevance — most important documents first with priority "high".
3. Be specific about what data points to extract from each document.
4. If no documents match, return empty recommended_documents with confidence=0.
5. The search_queries should help the section agent find relevant passages in its document library.
6. Consider that manually uploaded documents in the Mistral Library may also be available beyond what is shown in summaries.
7. Return ONLY the JSON object. No markdown fences, no explanation outside JSON.
8. Never fabricate document titles — only reference documents from the summaries provided.
"""


# ── Section-Specific User Prompt Templates ──────────────────────────────
# Each template has {deal_context} and {document_summaries} placeholders.

SECTION_USER_PROMPTS: dict[str, str] = {

    "executive_summary": """\
SECTION: Executive Summary
DESCRIPTION: High-level overview of client, facility, and credit recommendation.
REQUIRED DATA:
- Revenue, EBITDA, PAT, net worth (latest year)
- Credit ratings (internal and external)
- Business overview and industry positioning
- Proposed facility details (amount, tenor, pricing, security)
- Key credit strengths and risk snapshot
- Relationship vintage and track record

PRIORITY DOCUMENT TYPES: Annual reports, financial summaries, credit rating reports, \
CRM/relationship data, management presentations

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents that provide a comprehensive overview for the Executive Summary. \
Prioritize documents with financial highlights, credit ratings, and business overview.""",


    "client_overview": """\
SECTION: Client Overview
DESCRIPTION: Comprehensive background on the borrower entity and group.
REQUIRED DATA:
- Company history, incorporation date, legal entity details
- Group structure (parent, subsidiaries, associates)
- Promoter and management profiles with track record
- Business model and product/service portfolio
- Key customers, suppliers, and geographical presence
- Governance structure and board composition

PRIORITY DOCUMENT TYPES: Company registration docs, annual reports (company info sections), \
KYC documents, CRM records, management bios, public filings

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents containing company background, management details, and group structure.""",


    "relationship_summary": """\
SECTION: Relationship Summary
DESCRIPTION: Banking relationship vintage, wallet share, and account conduct.
REQUIRED DATA:
- Relationship vintage (years with the bank)
- Existing facilities (product, limit, outstanding, utilisation%)
- Account conduct (overdue history, LC devolvement, cheque bounces)
- Wallet share trends (current vs. potential)
- Revenue generated from the relationship
- Peer bank exposure and consortium details

PRIORITY DOCUMENT TYPES: CRM data, transaction history, account statements, \
relationship/RM reports, internal banking records

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with banking relationship data, account conduct, and existing facilities.""",


    "industry_analysis": """\
SECTION: Industry Analysis
DESCRIPTION: Industry outlook, competitive landscape, and client positioning.
REQUIRED DATA:
- Industry overview and macro context
- Market size, growth rates, CAGR
- Industry cycle position (expansion/peak/contraction)
- Competitive landscape and key players
- Regulatory environment and policy changes
- Client's market share and positioning within industry

PRIORITY DOCUMENT TYPES: Industry/sector reports, rating agency sector notes, \
market research, annual reports (industry sections), IBEF reports

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with industry data, competitive landscape, and sector outlook.""",


    "financial_analysis": """\
SECTION: Financial Analysis
DESCRIPTION: Three-year financial trend analysis with key drivers.
REQUIRED DATA:
- Revenue, EBITDA, PAT across 3+ years
- Revenue breakdown by segment/product
- EBITDA margins and PAT margins trend
- Net worth, total debt, debt-equity ratio
- Working capital (debtors, inventory, creditors in days)
- Capital expenditure and investment patterns
- Balance sheet line items

PRIORITY DOCUMENT TYPES: Audited financial statements, annual reports, quarterly results, \
MIS data, management accounts, projected financials

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with detailed financial statements and P&L data across multiple years. \
Prioritize audited financials over management accounts.""",


    "ratio_analysis": """\
SECTION: Ratio Analysis
DESCRIPTION: Key financial ratios across leverage, coverage, liquidity, profitability.
REQUIRED DATA:
- Leverage ratios: D/E, TOL/TNW, Debt/EBITDA (3+ years)
- Coverage ratios: ICR, DSCR (3+ years)
- Liquidity ratios: Current ratio, Quick ratio
- Profitability ratios: ROCE, ROE, EBITDA margin, PAT margin
- Efficiency ratios: Debtor days, Inventory days, Creditor days
- Industry benchmarks for comparison

PRIORITY DOCUMENT TYPES: Financial statements, ratio computation sheets, \
rating reports (ratio sections), bank analysis sheets, industry benchmark data

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents containing computed financial ratios or raw data to compute them. \
Prioritize rating reports that include ratio analysis.""",


    "cash_flow_analysis": """\
SECTION: Cash Flow Analysis
DESCRIPTION: Operating, investing, financing cash flows and repayment capacity.
REQUIRED DATA:
- Cash flow from operations (CFO) across 3+ years
- Cash flow from investing (CFI) and financing (CFF)
- Free cash flow computation
- CFO/EBITDA conversion ratio
- DSCR computation and adequacy
- Projected cash flows (if available)
- Debt repayment schedule

PRIORITY DOCUMENT TYPES: Cash flow statements, financial statements, \
DSCR computations, projected financials, debt schedules

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with cash flow statements and DSCR data. \
Projected financials are highly valuable for repayment capacity assessment.""",


    "qualitative_assessment": """\
SECTION: Qualitative Assessment
DESCRIPTION: Management quality, governance, business sustainability assessment.
REQUIRED DATA:
- Management quality and track record
- Corporate governance practices and board composition
- Succession planning and key-person risk
- Business sustainability and competitive moat
- Regulatory compliance history
- Stakeholder and labour relations
- Technology and operational infrastructure

PRIORITY DOCUMENT TYPES: RM/relationship notes, KYC documents, governance reports, \
annual reports (governance sections), ESG reports, public filings, news

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with qualitative data on management, governance, and business quality.""",


    "credit_risk_assessment": """\
SECTION: Credit Risk Assessment
DESCRIPTION: Internal rating, external ratings, and risk drivers.
REQUIRED DATA:
- Internal credit rating and risk grade
- External ratings (CRISIL/ICRA/CARE/Fitch/Moody's) with outlook
- Key risk drivers (top 5) with severity
- Rating triggers and watchlist items
- Risk migration history
- PD/LGD/Expected loss (if available)
- Risk-adjusted return assessment

PRIORITY DOCUMENT TYPES: Internal rating model outputs, credit rating reports, \
risk assessment sheets, RBI guidelines, risk register

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with credit ratings, risk assessments, and rating rationale.""",


    "facility_structure": """\
SECTION: Facility Structure
DESCRIPTION: Complete facility terms, sub-limits, pricing, and conditions.
REQUIRED DATA:
- Facility type, total limit, sub-limits
- Tenor and repayment schedule
- Pricing (base rate + spread, reset frequency)
- Moratorium period (if any)
- Conditions precedent and subsequent
- End-use of funds
- Drawing power/margin requirements

PRIORITY DOCUMENT TYPES: Term sheets, deal sheets, sanction letters, \
facility agreements, internal credit approval notes

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with facility terms, pricing, and deal structure details.""",


    "policy_mapping": """\
SECTION: Policy Mapping
DESCRIPTION: Mapping deal against credit policy parameters and regulatory norms.
REQUIRED DATA:
- Credit policy parameter thresholds
- Exposure norms (sector caps, group limits)
- Rating thresholds for approval
- Policy deviations with justification
- Delegation of authority (DOA) mapping
- Regulatory compliance (RBI/NHB/SEBI)
- Exposure concentration analysis

PRIORITY DOCUMENT TYPES: Credit policy documents, lending guidelines, \
regulatory circulars, internal norms, deviation approval notes

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with credit policy norms, regulatory guidelines, and deviation records.""",


    "collateral_and_security": """\
SECTION: Collateral and Security
DESCRIPTION: Security package, valuation, insurance, and charge details.
REQUIRED DATA:
- Primary and collateral security details
- Asset valuations with valuer certification
- Security cover ratio computation
- Insurance coverage and adequacy
- Charge type (mortgage/hypothecation/pledge)
- Personal/corporate guarantee details
- Priority of charge

PRIORITY DOCUMENT TYPES: Valuation reports, security documents, property records, \
insurance policies, charge creation documents, guarantee deeds

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with collateral valuations, security details, and insurance data.""",


    "covenants_and_conditions": """\
SECTION: Covenants and Conditions
DESCRIPTION: Financial and non-financial covenants with thresholds.
REQUIRED DATA:
- Financial covenants (ratio thresholds, testing frequency)
- Non-financial covenants and reporting requirements
- Negative covenants (dividend, capex, debt restrictions)
- Event of default triggers
- Cure periods and grace periods
- Historical covenant compliance record

PRIORITY DOCUMENT TYPES: Term sheets, sanction letters, covenant schedules, \
facility agreements, historical compliance reports

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with covenant schedules, compliance records, and facility terms.""",


    "esg_analysis": """\
SECTION: ESG Analysis
DESCRIPTION: Environmental, Social, and Governance risk assessment.
REQUIRED DATA:
- Environmental: emissions, carbon footprint, waste, climate risk
- Social: labour practices, community impact, diversity, human rights
- Governance: board composition, transparency, ethics, compliance
- ESG ratings from external agencies
- Material ESG risks for the industry
- ESG-linked pricing opportunities

PRIORITY DOCUMENT TYPES: ESG/sustainability reports, environmental assessments, \
social audit reports, governance reports, ESG rating agency data

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with ESG data, sustainability metrics, and governance details.""",


    "key_risks_and_mitigants": """\
SECTION: Key Risks and Mitigants
DESCRIPTION: Top risks ranked by severity with mitigation strategies.
REQUIRED DATA:
- Business risks (market, competition, concentration)
- Financial risks (liquidity, leverage, forex)
- Industry risks (cyclicality, regulation, disruption)
- Management risks (key-person, succession, governance)
- Operational risks (technology, supply chain, execution)
- Risk severity, likelihood, and impact assessment
- Existing mitigants and residual risk

PRIORITY DOCUMENT TYPES: Risk registers, credit assessment reports, industry reports, \
financial statements, internal risk analysis, rating reports

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents that highlight risks, challenges, and mitigating factors.""",


    "appendix": """\
SECTION: Appendix
DESCRIPTION: Supporting tables, schedules, and reference data.
REQUIRED DATA:
- Supplementary financial schedules
- Additional data tables not in main sections
- Glossary of key terms
- Document index and data sources
- Supporting analysis and workpapers

PRIORITY DOCUMENT TYPES: All available documents — any supplementary data tables, \
financial schedules, reference materials

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select any documents with supplementary data, reference tables, or additional details \
that complement the main dossier sections.""",
}


def build_orchestration_user_prompt(
    section_key: str,
    deal_context: str,
    document_summaries: str,
) -> str:
    """
    Build the dynamic user prompt for the orchestration agent.

    Args:
        section_key: The section being generated (e.g. "executive_summary")
        deal_context: Pre-built deal context string (section-specific fields)
        document_summaries: Document summaries from MCP server

    Returns:
        Formatted user prompt string
    """
    template = SECTION_USER_PROMPTS.get(section_key)
    if not template:
        # Fallback for unknown sections
        template = (
            "SECTION: {section_key}\n"
            "Select the most relevant documents for this credit dossier section.\n\n"
            "{deal_context}\n\n"
            "--- Available Document Summaries ---\n"
            "{document_summaries}"
        )
        return template.format(
            section_key=section_key,
            deal_context=deal_context,
            document_summaries=document_summaries,
        )

    return template.format(
        deal_context=deal_context,
        document_summaries=document_summaries or "No document summaries available.",
    )
