"""
Base Section Agent — abstract base class for all section-specific narrative agents.

Implements:
- Zero-shot mode: system prompt + deal context + user request (no custom instructions)
- Few-shot mode: adds user/assistant example pairs from custom_instructions
- Output template: injects markdown template as structural constraint
- Section-scoped grounding: uses only the section's uploaded document text
"""

from __future__ import annotations

import logging
from typing import Any

from mistralai.client import Mistral

from app.config import settings

logger = logging.getLogger(__name__)


class BaseSectionAgent:
    """
    Base class for all section-specific narrative agents.

    Subclasses must set:
        section_key: str  — e.g. "executive_summary"
        system_prompt: str — section-specific instructions for Mistral
    """

    section_key: str = ""
    system_prompt: str = (
        "You are a senior credit analyst drafting a section of a credit pitch book. "
        "Generate professional, bank-ready content in markdown format."
    )

    def __init__(self):
        self._client: Mistral | None = None

    @property
    def client(self) -> Mistral:
        if self._client is None:
            self._client = Mistral(api_key=settings.MISTRAL_API_KEY)
        return self._client

    # ── Prompt construction ─────────────────────────────────────

    def _build_system_prompt(self, deal_context: dict[str, Any]) -> str:
        """Combine section-specific system prompt with deal context."""
        deal_ctx = f"""

--- Deal Context ---
Customer: {deal_context.get('customer', 'N/A')}
Customer Type: {deal_context.get('customer_type', 'N/A')}
Industry: {deal_context.get('industry', 'N/A')}
Segment: {deal_context.get('segment', 'N/A')}
Geography: {deal_context.get('geography', 'N/A')}
Facility Type: {deal_context.get('facility', 'N/A')}
Currency: {deal_context.get('currency', 'N/A')}
Amount: {deal_context.get('currency', '')} {deal_context.get('amount', 0):,.0f}
Tenure: {deal_context.get('tenure', 0)} months
Pricing: {deal_context.get('pricing', 'N/A')}
Repayment: {deal_context.get('repayment', 'N/A')}
Collateral: {'Secured' if deal_context.get('collateral') else 'Clean/Unsecured'}
KYC Status: {deal_context.get('kyc', 'N/A')}
---

Generate professional, bank-ready content. Use markdown formatting for structure.
Do NOT include a title/heading — the system adds that automatically.
"""
        return self.system_prompt + deal_ctx

    def _build_messages(
        self,
        system_prompt: str,
        section_title: str,
        section_description: str,
        expected_output: str,
        custom_instructions: str | None,
        grounding_data: str | None,
        output_template: str | None,
    ) -> list[dict]:
        """
        Build the complete messages list for the Mistral chat API.

        - Zero-shot (no custom_instructions): [system, user]
        - Few-shot (custom_instructions provided): [system, user-example, assistant-example, user]
        - Template-aware: injects template constraint into the user message
        """
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
        ]

        # ── Few-shot: inject custom instructions as example pairs ──
        if custom_instructions and custom_instructions.strip():
            # Parse custom instructions as example pairs
            # Expected format: user/assistant example pairs separated by "---"
            # Or treat the entire custom_instructions as guidance examples
            example_user = (
                f"Here is an example of the tone, style, and structure I want "
                f"for the {section_title} section:\n\n{custom_instructions}"
            )
            example_assistant = (
                f"Understood. I will follow the style, tone, structure, and "
                f"formatting patterns shown in your example when generating "
                f"the {section_title} narrative. I will adapt the content to "
                f"match the deal context and grounding data provided."
            )
            messages.append({"role": "user", "content": example_user})
            messages.append({"role": "assistant", "content": example_assistant})

        # ── Build the main user prompt ──
        user_parts = [
            f"Section: {section_title}",
            f"Description: {section_description}",
            f"Expected Output: {expected_output}",
        ]

        # Grounding data — section-scoped document content
        if grounding_data:
            user_parts.append(
                f"\n--- Grounding Data (OCR-extracted from uploaded documents) ---\n"
                f"{grounding_data}\n---\n"
                f"The above grounding data has been extracted using advanced OCR and is highly accurate. "
                f"ALWAYS reference specific numbers, dates, percentages, and facts from this data. "
                f"Do NOT hallucinate or invent any figures. If a specific data point is not available "
                f"in the grounding data, explicitly state 'Data not available' rather than guessing."
            )
        else:
            user_parts.append(
                "\n[No grounding documents uploaded for this section. "
                "Generate based on deal context and industry best practices.]"
            )

        # Output template — structural constraint
        if output_template and output_template.strip():
            user_parts.append(
                f"\n--- Output Template (MUST follow this structure) ---\n"
                f"{output_template}\n---\n"
                f"IMPORTANT: Your output MUST follow the exact markdown structure, "
                f"headings, and sections shown in the template above. Fill in each "
                f"section of the template with appropriate content based on the deal "
                f"context and grounding data. Maintain the same heading hierarchy, "
                f"bullet structure, and table formats."
            )

        user_parts.append("\nGenerate the narrative now.")
        messages.append({"role": "user", "content": "\n".join(user_parts)})

        return messages

    # ── Generation ──────────────────────────────────────────────

    async def generate(
        self,
        section_title: str,
        section_description: str,
        expected_output: str,
        custom_instructions: str | None,
        deal_context: dict[str, Any],
        grounding_data: str | None = None,
        output_template: str | None = None,
    ) -> str:
        """
        Generate narrative content for this section.

        Uses section-scoped grounding data (extracted text from this section's
        uploads only), not the deal-wide DocumentLibraryTool.

        Modes:
        - Zero-shot: no custom_instructions → system + user only
        - Few-shot: custom_instructions present → adds example pairs
        - Template: output_template present → constrains output structure
        """
        system_prompt = self._build_system_prompt(deal_context)

        messages = self._build_messages(
            system_prompt=system_prompt,
            section_title=section_title,
            section_description=section_description,
            expected_output=expected_output,
            custom_instructions=custom_instructions,
            grounding_data=grounding_data,
            output_template=output_template,
        )

        mode = "few-shot" if custom_instructions else "zero-shot"
        has_template = "with-template" if output_template else "no-template"
        has_docs = "with-docs" if grounding_data else "no-docs"
        logger.info(
            f"[{self.section_key}] Generating narrative "
            f"(mode={mode}, {has_template}, {has_docs})"
        )

        try:
            response = await self.client.chat.complete_async(
                model=settings.MISTRAL_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=4096,
            )

            msg = response.choices[0].message
            if msg and msg.content:
                logger.info(f"[{self.section_key}] Successfully generated narrative")
                return msg.content

            # Fallback: retry if empty
            logger.warning(f"[{self.section_key}] Empty response, retrying…")
            response = await self.client.chat.complete_async(
                model=settings.MISTRAL_MODEL,
                messages=messages,
                temperature=0.4,
                max_tokens=4096,
            )
            if response.choices[0].message and response.choices[0].message.content:
                return response.choices[0].message.content

            logger.error(f"[{self.section_key}] No content after retry")
            return f"[Generation failed — model returned no content for {section_title}]"

        except Exception as e:
            logger.error(f"[{self.section_key}] Generation failed: {e}")
            raise
