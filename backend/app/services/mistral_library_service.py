"""
Mistral Library Service — manages Mistral Libraries, Agents, and Agent-based generation.

Handles:
- Library lifecycle (create, delete, list files)
- File upload to Mistral Library
- Agent lifecycle (create per section, delete on deal cleanup)
- Generation via Mistral Agents API (with document_library tool for RAG)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.deal import Deal
from app.models.mistral_agent import MistralAgent
from app.models.library_file import LibraryFile
from app.agents.instructions import get_instructions

logger = logging.getLogger(__name__)

# Lazy Mistral client
_mistral_client = None


def _get_client():
    global _mistral_client
    if _mistral_client is None:
        from mistralai.client import Mistral
        _mistral_client = Mistral(api_key=settings.MISTRAL_API_KEY)
    return _mistral_client


class MistralLibraryService:
    """Manages Mistral Libraries, Agents, and RAG-based generation."""

    # ── Library Management ─────────────────────────────────────────

    @staticmethod
    async def create_library(db: Session, deal: Deal) -> str:
        """
        Create a Mistral Library for a deal. Stores library_id on the Deal.
        Returns the library_id.
        """
        if deal.mistral_library_id:
            logger.info(f"Deal {deal.id} already has library {deal.mistral_library_id}")
            return deal.mistral_library_id

        client = _get_client()

        library = await client.beta.libraries.create_async(
            name=f"CreditDossier_{deal.customer}_{deal.id}",
            description=f"Document library for credit dossier — {deal.customer}",
        )

        deal.mistral_library_id = library.id
        db.commit()

        logger.info(f"Created Mistral Library {library.id} for deal {deal.id}")
        return library.id

    @staticmethod
    async def delete_library(library_id: str) -> None:
        """Delete a Mistral Library. Called on deal deletion."""
        if not library_id:
            return
        client = _get_client()
        try:
            await client.beta.libraries.delete_async(library_id=library_id)
            logger.info(f"Deleted Mistral Library {library_id}")
        except Exception as e:
            logger.warning(f"Failed to delete Mistral Library {library_id}: {e}")

    # ── File Upload to Library ─────────────────────────────────────

    @staticmethod
    async def upload_file_to_library(
        db: Session,
        deal: Deal,
        file_bytes: bytes,
        filename: str,
        source_type: str = "file",
        note: str | None = None,
    ) -> LibraryFile:
        """
        Upload a file to the deal's Mistral Library.

        1. Ensure library exists (create if needed)
        2. Upload file via Mistral Files API
        3. Create LibraryFile record
        """
        client = _get_client()

        # Ensure library exists
        if not deal.mistral_library_id:
            await MistralLibraryService.create_library(db, deal)

        # Upload file to Mistral
        uploaded = await client.files.upload_async(
            file={"file_name": filename, "content": file_bytes},
            purpose="library",
        )

        logger.info(
            f"Uploaded {filename} to Mistral files (id={uploaded.id}) "
            f"for library {deal.mistral_library_id}"
        )

        # Add file to the library
        await client.beta.libraries.files.create_async(
            library_id=deal.mistral_library_id,
            file_id=uploaded.id,
        )

        logger.info(
            f"Added file {uploaded.id} to library {deal.mistral_library_id}"
        )

        # Create local record
        lib_file = LibraryFile(
            deal_id=deal.id,
            mistral_file_id=uploaded.id,
            filename=filename,
            source_type=source_type,
            file_size=len(file_bytes),
            note=note,
        )
        db.add(lib_file)
        db.commit()
        db.refresh(lib_file)

        return lib_file

    @staticmethod
    async def delete_library_file(
        db: Session, deal: Deal, file_id: str
    ) -> bool:
        """Remove a file from the Mistral Library and delete local record."""
        lib_file = (
            db.query(LibraryFile)
            .filter(LibraryFile.id == file_id, LibraryFile.deal_id == deal.id)
            .first()
        )
        if not lib_file:
            return False

        client = _get_client()

        # Remove from Mistral library
        if deal.mistral_library_id:
            try:
                await client.beta.libraries.files.delete_async(
                    library_id=deal.mistral_library_id,
                    file_id=lib_file.mistral_file_id,
                )
            except Exception as e:
                logger.warning(f"Failed to remove file from library: {e}")

        # Delete Mistral file
        try:
            await client.files.delete_async(file_id=lib_file.mistral_file_id)
        except Exception as e:
            logger.warning(f"Failed to delete Mistral file {lib_file.mistral_file_id}: {e}")

        db.delete(lib_file)
        db.commit()
        return True

    # ── Agent Management ───────────────────────────────────────────

    @staticmethod
    async def create_section_agent(
        db: Session,
        deal: Deal,
        section_key: str,
        section_title: str,
    ) -> str:
        """
        Create a Mistral Agent for a specific section with document_library tool.
        Returns the agent_id.
        """
        client = _get_client()

        # Check if agent already exists
        existing = (
            db.query(MistralAgent)
            .filter(
                MistralAgent.deal_id == deal.id,
                MistralAgent.section_key == section_key,
            )
            .first()
        )
        if existing:
            return existing.agent_id

        # Get section-specific instructions
        instructions = get_instructions(section_key)

        # Build deal context into instructions
        deal_ctx = (
            f"\n\n--- Deal Context ---\n"
            f"Customer: {deal.customer}\n"
            f"Customer Type: {deal.customer_type}\n"
            f"Industry: {deal.industry}\n"
            f"Segment: {deal.segment}\n"
            f"Geography: {deal.geography}\n"
            f"Facility Type: {deal.facility}\n"
            f"Currency: {deal.currency}\n"
            f"Amount: {deal.currency} {deal.amount:,.0f}\n"
            f"Tenure: {deal.tenure} months\n"
            f"Pricing: {deal.pricing}\n"
            f"Repayment: {deal.repayment}\n"
            f"Collateral: {'Secured' if deal.collateral else 'Clean/Unsecured'}\n"
            f"KYC Status: {deal.kyc}\n"
            f"---"
        )

        full_instructions = instructions + deal_ctx

        # Build tools list
        tools = []
        if deal.mistral_library_id:
            tools.append({
                "type": "document_library",
                "library_ids": [deal.mistral_library_id],
            })

        # Create agent
        agent = await client.beta.agents.create_async(
            model=settings.MISTRAL_AGENT_MODEL,
            name=f"{section_title} — {deal.customer}",
            instructions=full_instructions,
            tools=tools,
        )

        # Store agent ID
        ma = MistralAgent(
            deal_id=deal.id,
            section_key=section_key,
            agent_id=agent.id,
        )
        db.add(ma)
        db.commit()

        logger.info(
            f"Created Mistral Agent {agent.id} for {section_key} "
            f"in deal {deal.id}"
        )
        return agent.id

    @staticmethod
    async def create_all_agents(db: Session, deal: Deal) -> dict[str, str]:
        """
        Create all 16 section agents for a deal.
        Returns {section_key: agent_id} mapping.
        """
        from app.services.deal_service import DEFAULT_SECTIONS

        agents = {}
        for sec_def in DEFAULT_SECTIONS:
            agent_id = await MistralLibraryService.create_section_agent(
                db=db,
                deal=deal,
                section_key=sec_def["section_key"],
                section_title=sec_def["title"],
            )
            agents[sec_def["section_key"]] = agent_id

        logger.info(f"Created {len(agents)} agents for deal {deal.id}")
        return agents

    @staticmethod
    async def delete_all_agents(db: Session, deal_id: str) -> None:
        """Delete all Mistral agents for a deal."""
        client = _get_client()
        agents = (
            db.query(MistralAgent)
            .filter(MistralAgent.deal_id == deal_id)
            .all()
        )
        for ma in agents:
            try:
                await client.beta.agents.delete_async(agent_id=ma.agent_id)
            except Exception as e:
                logger.warning(f"Failed to delete agent {ma.agent_id}: {e}")
            db.delete(ma)

        db.commit()
        logger.info(f"Deleted {len(agents)} agents for deal {deal_id}")

    @staticmethod
    def get_agent_id(db: Session, deal_id: str, section_key: str) -> str | None:
        """Look up the Mistral agent ID for a deal + section."""
        ma = (
            db.query(MistralAgent)
            .filter(
                MistralAgent.deal_id == deal_id,
                MistralAgent.section_key == section_key,
            )
            .first()
        )
        return ma.agent_id if ma else None

    # ── Agent-Based Generation ─────────────────────────────────────

    @staticmethod
    async def generate_with_agent(
        agent_id: str,
        section_title: str,
        section_description: str,
        expected_output: str,
        custom_instructions: str | None = None,
        output_template: str | None = None,
    ) -> str:
        """
        Generate narrative content using a Mistral Agent.
        The agent has document_library tool access for RAG.

        Returns the generated content string.
        """
        client = _get_client()

        # Build the user message
        user_parts = [
            f"Section: {section_title}",
            f"Description: {section_description}",
            f"Expected Output: {expected_output}",
        ]

        if custom_instructions and custom_instructions.strip():
            user_parts.append(
                f"\n--- Custom Instructions (follow this style/structure) ---\n"
                f"{custom_instructions}\n---"
            )

        if output_template and output_template.strip():
            user_parts.append(
                f"\n--- Output Template (MUST follow this structure) ---\n"
                f"{output_template}\n---\n"
                f"IMPORTANT: Your output MUST follow the exact markdown structure, "
                f"headings, and sections shown in the template above."
            )

        user_parts.append(
            "\nSearch the document library for relevant data, "
            "then generate the narrative. Use markdown formatting."
        )

        messages = [
            {"role": "user", "content": "\n".join(user_parts)},
        ]

        logger.info(f"Generating with agent {agent_id} for section: {section_title}")

        try:
            response = await client.agents.complete_async(
                agent_id=agent_id,
                messages=messages,
            )

            content = None
            if response.choices and response.choices[0].message:
                content = response.choices[0].message.content

            if not content:
                # Retry once with slightly different prompt
                logger.warning(f"Empty response from agent {agent_id}, retrying...")
                messages[0]["content"] += "\n\nPlease generate the complete section now."
                response = await client.agents.complete_async(
                    agent_id=agent_id,
                    messages=messages,
                )
                if response.choices and response.choices[0].message:
                    content = response.choices[0].message.content

            if not content:
                return f"[Generation failed — agent returned no content for {section_title}]"

            logger.info(f"Agent {agent_id} generated {len(content)} chars for {section_title}")
            return content

        except Exception as e:
            logger.error(f"Agent generation failed for {section_title}: {e}")
            raise

    # ── Accuracy Evaluation (non-agent, direct chat) ───────────────

    @staticmethod
    async def evaluate_accuracy(
        generated_content: str,
        section_title: str,
        has_library_docs: bool,
    ) -> dict[str, Any] | None:
        """
        Evaluate accuracy of generated content.
        Uses direct chat (not agent) since evaluation doesn't need library access.

        Returns accuracy dict or None if no docs to evaluate against.
        """
        if not has_library_docs:
            logger.info(f"No library docs — skipping accuracy for {section_title}")
            return None

        import json
        client = _get_client()

        evaluator_prompt = (
            "You are an accuracy evaluator for AI-generated credit analysis narratives. "
            "The narrative was generated by an AI agent that had access to a document library. "
            "Evaluate how well the narrative appears to be grounded in real data vs. potentially hallucinated.\n\n"
            "Assess:\n"
            "1. **Grounded claims**: Specific facts, figures, dates that appear data-backed\n"
            "2. **Inferred claims**: Reasonable analytical conclusions\n"
            "3. **Unsupported claims**: Generic statements or potentially fabricated specifics\n\n"
            "Return ONLY a valid JSON object (no markdown, no explanation outside JSON):\n"
            "{\n"
            '  "score": <integer 0-100>,\n'
            '  "grounded_claims": <integer>,\n'
            '  "inferred_claims": <integer>,\n'
            '  "unsupported_claims": <integer>,\n'
            '  "summary": "<1-2 sentence explanation>"\n'
            "}\n\n"
            "Scoring guide:\n"
            "- 90-100: Almost all claims appear specifically data-backed\n"
            "- 70-89: Most claims supported, some reasonable inferences\n"
            "- 50-69: Mixed — significant inferences or some unsupported claims\n"
            "- Below 50: Many generic or potentially fabricated claims"
        )

        # Truncate content for evaluation
        max_chars = 8_000
        excerpt = generated_content[:max_chars]
        if len(generated_content) > max_chars:
            excerpt += "\n\n[... truncated for evaluation ...]"

        user_message = (
            f"## Section: {section_title}\n\n"
            f"### Generated Narrative:\n{excerpt}\n\n"
            "Evaluate the accuracy. Return ONLY the JSON object."
        )

        try:
            response = await client.chat.complete_async(
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
                lines = [l for l in lines if not l.strip().startswith("```")]
                raw = "\n".join(lines).strip()

            result = json.loads(raw)

            score = max(0, min(100, int(result.get("score", 0))))
            accuracy = {
                "score": score,
                "grounded_claims": int(result.get("grounded_claims", 0)),
                "inferred_claims": int(result.get("inferred_claims", 0)),
                "unsupported_claims": int(result.get("unsupported_claims", 0)),
                "summary": str(result.get("summary", "Assessment completed.")),
            }

            logger.info(
                f"Accuracy for {section_title}: score={accuracy['score']}%, "
                f"grounded={accuracy['grounded_claims']}, "
                f"inferred={accuracy['inferred_claims']}, "
                f"unsupported={accuracy['unsupported_claims']}"
            )
            return accuracy

        except json.JSONDecodeError as e:
            logger.warning(f"Accuracy evaluator returned invalid JSON: {e}")
            return {
                "score": 0,
                "grounded_claims": 0,
                "inferred_claims": 0,
                "unsupported_claims": 0,
                "summary": "Accuracy assessment failed — could not parse evaluator response.",
            }
        except Exception as e:
            logger.error(f"Accuracy evaluation failed for {section_title}: {e}")
            return {
                "score": 0,
                "grounded_claims": 0,
                "inferred_claims": 0,
                "unsupported_claims": 0,
                "summary": f"Accuracy assessment error: {str(e)}",
            }
