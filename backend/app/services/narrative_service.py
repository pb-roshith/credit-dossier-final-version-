"""
Narrative Service — orchestrates dedicated Mistral AI agents per section.

Each section has its own agent class (from the registry) with:
- Tailored system prompt for the section type
- Zero-shot mode (no custom instructions) or few-shot mode (with examples)
- Section-scoped grounding: only documents uploaded to THIS section
- Output template support: constrains the narrative structure

- Single section: generate one narrative via its dedicated agent
- Draft all: run all 16 section agents in parallel using asyncio.gather()

Grounding data comes from DealDocuments linked to each section
via SectionDocumentLink (new architecture), with fallback to
legacy Upload records.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.agents.registry import get_agent
from app.models.deal import Deal, Section, AuditEntry
from app.models.document import SectionDocumentLink

logger = logging.getLogger(__name__)

# Maximum characters of grounding data to inject into prompt
# Increased from 30k to 80k — OCR text is cleaner and more compact
MAX_GROUNDING_CHARS = 80_000


class NarrativeService:
    """Orchestrates narrative generation using section-specific Mistral agents."""

    @staticmethod
    def _deal_context(deal: Deal) -> dict:
        """Extract deal context for the agent."""
        return {
            "customer": deal.customer,
            "customer_type": deal.customer_type,
            "industry": deal.industry,
            "segment": deal.segment,
            "geography": deal.geography,
            "facility": deal.facility,
            "currency": deal.currency,
            "amount": deal.amount,
            "tenure": deal.tenure,
            "pricing": deal.pricing,
            "repayment": deal.repayment,
            "collateral": deal.collateral,
            "kyc": deal.kyc,
        }

    @staticmethod
    def _get_section_grounding(section: Section) -> str | None:
        """
        Collect grounding data from documents linked to this section.

        Priority:
        1. New: DealDocument via SectionDocumentLink (OCR-quality text)
        2. Legacy fallback: Upload records (local extraction)
        """
        parts = []

        # New architecture: check document_links first
        if section.document_links:
            for link in section.document_links:
                doc = link.document
                if doc and doc.extracted_text:
                    label = doc.filename or doc.url or "Text input"
                    method_tag = f" [{doc.extraction_method}]" if doc.extraction_method else ""
                    parts.append(
                        f"[Document: {label}{method_tag}]\n{doc.extracted_text}"
                    )

        # Legacy fallback: use old uploads if no document_links
        if not parts and section.uploads:
            for upl in section.uploads:
                if upl.extracted_text:
                    label = upl.filename or upl.url or "Text input"
                    parts.append(f"[Document: {label}]\n{upl.extracted_text}")

        if not parts:
            return None

        combined = "\n\n---\n\n".join(parts)

        # Truncate if too large to fit in context window
        if len(combined) > MAX_GROUNDING_CHARS:
            combined = (
                combined[:MAX_GROUNDING_CHARS]
                + "\n\n[... truncated due to length ...]"
            )
            logger.warning(
                f"Grounding data for section {section.section_key} truncated to "
                f"{MAX_GROUNDING_CHARS} chars"
            )

        return combined

    @staticmethod
    async def generate_section(
        db: Session,
        deal_id: str,
        section_id: str,
        custom_instructions: str | None = None,
    ) -> Section | None:
        """Generate narrative for a single section using its dedicated agent."""
        deal = (
            db.query(Deal)
            .options(
                joinedload(Deal.sections)
                .joinedload(Section.uploads),
                joinedload(Deal.sections)
                .joinedload(Section.document_links)
                .joinedload(SectionDocumentLink.document),
            )
            .filter(Deal.id == deal_id)
            .first()
        )
        if not deal:
            return None

        section = next((s for s in deal.sections if s.id == section_id), None)
        if not section:
            return None

        # Update custom instructions if provided
        if custom_instructions is not None:
            section.custom_instructions = custom_instructions

        # Get section-scoped grounding data (only this section's uploads)
        grounding_data = NarrativeService._get_section_grounding(section)

        # Get the dedicated agent for this section type
        agent = get_agent(section.section_key)
        deal_ctx = NarrativeService._deal_context(deal)

        result = await agent.generate(
            section_title=section.title,
            section_description=section.description,
            expected_output=section.expected_output,
            custom_instructions=section.custom_instructions,
            deal_context=deal_ctx,
            grounding_data=grounding_data,
            output_template=section.output_template,
        )

        # Update section with content and accuracy
        section.generated_content = result["content"]
        section.state = "ready"

        accuracy = result.get("accuracy")
        if accuracy:
            section.accuracy_score = accuracy["score"]
            section.accuracy_details = json.dumps(accuracy)
        else:
            section.accuracy_score = None
            section.accuracy_details = None

        # Audit entry
        mode = "few-shot" if section.custom_instructions else "zero-shot"
        has_template = " with template" if section.output_template else ""
        doc_count = len(section.document_links) if section.document_links else 0
        legacy_count = len(section.uploads) if section.uploads else 0
        total_docs = doc_count + legacy_count
        accuracy_tag = f", accuracy={accuracy['score']}%" if accuracy else ""
        audit = AuditEntry(
            deal_id=deal_id,
            action="narrative.generated",
            subject=f"{section.title} ({mode}{has_template}, {total_docs} docs{accuracy_tag})",
            user=f"Agent: {agent.__class__.__name__}",
        )
        db.add(audit)

        # Update deal status
        mandatory = [s for s in deal.sections if not s.optional]
        ready_count = sum(1 for s in mandatory if s.state == "ready")
        if deal.status == "Draft" and ready_count > 0:
            deal.status = "In Progress"

        db.commit()
        db.refresh(section)
        return section

    @staticmethod
    async def draft_all(db: Session, deal_id: str) -> list[dict]:
        """
        Generate narratives for ALL sections in parallel.
        Each section has its own dedicated agent running concurrently.
        Each agent only uses documents from its own section for grounding.
        """
        deal = (
            db.query(Deal)
            .options(
                joinedload(Deal.sections)
                .joinedload(Section.uploads),
                joinedload(Deal.sections)
                .joinedload(Section.document_links)
                .joinedload(SectionDocumentLink.document),
            )
            .filter(Deal.id == deal_id)
            .first()
        )
        if not deal:
            return []

        deal_ctx = NarrativeService._deal_context(deal)

        async def _generate_one(section: Section) -> dict:
            """Generate narrative for one section (runs as async task)."""
            try:
                # Get section-scoped grounding
                grounding_data = NarrativeService._get_section_grounding(section)

                # Get dedicated agent
                agent = get_agent(section.section_key)

                result = await agent.generate(
                    section_title=section.title,
                    section_description=section.description,
                    expected_output=section.expected_output,
                    custom_instructions=section.custom_instructions,
                    deal_context=deal_ctx,
                    grounding_data=grounding_data,
                    output_template=section.output_template,
                )

                accuracy = result.get("accuracy")
                return {
                    "section_id": section.id,
                    "section_key": section.section_key,
                    "title": section.title,
                    "generated_content": result["content"],
                    "state": "ready",
                    "success": True,
                    "agent": agent.__class__.__name__,
                    "accuracy": accuracy,
                }
            except Exception as e:
                logger.error(f"Failed to draft section {section.section_key}: {e}")
                return {
                    "section_id": section.id,
                    "section_key": section.section_key,
                    "title": section.title,
                    "generated_content": f"[Generation failed: {str(e)}]",
                    "state": "pending",
                    "success": False,
                    "agent": "N/A",
                    "accuracy": None,
                }

        # Run all agents in parallel
        tasks = [_generate_one(section) for section in deal.sections]
        results = await asyncio.gather(*tasks)

        # Update all sections in DB
        for result in results:
            section = next((s for s in deal.sections if s.id == result["section_id"]), None)
            if section:
                section.generated_content = result["generated_content"]
                if result["success"]:
                    section.state = "ready"
                accuracy = result.get("accuracy")
                if accuracy:
                    section.accuracy_score = accuracy["score"]
                    section.accuracy_details = json.dumps(accuracy)
                else:
                    section.accuracy_score = None
                    section.accuracy_details = None

        # Update deal status
        mandatory = [s for s in deal.sections if not s.optional]
        ready_count = sum(1 for s in mandatory if s.state == "ready")
        if ready_count > 0:
            deal.status = "In Progress"
        if ready_count == len(mandatory):
            deal.status = "In Progress"  # All ready, can submit

        # Single audit entry for batch operation
        succeeded = sum(1 for r in results if r["success"])
        audit = AuditEntry(
            deal_id=deal_id,
            action="narrative.draft_all",
            subject=f"Generated {succeeded}/{len(results)} sections (dedicated agents)",
            user="Agent System",
        )
        db.add(audit)

        db.commit()

        return list(results)
