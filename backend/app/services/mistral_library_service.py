"""
Mistral Library Service — manages Mistral Libraries, Agents, and Agent-based generation.

Handles:
- Library lifecycle (create, delete, list files)
- File upload to Mistral Library
- Agent lifecycle (create per section, delete on deal cleanup)
- Generation via Mistral Agents API (with document_library tool for RAG)
"""

from __future__ import annotations

import asyncio
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

# Timeout for Mistral API calls (5 minutes — agent RAG completions are slow)
_MISTRAL_TIMEOUT_MS = 300_000
# Retry configuration for transient errors (timeouts, 5xx, connection errors)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 5  # seconds


def _get_client():
    global _mistral_client
    if _mistral_client is None:
        from mistralai.client import Mistral
        _mistral_client = Mistral(
            api_key=settings.MISTRAL_API_KEY,
            timeout_ms=_MISTRAL_TIMEOUT_MS,
        )
    return _mistral_client


def _reset_client():
    """Force re-creation of the Mistral client (e.g. after config changes)."""
    global _mistral_client
    _mistral_client = None


async def _call_with_retry(coro_factory, description: str = "Mistral API call"):
    """
    Call a Mistral async API with automatic retry on transient errors.

    `coro_factory` must be a zero-arg callable that returns a *new* awaitable
    each time it is called (lambdas work well).
    """
    import httpx

    last_exc = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return await coro_factory()
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            last_exc = exc
            delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))  # 5, 10, 20
            logger.warning(
                f"{description}: timeout on attempt {attempt}/{_MAX_RETRIES} "
                f"({type(exc).__name__}). Retrying in {delay}s..."
            )
            await asyncio.sleep(delay)
        except httpx.HTTPStatusError as exc:
            # Retry on 5xx server errors only
            if exc.response.status_code >= 500:
                last_exc = exc
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"{description}: server error {exc.response.status_code} "
                    f"on attempt {attempt}/{_MAX_RETRIES}. Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                raise
        except (httpx.RemoteProtocolError, httpx.ReadError, ConnectionError, OSError) as exc:
            last_exc = exc
            delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                f"{description}: connection error on attempt {attempt}/{_MAX_RETRIES} "
                f"({type(exc).__name__}). Retrying in {delay}s..."
            )
            await asyncio.sleep(delay)

    # All retries exhausted
    logger.error(f"{description}: all {_MAX_RETRIES} attempts failed.")
    raise last_exc  # type: ignore[misc]


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

        # Upload document to Mistral library
        uploaded = await client.beta.libraries.documents.upload_async(
            library_id=deal.mistral_library_id,
            file={"file_name": filename, "content": file_bytes},
        )

        logger.info(
            f"Uploaded document {filename} to Mistral library (id={uploaded.id}) "
            f"for library {deal.mistral_library_id}"
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

        # Remove document from Mistral library
        if deal.mistral_library_id:
            try:
                await client.beta.libraries.documents.delete_async(
                    library_id=deal.mistral_library_id,
                    document_id=lib_file.mistral_file_id,
                )
            except Exception as e:
                logger.warning(f"Failed to remove document from library: {e}")

        db.delete(lib_file)
        db.commit()
        return True

    # ── Agent Management ───────────────────────────────────────────

    @staticmethod
    async def initialize_global_agents(db: Session) -> None:
        """Create the 16 global agents on startup if they don't exist."""
        client = _get_client()
        from app.services.deal_service import DEFAULT_SECTIONS

        logger.info("Initializing global Mistral agents...")
        for sec_def in DEFAULT_SECTIONS:
            section_key = sec_def["section_key"]
            section_title = sec_def["title"]

            existing = db.query(MistralAgent).filter(MistralAgent.section_key == section_key).first()
            if existing:
                continue

            instructions = get_instructions(section_key)
            agent = await client.beta.agents.create_async(
                model=settings.MISTRAL_AGENT_MODEL,
                name=f"GlobalAgent_{section_title}",
                instructions=instructions,
                completion_args={"temperature": 0.1},
            )
            
            ma = MistralAgent(section_key=section_key, agent_id=agent.id)
            db.add(ma)
        
        db.commit()
        logger.info("Global Mistral agents initialized.")

    @staticmethod
    async def cleanup_global_agents(db: Session) -> None:
        """Delete all global Mistral agents on shutdown."""
        client = _get_client()
        agents = db.query(MistralAgent).all()
        logger.info(f"Cleaning up {len(agents)} global Mistral agents...")
        
        for ma in agents:
            try:
                await client.beta.agents.delete_async(agent_id=ma.agent_id)
            except Exception as e:
                logger.warning(f"Failed to delete global agent {ma.agent_id}: {e}")
            db.delete(ma)
            
        db.commit()
        logger.info("Global Mistral agents cleaned up.")

    @staticmethod
    async def sync_agents_to_library(db: Session, library_id: str | None) -> None:
        """Sync all global agents to use the given library_id (or none)."""
        if not library_id:
            return

        client = _get_client()
        agents = db.query(MistralAgent).all()
        
        logger.info(f"Syncing {len(agents)} global agents to library {library_id}...")

        async def _update_one(ma: MistralAgent):
            try:
                await client.beta.agents.update_async(
                    agent_id=ma.agent_id,
                    tools=[{"type": "document_library", "library_ids": [library_id]}]
                )
            except Exception as e:
                logger.error(f"Failed to sync agent {ma.agent_id} to library {library_id}: {e}")

        import asyncio
        await asyncio.gather(*[_update_one(ma) for ma in agents])
        logger.info(f"Successfully synced global agents to library {library_id}.")

    @staticmethod
    def get_global_agent_id(db: Session, section_key: str) -> str | None:
        ma = db.query(MistralAgent).filter(MistralAgent.section_key == section_key).first()
        return ma.agent_id if ma else None

    # ── Agent-Based Generation ─────────────────────────────────────

    @staticmethod
    async def generate_with_agent(
        agent_id: str,
        section_title: str,
        section_description: str,
        expected_output: str,
        deal: Deal,
        custom_instructions: str | None = None,
        output_template: str | None = None,
    ) -> str:
        """
        Generate narrative content using a Mistral Agent.
        The agent has document_library tool access for RAG.

        Returns the generated content string.
        """
        client = _get_client()
        
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

        # Build the user message
        user_parts = [
            deal_ctx,
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
            response = await _call_with_retry(
                lambda: client.agents.complete_async(
                    agent_id=agent_id,
                    messages=messages,
                ),
                description=f"Agent completion for '{section_title}'",
            )

            content = None
            if getattr(response.choices[0], "message", None):
                content = response.choices[0].message.content
            elif getattr(response.choices[0], "messages", None) and len(response.choices[0].messages) > 0:
                content = response.choices[0].messages[-1].content

            if not content:
                # Retry once with slightly different prompt
                logger.warning(f"Empty response from agent {agent_id}, retrying...")
                messages[0]["content"] += "\n\nPlease generate the complete section now."
                response = await _call_with_retry(
                    lambda: client.agents.complete_async(
                        agent_id=agent_id,
                        messages=messages,
                    ),
                    description=f"Agent completion retry for '{section_title}'",
                )
                if getattr(response.choices[0], "message", None):
                    content = response.choices[0].message.content
                elif getattr(response.choices[0], "messages", None) and len(response.choices[0].messages) > 0:
                    content = response.choices[0].messages[-1].content

            if not content:
                return f"[Generation failed — agent returned no content for {section_title}]"

            # Normalize content — Mistral may return a list of content blocks
            if isinstance(content, list):
                # Join text parts; each element may be a dict with a "text" key or a plain string
                parts = []
                for part in content:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict) and "text" in part:
                        parts.append(part["text"])
                    elif hasattr(part, "text"):
                        parts.append(part.text)
                    else:
                        parts.append(str(part))
                content = "\n".join(parts)

            # Strip common preambles/search logs that Mistral sometimes outputs
            import re
            # Remove "Searching [xyz] for: ..." lines at the start. 
            # We match up to the first double newline, or heading, or bold text.
            content = re.sub(r'^Searching\s*\[.*?\].*?(?=\n\n|\n#|\n\*\*|$)', '', content, flags=re.IGNORECASE|re.DOTALL)
            # Remove "Here is the [xyz] section..." lines at the start
            content = re.sub(r'^\s*Here is the.*?based on the available documents:?\s*\n*', '', content, flags=re.IGNORECASE)
            
            content = content.strip()
            
            # Strip markdown fences if the agent wrapped the entire response in them
            content = re.sub(r'^```(?:markdown)?\s*\n', '', content, flags=re.IGNORECASE)
            content = re.sub(r'\n```\s*$', '', content)
            
            content = content.strip()

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
            response = await _call_with_retry(
                lambda: client.chat.complete_async(
                    model=settings.MISTRAL_MODEL,
                    messages=[
                        {"role": "system", "content": evaluator_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.1,
                    max_tokens=512,
                ),
                description=f"Accuracy evaluation for '{section_title}'",
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
