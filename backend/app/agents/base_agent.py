"""
Base Section Agent — abstract base class for all section-specific narrative agents.

Implements:
- Zero-shot mode: system prompt + deal context + user request (no custom instructions)
- Few-shot mode: adds user/assistant example pairs from custom_instructions
- Output template: injects markdown template as structural constraint
- Section-scoped grounding: uses only the section's uploaded document text
"""

from __future__ import annotations

import json
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
    ) -> dict[str, Any]:
        """
        Generate narrative content for this section and assess accuracy.

        Returns a dict:
            {
                "content": str,          # The generated narrative markdown
                "accuracy": dict | None  # Accuracy assessment or None if no docs
            }

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
            content = None
            if msg and msg.content:
                logger.info(f"[{self.section_key}] Successfully generated narrative")
                content = msg.content

            # Fallback: retry if empty
            if not content:
                logger.warning(f"[{self.section_key}] Empty response, retrying…")
                response = await self.client.chat.complete_async(
                    model=settings.MISTRAL_MODEL,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=4096,
                )
                if response.choices[0].message and response.choices[0].message.content:
                    content = response.choices[0].message.content

            if not content:
                logger.error(f"[{self.section_key}] No content after retry")
                return {
                    "content": f"[Generation failed — model returned no content for {section_title}]",
                    "accuracy": None,
                }

            # Assess accuracy against grounding data
            accuracy = await self._assess_accuracy(
                content, grounding_data, section_title
            )

            return {"content": content, "accuracy": accuracy}

        except Exception as e:
            logger.error(f"[{self.section_key}] Generation failed: {e}")
            raise

    # ── Accuracy Assessment ─────────────────────────────────────

    async def _assess_accuracy(
        self,
        generated_content: str,
        grounding_data: str | None,
        section_title: str,
    ) -> dict[str, Any] | None:
        """
        Assess how well the generated narrative is grounded in the source documents.

        Makes a second Mistral call with an evaluator prompt that returns a
        structured JSON assessment.

        Returns None if no grounding data was provided (nothing to verify against).
        """
        if not grounding_data:
            logger.info(
                f"[{self.section_key}] No grounding data — skipping accuracy assessment"
            )
            return None

        evaluator_prompt = (
            "You are an accuracy evaluator for AI-generated credit analysis narratives. "
            "Your job is to compare a generated narrative against the source documents "
            "and assess how well the narrative is grounded in the provided data.\n\n"
            "Evaluate the following:\n"
            "1. **Grounded claims**: Facts, figures, dates, percentages directly found in the source documents\n"
            "2. **Inferred claims**: Reasonable conclusions drawn from the data (e.g., trend analysis)\n"
            "3. **Unsupported claims**: Statements that have no basis in the source documents\n\n"
            "Return ONLY a valid JSON object (no markdown, no explanation outside the JSON) "
            "with this exact structure:\n"
            "{\n"
            '  "score": <integer 0-100>,\n'
            '  "grounded_claims": <integer>,\n'
            '  "inferred_claims": <integer>,\n'
            '  "unsupported_claims": <integer>,\n'
            '  "summary": "<1-2 sentence explanation>"\n'
            "}\n\n"
            "Scoring guide:\n"
            "- 90-100: Almost all claims directly supported by documents\n"
            "- 70-89: Most claims supported, some reasonable inferences\n"
            "- 50-69: Mixed — significant inferences or some unsupported claims\n"
            "- Below 50: Many unsupported or fabricated claims"
        )

        # Truncate inputs to avoid exceeding context window
        max_content_chars = 8_000
        max_grounding_chars = 20_000

        content_excerpt = generated_content[:max_content_chars]
        if len(generated_content) > max_content_chars:
            content_excerpt += "\n\n[... truncated for evaluation ...]"

        grounding_excerpt = grounding_data[:max_grounding_chars]
        if len(grounding_data) > max_grounding_chars:
            grounding_excerpt += "\n\n[... truncated for evaluation ...]"

        user_message = (
            f"## Section: {section_title}\n\n"
            f"### Generated Narrative:\n{content_excerpt}\n\n"
            f"### Source Documents:\n{grounding_excerpt}\n\n"
            "Now evaluate the accuracy. Return ONLY the JSON object."
        )

        try:
            response = await self.client.chat.complete_async(
                model=settings.MISTRAL_MODEL,
                messages=[
                    {"role": "system", "content": evaluator_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_tokens=512,
            )

            raw = response.choices[0].message.content or ""
            raw = raw.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                lines = raw.split("\n")
                # Remove first line (```json or ```) and last line (```)
                lines = [l for l in lines if not l.strip().startswith("```")]
                raw = "\n".join(lines).strip()

            result = json.loads(raw)

            # Validate and clamp score
            score = max(0, min(100, int(result.get("score", 0))))
            accuracy = {
                "score": score,
                "grounded_claims": int(result.get("grounded_claims", 0)),
                "inferred_claims": int(result.get("inferred_claims", 0)),
                "unsupported_claims": int(result.get("unsupported_claims", 0)),
                "summary": str(result.get("summary", "Assessment completed.")),
            }

            logger.info(
                f"[{self.section_key}] Accuracy assessment: "
                f"score={accuracy['score']}%, "
                f"grounded={accuracy['grounded_claims']}, "
                f"inferred={accuracy['inferred_claims']}, "
                f"unsupported={accuracy['unsupported_claims']}"
            )
            return accuracy

        except json.JSONDecodeError as e:
            logger.warning(
                f"[{self.section_key}] Accuracy evaluator returned invalid JSON: {e}"
            )
            return {
                "score": 0,
                "grounded_claims": 0,
                "inferred_claims": 0,
                "unsupported_claims": 0,
                "summary": "Accuracy assessment failed — could not parse evaluator response.",
            }
        except Exception as e:
            logger.error(f"[{self.section_key}] Accuracy assessment failed: {e}")
            return {
                "score": 0,
                "grounded_claims": 0,
                "inferred_claims": 0,
                "unsupported_claims": 0,
                "summary": f"Accuracy assessment error: {str(e)}",
            }

