"""
Narrative Service — orchestrates section narrative generation via Mistral Agents.

Pipeline per section:
    1. Moderation gate (user-provided inputs)
    2. Orchestration pre-flight (MCP summaries → document selection strategy)
    3. Deal context optimization (section-specific fields only)
    4. Generation via section agent (with orchestration strategy + library RAG)
    5. Accuracy evaluation

- Single section: full pipeline for one section
- Draft all: MCP summaries fetched ONCE, then 16 sections in parallel with dual semaphores
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.deal import Deal, Section, AuditEntry
from app.models.library_file import LibraryFile
from app.services.mistral_library_service import MistralLibraryService
from app.services.moderation_service import ModerationService
from app.services.orchestration_service import OrchestrationService, OrchestrationResult
from app.services.mcp_service import MCPClientService

logger = logging.getLogger(__name__)


class NarrativeService:
    """Orchestrates narrative generation using section-specific Mistral agents."""

    # ── Single Section Generation ──────────────────────────────────

    @staticmethod
    async def generate_section(
        db: Session,
        deal_id: str,
        section_id: str,
        custom_instructions: str | None = None,
    ) -> Section | None:
        """
        Generate narrative for a single section using the full pipeline:
        moderation → orchestration → context optimization → generation → accuracy.
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
            return None

        section = next((s for s in deal.sections if s.id == section_id), None)
        if not section:
            return None

        # Update custom instructions if provided
        if custom_instructions is not None:
            section.custom_instructions = custom_instructions

        total_start = time.time()

        # ── Step 1: Moderation Gate ──────────────────────────────
        if section.custom_instructions or section.output_template:
            moderation = await ModerationService.moderate_section_inputs(
                custom_instructions=section.custom_instructions,
                output_template=section.output_template,
            )
            section.moderation_status = "safe" if moderation.is_safe else "flagged"
            section.moderation_details = json.dumps(moderation.to_dict())

            if not moderation.is_safe:
                db.commit()
                db.refresh(section)
                flagged = ", ".join(moderation.flagged_categories)
                raise ValueError(
                    f"Content moderation failed for '{section.title}'. "
                    f"Flagged categories: {flagged}. "
                    f"Please review and edit your custom instructions or output template."
                )
        else:
            section.moderation_status = None
            section.moderation_details = None

        # ── Step 2: Orchestration Pre-flight ─────────────────────
        orch_start = time.time()
        orchestration = await NarrativeService._run_orchestration(
            deal=deal,
            section=section,
            db=db,
        )
        orch_ms = (time.time() - orch_start) * 1000

        # ── Step 3: Build Section-Specific Deal Context ──────────
        deal_context = OrchestrationService.build_deal_context_for_section(
            deal, section.section_key
        )

        # ── Step 4: Generate via Mistral Agent ───────────────────
        agent_id = MistralLibraryService.get_global_agent_id(db, section.section_key)
        if not agent_id:
            raise ValueError(f"Global agent for {section.section_key} not initialized")

        gen_start = time.time()
        content = await MistralLibraryService.generate_with_agent(
            agent_id=agent_id,
            section_title=section.title,
            section_description=section.description,
            expected_output=section.expected_output,
            deal_context=deal_context,
            orchestration_strategy=orchestration.to_strategy_text(),
            custom_instructions=section.custom_instructions,
            output_template=section.output_template,
        )
        gen_ms = (time.time() - gen_start) * 1000

        # Update section
        section.generated_content = content
        section.state = "ready"
        section.orchestration_strategy = orchestration.to_strategy_text()

        # ── Step 5: Accuracy Evaluation ──────────────────────────
        acc_start = time.time()
        has_docs = len(deal.library_files) > 0
        accuracy = await MistralLibraryService.evaluate_accuracy(
            generated_content=content,
            section_title=section.title,
            has_library_docs=has_docs,
        )
        acc_ms = (time.time() - acc_start) * 1000

        if accuracy:
            section.accuracy_score = accuracy["score"]
            section.accuracy_details = json.dumps(accuracy)
        else:
            section.accuracy_score = None
            section.accuracy_details = None

        # ── Audit + Timing ───────────────────────────────────────
        total_ms = (time.time() - total_start) * 1000
        mode = "few-shot" if section.custom_instructions else "zero-shot"
        has_template = " with template" if section.output_template else ""
        doc_count = len(deal.library_files)
        accuracy_tag = f", accuracy={accuracy['score']}%" if accuracy else ""

        timing_tag = ""
        if settings.ENABLE_TIMING_METRICS:
            timing_tag = (
                f", timing: orch={orch_ms:.0f}ms "
                f"gen={gen_ms:.0f}ms "
                f"acc={acc_ms:.0f}ms "
                f"total={total_ms:.0f}ms"
            )

        audit = AuditEntry(
            deal_id=deal_id,
            action="narrative.generated",
            subject=(
                f"{section.title} ({mode}{has_template}, "
                f"{doc_count} library docs, "
                f"orch_conf={orchestration.confidence:.1f}"
                f"{accuracy_tag}{timing_tag})"
            ),
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
        return section, orchestration.to_strategy_text()

    # ── Draft All (Parallel) ───────────────────────────────────────

    @staticmethod
    async def draft_all(db: Session, deal_id: str) -> list[dict]:
        """
        Generate narratives for ALL sections in parallel.

        Optimizations:
        - MCP summaries fetched ONCE and shared across all 16 sections
        - Dual semaphores: orchestration(5) and generation(3)
        - Accuracy evaluation runs with orchestration semaphore (lightweight)
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

        has_docs = len(deal.library_files) > 0
        batch_start = time.time()

        # ── Pre-fetch MCP summaries ONCE for the entire batch ────
        mcp_summaries = ""
        if settings.ORCHESTRATION_ENABLED and deal.customer:
            try:
                mcp_summaries = await MCPClientService.get_document_summaries_cached(
                    company_name=deal.customer
                )
                logger.info(
                    f"Fetched MCP summaries for '{deal.customer}' "
                    f"({len(mcp_summaries)} chars)"
                )
            except Exception as e:
                logger.warning(f"MCP summary fetch failed: {e}")
                mcp_summaries = ""

        # ── Get orchestration agent ID ───────────────────────────
        orch_agent_id = MistralLibraryService.get_global_agent_id(db, "orchestration")

        # ── Dual semaphores ──────────────────────────────────────
        orch_semaphore = asyncio.Semaphore(settings.ORCHESTRATION_SEMAPHORE)
        gen_semaphore = asyncio.Semaphore(settings.GENERATION_SEMAPHORE)
        eval_semaphore = asyncio.Semaphore(settings.ORCHESTRATION_SEMAPHORE)

        async def _generate_one(section: Section) -> dict:
            """Full pipeline for one section (runs as async task)."""
            section_start = time.time()
            orch_ms = gen_ms = acc_ms = 0.0

            try:
                # ── Moderation Gate ──
                if section.custom_instructions or section.output_template:
                    moderation = await ModerationService.moderate_section_inputs(
                        custom_instructions=section.custom_instructions,
                        output_template=section.output_template,
                    )
                    section.moderation_status = "safe" if moderation.is_safe else "flagged"
                    section.moderation_details = json.dumps(moderation.to_dict())

                    if not moderation.is_safe:
                        flagged = ", ".join(moderation.flagged_categories)
                        raise ValueError(f"Moderation failed: {flagged}")

                # ── Orchestration (lightweight, semaphore=5) ──
                t0 = time.time()
                async with orch_semaphore:
                    orchestration = await OrchestrationService.select_documents_for_section(
                        deal=deal,
                        section=section,
                        document_summaries=mcp_summaries,
                        orch_agent_id=orch_agent_id,
                    )
                orch_ms = (time.time() - t0) * 1000

                # ── Deal Context ──
                deal_context = OrchestrationService.build_deal_context_for_section(
                    deal, section.section_key
                )

                # ── Generation (heavy, semaphore=3) ──
                agent_id = MistralLibraryService.get_global_agent_id(
                    db, section.section_key
                )
                if not agent_id:
                    raise ValueError(f"No global agent found for {section.section_key}")

                t0 = time.time()
                async with gen_semaphore:
                    content = await MistralLibraryService.generate_with_agent(
                        agent_id=agent_id,
                        section_title=section.title,
                        section_description=section.description,
                        expected_output=section.expected_output,
                        deal_context=deal_context,
                        orchestration_strategy=orchestration.to_strategy_text(),
                        custom_instructions=section.custom_instructions,
                        output_template=section.output_template,
                    )
                gen_ms = (time.time() - t0) * 1000

                # ── Accuracy Evaluation (lightweight, semaphore=5) ──
                accuracy = None
                t0 = time.time()
                async with eval_semaphore:
                    accuracy = await MistralLibraryService.evaluate_accuracy(
                        generated_content=content,
                        section_title=section.title,
                        has_library_docs=has_docs,
                    )
                acc_ms = (time.time() - t0) * 1000

                total_ms = (time.time() - section_start) * 1000
                logger.info(
                    f"[draft-all] {section.section_key}: "
                    f"orch={orch_ms:.0f}ms gen={gen_ms:.0f}ms "
                    f"acc={acc_ms:.0f}ms total={total_ms:.0f}ms"
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
                    "orchestration_strategy": orchestration.to_strategy_text(),
                    "timing": {
                        "orchestration_ms": round(orch_ms),
                        "generation_ms": round(gen_ms),
                        "accuracy_ms": round(acc_ms),
                        "total_ms": round(total_ms),
                    },
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
                    "orchestration_strategy": None,
                    "timing": None,
                }

        # ── Run all 16 sections concurrently ─────────────────────
        tasks = [_generate_one(section) for section in deal.sections]
        results = await asyncio.gather(*tasks)

        # ── Persist all results to DB ────────────────────────────
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
                
                section.orchestration_strategy = result.get("orchestration_strategy")

        # Update deal status
        mandatory = [s for s in deal.sections if not s.optional]
        ready_count = sum(1 for s in mandatory if s.state == "ready")
        if ready_count > 0:
            deal.status = "In Progress"
        if ready_count == len(mandatory):
            deal.status = "In Progress"  # All ready, can submit

        # Batch audit entry with timing
        batch_ms = (time.time() - batch_start) * 1000
        succeeded = sum(1 for r in results if r["success"])

        timing_tag = ""
        if settings.ENABLE_TIMING_METRICS:
            timing_tag = f", total_batch={batch_ms:.0f}ms"

        audit = AuditEntry(
            deal_id=deal_id,
            action="narrative.draft_all",
            subject=(
                f"Generated {succeeded}/{len(results)} sections "
                f"(orchestrated + Library RAG, "
                f"gen_sem={settings.GENERATION_SEMAPHORE}, "
                f"orch_sem={settings.ORCHESTRATION_SEMAPHORE}"
                f"{timing_tag})"
            ),
            user="Agent System",
        )
        db.add(audit)

        db.commit()

        return list(results)

    # ── Orchestration Helper ───────────────────────────────────────

    @staticmethod
    async def _run_orchestration(
        deal: Deal,
        section: Section,
        db: Session,
    ) -> OrchestrationResult:
        """
        Run orchestration for a single section.
        Fetches MCP summaries (cached) and calls OrchestrationService.
        """
        if not settings.ORCHESTRATION_ENABLED:
            return OrchestrationResult(
                strategy_summary="Orchestration disabled.",
                confidence=0.0,
            )

        # Fetch MCP summaries (cached — won't hit MCP repeatedly)
        mcp_summaries = ""
        if deal.customer:
            try:
                mcp_summaries = await MCPClientService.get_document_summaries_cached(
                    company_name=deal.customer
                )
            except Exception as e:
                logger.warning(f"MCP summary fetch failed: {e}")

        # Get orchestration agent ID
        orch_agent_id = MistralLibraryService.get_global_agent_id(db, "orchestration")

        return await OrchestrationService.select_documents_for_section(
            deal=deal,
            section=section,
            document_summaries=mcp_summaries,
            orch_agent_id=orch_agent_id,
        )
