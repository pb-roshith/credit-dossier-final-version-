"""
Narrative Service — orchestrates section narrative generation via Mistral Agents.

Each section has a dedicated Mistral Agent with document_library tool access.
The agent automatically retrieves relevant content from the deal's library.

- Single section: generate one narrative via its dedicated agent
- Draft all: run all 16 section agents in parallel using asyncio.gather()
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models.deal import Deal, Section, AuditEntry
from app.models.library_file import LibraryFile
from app.services.mistral_library_service import MistralLibraryService

logger = logging.getLogger(__name__)


class NarrativeService:
    """Orchestrates narrative generation using section-specific Mistral agents."""

    @staticmethod
    async def generate_section(
        db: Session,
        deal_id: str,
        section_id: str,
        custom_instructions: str | None = None,
    ) -> Section | None:
        """Generate narrative for a single section using its dedicated Mistral agent."""
        deal = (
            db.query(Deal)
            .options(
                joinedload(Deal.sections),
                joinedload(Deal.library_files),
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

        # Ensure agent exists for this section
        agent_id = MistralLibraryService.get_agent_id(db, deal_id, section.section_key)
        if not agent_id:
            agent_id = await MistralLibraryService.create_section_agent(
                db=db,
                deal=deal,
                section_key=section.section_key,
                section_title=section.title,
            )

        # Generate via Mistral Agent (RAG handled by document_library tool)
        content = await MistralLibraryService.generate_with_agent(
            agent_id=agent_id,
            section_title=section.title,
            section_description=section.description,
            expected_output=section.expected_output,
            custom_instructions=section.custom_instructions,
            output_template=section.output_template,
        )

        # Update section with generated content
        section.generated_content = content
        section.state = "ready"

        # Assess accuracy
        has_docs = len(deal.library_files) > 0
        accuracy = await MistralLibraryService.evaluate_accuracy(
            generated_content=content,
            section_title=section.title,
            has_library_docs=has_docs,
        )

        if accuracy:
            section.accuracy_score = accuracy["score"]
            section.accuracy_details = json.dumps(accuracy)
        else:
            section.accuracy_score = None
            section.accuracy_details = None

        # Audit entry
        mode = "few-shot" if section.custom_instructions else "zero-shot"
        has_template = " with template" if section.output_template else ""
        doc_count = len(deal.library_files)
        accuracy_tag = f", accuracy={accuracy['score']}%" if accuracy else ""
        audit = AuditEntry(
            deal_id=deal_id,
            action="narrative.generated",
            subject=f"{section.title} ({mode}{has_template}, {doc_count} library docs{accuracy_tag})",
            user=f"Mistral Agent: {section.section_key}",
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
        Each section has its own dedicated Mistral agent running concurrently.
        """
        deal = (
            db.query(Deal)
            .options(
                joinedload(Deal.sections),
                joinedload(Deal.library_files),
            )
            .filter(Deal.id == deal_id)
            .first()
        )
        if not deal:
            return []

        # Ensure all agents exist
        await MistralLibraryService.create_all_agents(db, deal)

        has_docs = len(deal.library_files) > 0

        async def _generate_one(section: Section) -> dict:
            """Generate narrative for one section (runs as async task)."""
            try:
                agent_id = MistralLibraryService.get_agent_id(
                    db, deal_id, section.section_key
                )
                if not agent_id:
                    raise ValueError(f"No agent found for {section.section_key}")

                content = await MistralLibraryService.generate_with_agent(
                    agent_id=agent_id,
                    section_title=section.title,
                    section_description=section.description,
                    expected_output=section.expected_output,
                    custom_instructions=section.custom_instructions,
                    output_template=section.output_template,
                )

                accuracy = await MistralLibraryService.evaluate_accuracy(
                    generated_content=content,
                    section_title=section.title,
                    has_library_docs=has_docs,
                )

                return {
                    "section_id": section.id,
                    "section_key": section.section_key,
                    "title": section.title,
                    "generated_content": content,
                    "state": "ready",
                    "success": True,
                    "agent": f"Mistral Agent: {section.section_key}",
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
            section = next(
                (s for s in deal.sections if s.id == result["section_id"]), None
            )
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
            subject=f"Generated {succeeded}/{len(results)} sections (Mistral Agents + Library RAG)",
            user="Agent System",
        )
        db.add(audit)

        db.commit()

        return list(results)
