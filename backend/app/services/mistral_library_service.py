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
import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.deal import Deal
from app.models.mistral_agent import MistralAgent
from app.models.library_file import LibraryFile
from app.agents.instructions import get_instructions
from app.telemetry import (
    setup_telemetry,
    get_tracer,
    set_span_attributes,
    set_gen_ai_attributes,
)

logger = logging.getLogger(__name__)

# Lazy Mistral client
_mistral_client = None

# Timeout for Mistral API calls (5 minutes — agent RAG completions are slow)
_MISTRAL_TIMEOUT_MS = 300_000
# Retry configuration for transient errors (timeouts, 5xx, connection errors)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 5  # seconds


def normalize_inline_sources(content: str) -> str:
    """Convert legacy numbered references into inline source-name markers."""
    reference_section = re.search(
        r"\n{0,2}#{1,6}\s*(?:References|Sources)\b(?P<body>.*)\Z",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not reference_section:
        return content.strip()

    references: dict[str, str] = {}
    for number, document_name in re.findall(
        r"\[(\d{1,2})\]\s*\[\[([^\]]+)\]\]",
        reference_section.group("body"),
    ):
        references[number] = document_name.strip()

    narrative = content[: reference_section.start()].rstrip()
    for number, document_name in references.items():
        narrative = re.sub(
            rf"[ \t]*\[{re.escape(number)}\]",
            f" [Source : {document_name}]",
            narrative,
        )
    return narrative.strip()


def clean_generation_artifacts(content: str) -> tuple[str, bool]:
    """Remove internal library-search traces and report whether any leaked."""
    patterns = (
        r'(?im)^[ \t]*\{[ \t]*["\']query["\'][ \t]*:[^\r\n}]*\}[ \t]*$',
        r"(?im)^[ \t]*(?:searching|search query)\b[^\r\n]*$",
    )
    leaked = any(re.search(pattern, content) for pattern in patterns)
    for pattern in patterns:
        content = re.sub(pattern, "", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip(), leaked


def repair_inline_source_markers(content: str) -> str:
    """Repair source markers split or partially emitted by the model."""
    malformed_source = re.compile(
        r"(?m)\n[ \t]*:[ \t]*(?P<source>[^\r\n|\]]+?)[ \t]*\]?[ \t]*(?=$|\n|\|)"
    )

    def replace_source(match: re.Match[str]) -> str:
        source = match.group("source").strip().rstrip(".")
        return f" [Source : {source}]"

    content = malformed_source.sub(replace_source, content)
    content = re.sub(
        r"(?im)^[ \t]*data for ([^\r\n]+?)[.]?[ \t]*$",
        r"[Insufficient data for \1.]",
        content,
    )
    return content.strip()


def _get_client():
    global _mistral_client
    if _mistral_client is None:
        from mistralai.client import Mistral
        _mistral_client = Mistral(
            api_key=settings.MISTRAL_API_KEY,
            timeout_ms=_MISTRAL_TIMEOUT_MS,
        )
        # Configure Mistral telemetry on first client creation
        setup_telemetry(_mistral_client)
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

    @staticmethod
    async def get_document_download_url(
        library_id: str,
        document_id: str,
    ) -> str:
        """Resolve a Mistral Library document to a temporary HTTPS URL."""
        client = _get_client()
        return await client.beta.libraries.documents.get_signed_url_async(
            library_id=library_id,
            document_id=document_id,
        )

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
        tracer = get_tracer()

        def _do_create():
            return client.beta.libraries.create_async(
                name=f"CreditDossier_{deal.customer}_{deal.id}",
                description=f"Document library for credit dossier — {deal.customer}",
            )

        if tracer:
            with tracer.start_as_current_span("create_library") as span:
                set_span_attributes(span,
                    deal_id=str(deal.id),
                    customer=deal.customer or "",
                    operation="create_library",
                )
                set_gen_ai_attributes(span, system="mistral")
                library = await _do_create()
                span.set_attribute("credit_dossier.library_id", library.id)
        else:
            library = await _do_create()

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

    @staticmethod
    def library_ids_for_deal(deal: Deal) -> list[str]:
        """Return source and deal-upload libraries without duplicate IDs."""
        library_ids: list[str] = []
        if deal.company_mistral_library_id:
            library_ids.append(deal.company_mistral_library_id)

        # Older deals may still have copied MCP files in their deal library.
        # Do not search that duplicate library unless it also has deal uploads.
        deal_files = list(getattr(deal, "library_files", []) or [])
        has_deal_specific_files = any(
            item.source_type != "mcp_auto" for item in deal_files
        )
        if (
            deal.mistral_library_id
            and (
                not deal.company_mistral_library_id
                or has_deal_specific_files
            )
            and deal.mistral_library_id not in library_ids
        ):
            library_ids.append(deal.mistral_library_id)
        return library_ids

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
        tracer = get_tracer()

        # Ensure library exists
        if not deal.mistral_library_id:
            await MistralLibraryService.create_library(db, deal)

        # Upload document to Mistral library
        async def _do_upload():
            return await client.beta.libraries.documents.upload_async(
                library_id=deal.mistral_library_id,
                file={"file_name": filename, "content": file_bytes},
            )

        if tracer:
            with tracer.start_as_current_span("upload_file") as span:
                set_span_attributes(span,
                    deal_id=str(deal.id),
                    filename=filename,
                    source_type=source_type,
                    file_size_bytes=str(len(file_bytes)),
                    library_id=deal.mistral_library_id or "",
                    operation="upload_file",
                )
                set_gen_ai_attributes(span, system="mistral")
                uploaded = await _do_upload()
                span.set_attribute("credit_dossier.mistral_file_id", uploaded.id)
        else:
            uploaded = await _do_upload()

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

    @staticmethod
    async def remove_legacy_mcp_copies(db: Session, deal: Deal) -> int:
        """Delete MCP files copied by the old sync pipeline after direct linking."""
        if not deal.company_mistral_library_id or not deal.mistral_library_id:
            return 0
        if deal.company_mistral_library_id == deal.mistral_library_id:
            return 0

        copied_files = (
            db.query(LibraryFile)
            .filter(
                LibraryFile.deal_id == deal.id,
                LibraryFile.source_type == "mcp_auto",
            )
            .all()
        )
        if not copied_files:
            return 0

        client = _get_client()
        removed = 0
        for library_file in copied_files:
            try:
                await client.beta.libraries.documents.delete_async(
                    library_id=deal.mistral_library_id,
                    document_id=library_file.mistral_file_id,
                )
            except Exception as exc:
                # A missing remote document means the duplicate is already gone.
                if "404" not in str(exc) and "not found" not in str(exc).lower():
                    logger.warning(
                        "Could not remove legacy MCP copy %s: %s",
                        library_file.filename,
                        exc,
                    )
                    continue
            db.delete(library_file)
            removed += 1

        db.commit()

        remaining = (
            db.query(LibraryFile)
            .filter(LibraryFile.deal_id == deal.id)
            .count()
        )
        if remaining == 0 and deal.mistral_library_id:
            empty_library_id = deal.mistral_library_id
            await MistralLibraryService.delete_library(empty_library_id)
            deal.mistral_library_id = None
            db.commit()

        logger.info(
            "Removed %s legacy copied MCP files from deal %s",
            removed,
            deal.id,
        )
        return removed

    # ── Agent Management ───────────────────────────────────────────

    @staticmethod
    async def initialize_global_agents(db: Session) -> None:
        """Create the 16 section agents + 1 orchestration agent on startup."""
        client = _get_client()
        tracer = get_tracer()
        from app.services.deal_service import DEFAULT_SECTIONS

        logger.info("Initializing global Mistral agents...")

        async def _do_init():
            # ── Create 16 section-specific agents ────────────────────
            created_count = 0
            for sec_def in DEFAULT_SECTIONS:
                section_key = sec_def["section_key"]
                section_title = sec_def["title"]

                existing = db.query(MistralAgent).filter(MistralAgent.section_key == section_key).first()
                if existing:
                    await client.beta.agents.update_async(
                        agent_id=existing.agent_id,
                        instructions=get_instructions(section_key),
                    )
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
                created_count += 1
                logger.info(f"Created section agent: {section_title} ({agent.id})")
            
            db.commit()

            # ── Create orchestration agent (fixed system prompt, dynamic user prompt) ──
            try:
                existing_orch = db.query(MistralAgent).filter(
                    MistralAgent.section_key == "orchestration"
                ).first()

                if not existing_orch:
                    from app.agents.orchestration_prompts import ORCHESTRATION_SYSTEM_PROMPT

                    orch_agent = await client.beta.agents.create_async(
                        model=settings.MISTRAL_AGENT_MODEL,
                        name="GlobalAgent_Orchestration",
                        instructions=ORCHESTRATION_SYSTEM_PROMPT,
                        completion_args={"temperature": 0.1},
                    )
                    ma_orch = MistralAgent(
                        section_key="orchestration", agent_id=orch_agent.id
                    )
                    db.add(ma_orch)
                    db.commit()
                    created_count += 1
                    logger.info(f"Created orchestration agent: {orch_agent.id}")
                else:
                    logger.info(f"Orchestration agent already exists: {existing_orch.agent_id}")
            except Exception as e:
                logger.error(f"Failed to create orchestration agent: {e}")

            return created_count

        if tracer:
            with tracer.start_as_current_span("initialize_agents") as span:
                set_span_attributes(span,
                    operation="initialize_agents",
                    model=settings.MISTRAL_AGENT_MODEL,
                )
                set_gen_ai_attributes(span, system="mistral")
                created = await _do_init()
                span.set_attribute("credit_dossier.agents_created", str(created))
        else:
            await _do_init()

        logger.info("Global Mistral agents initialized.")

    @staticmethod
    async def cleanup_global_agents(db: Session) -> None:
        """Delete all global Mistral agents on shutdown."""
        client = _get_client()
        tracer = get_tracer()
        agents = db.query(MistralAgent).all()
        agent_count = len(agents)
        logger.info(f"Cleaning up {agent_count} global Mistral agents...")

        async def _do_cleanup():
            for ma in agents:
                try:
                    if ma.section_key == "mcp_connector":
                        await client.beta.connectors.delete_async(connector_id=ma.agent_id)
                    else:
                        await client.beta.agents.delete_async(agent_id=ma.agent_id)
                except Exception as e:
                    logger.warning(f"Failed to delete global agent/connector {ma.agent_id}: {e}")
                db.delete(ma)
                
            db.commit()

        if tracer:
            with tracer.start_as_current_span("cleanup_agents") as span:
                set_span_attributes(span,
                    operation="cleanup_agents",
                    agent_count=str(agent_count),
                )
                set_gen_ai_attributes(span, system="mistral")
                await _do_cleanup()
        else:
            await _do_cleanup()

        logger.info("Global Mistral agents cleaned up.")

    @staticmethod
    async def sync_agents_to_libraries(
        db: Session,
        library_ids: list[str],
    ) -> None:
        """Configure all global agents to search the supplied libraries."""
        library_ids = list(dict.fromkeys(item for item in library_ids if item))
        if not library_ids:
            return

        client = _get_client()
        # Fetch all agents except the MCP connector, which is not an agent
        agents = db.query(MistralAgent).filter(MistralAgent.section_key != "mcp_connector").all()
        
        logger.info(
            "Syncing %s global agents to %s libraries...",
            len(agents),
            len(library_ids),
        )

        async def _update_one(ma: MistralAgent):
            try:
                await client.beta.agents.update_async(
                    agent_id=ma.agent_id,
                    tools=[{
                        "type": "document_library",
                        "library_ids": library_ids,
                    }]
                )
            except Exception as e:
                logger.error(
                    "Failed to sync agent %s to libraries %s: %s",
                    ma.agent_id,
                    library_ids,
                    e,
                )

        import asyncio
        await asyncio.gather(*[_update_one(ma) for ma in agents])
        logger.info("Successfully synced global agents to %s.", library_ids)

    @staticmethod
    async def sync_agents_to_library(
        db: Session,
        library_id: str | None,
    ) -> None:
        """Backward-compatible wrapper for callers with one library."""
        await MistralLibraryService.sync_agents_to_libraries(
            db,
            [library_id] if library_id else [],
        )

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
        deal_context: str,
        structured_data: str | None = None,
        orchestration_strategy: str | None = None,
        custom_instructions: str | None = None,
        output_template: str | None = None,
    ) -> str:
        """
        Generate narrative content using a Mistral Agent.
        The agent has document_library tool access for RAG.

        Args:
            agent_id: Mistral Agent ID for this section
            section_title: Human-readable section title
            section_description: What the section covers
            expected_output: What the output should look like
            deal_context: Pre-built, section-specific deal context string
            structured_data: Relevant company rows from PostgreSQL credit tables
            orchestration_strategy: Strategy text from OrchestrationService
            custom_instructions: User-provided style/structure instructions
            output_template: User-provided markdown template

        Returns:
            Generated content string (markdown)
        """
        client = _get_client()
        tracer = get_tracer()

        # Build the user message
        user_parts = [
            deal_context,
            f"Section: {section_title}",
            f"Description: {section_description}",
            f"Expected Output: {expected_output}",
        ]

        if structured_data and structured_data.strip():
            user_parts.append(
                "\n--- Structured PostgreSQL Credit Data ---\n"
                f"{structured_data}\n"
                "--- End Structured Data ---\n"
                "Use these structured rows together with the PDF library. "
                "Treat explicit table values as the primary source for numeric "
                "financials, facilities, collateral, covenants, and exceptions. "
                "Reconcile differences with the PDFs and do not invent missing values."
            )

        # Inject orchestration strategy (from OrchestrationService)
        if orchestration_strategy and orchestration_strategy.strip():
            user_parts.append(
                f"\n--- Orchestration Strategy (use to guide your search) ---\n"
                f"{orchestration_strategy}\n---\n"
                f"Prioritize the recommended documents and data points above."
            )

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
            "then generate the narrative. Use markdown formatting. "
            "Put the source directly after each sourced statement using "
            "[Source : Exact_Document_Name.pdf], or "
            "[Source : PostgreSQL.table_name] for structured data. "
            "Do not add a References or Sources section at the bottom."
        )

        messages = [
            {"role": "user", "content": "\n".join(user_parts)},
        ]

        logger.info(f"Generating with agent {agent_id} for section: {section_title}")

        # Determine generation mode for span attributes
        gen_mode = "few-shot" if custom_instructions else "zero-shot"
        has_template = bool(output_template and output_template.strip())
        has_orch = bool(orchestration_strategy and orchestration_strategy.strip())
        has_structured_data = bool(structured_data and structured_data.strip())

        try:
            # Wrap the entire generation in a telemetry span
            span_ctx = None
            if tracer:
                span_ctx = tracer.start_as_current_span("generate_section")
                span = span_ctx.__enter__()
                set_span_attributes(span,
                    operation="generate_section",
                    section_title=section_title,
                    agent_id=agent_id,
                    generation_mode=gen_mode,
                    has_template=str(has_template),
                    has_orchestration=str(has_orch),
                    has_structured_data=str(has_structured_data),
                )
                set_gen_ai_attributes(span,
                    agent_name=f"section_agent_{section_title}",
                    system="mistral",
                    request_model=settings.MISTRAL_AGENT_MODEL,
                )

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
                if tracer and span_ctx:
                    span.set_attribute("credit_dossier.retried", "true")
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
                if tracer and span_ctx:
                    span.set_attribute("credit_dossier.result", "empty")
                    span_ctx.__exit__(None, None, None)
                return f"[Generation failed — agent returned no content for {section_title}]"

            # Normalize content — Mistral may return a list of content blocks
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict) and part.get("type", "text") == "text" and "text" in part:
                        parts.append(part["text"])
                    elif getattr(part, "type", "text") == "text" and hasattr(part, "text"):
                        parts.append(part.text)
                content = "\n".join(parts)

            # Strip common preambles/search logs that Mistral sometimes outputs
            content = re.sub(r'^Searching\s*\[.*?\].*?(?=\n\n|\n#|\n\*\*|$)', '', content, flags=re.IGNORECASE|re.DOTALL)
            content = re.sub(r'^\s*Here is the.*?based on the available documents:?\s*\n*', '', content, flags=re.IGNORECASE)
            content, leaked_search = clean_generation_artifacts(content)

            if leaked_search:
                logger.warning(
                    "Agent %s leaked a search query for %s; retrying complete output",
                    agent_id,
                    section_title,
                )
                messages[0]["content"] += (
                    "\n\nYour previous attempt exposed an internal JSON search query "
                    "and stopped early. Use document-library search internally, "
                    "but never print queries, tool calls, JSON, or search logs. "
                    "Return the complete final narrative for every required "
                    "subsection, with inline [Source : source_name] markers."
                )
                retry_response = await _call_with_retry(
                    lambda: client.agents.complete_async(
                        agent_id=agent_id,
                        messages=messages,
                    ),
                    description=f"Artifact-free retry for '{section_title}'",
                )
                retry_content = None
                if getattr(retry_response.choices[0], "message", None):
                    retry_content = retry_response.choices[0].message.content
                elif (
                    getattr(retry_response.choices[0], "messages", None)
                    and retry_response.choices[0].messages
                ):
                    retry_content = retry_response.choices[0].messages[-1].content
                if isinstance(retry_content, list):
                    retry_content = "\n".join(
                        part if isinstance(part, str) else (
                            part.get("text", "") if isinstance(part, dict)
                            else getattr(part, "text", "")
                        )
                        for part in retry_content
                    )
                if retry_content:
                    cleaned_retry, _ = clean_generation_artifacts(retry_content)
                    if len(cleaned_retry) > len(content):
                        content = cleaned_retry
            
            # Strip markdown fences if the agent wrapped the entire response in them
            content = re.sub(r'^```(?:markdown)?\s*\n', '', content, flags=re.IGNORECASE)
            content = re.sub(r'\n```\s*$', '', content)
            
            content = repair_inline_source_markers(content)
            content = normalize_inline_sources(content)

            # Set result attributes on the span
            if tracer and span_ctx:
                set_span_attributes(span,
                    result="success",
                    content_length=str(len(content)),
                )
                span_ctx.__exit__(None, None, None)

            logger.info(f"Agent {agent_id} generated {len(content)} chars for {section_title}")
            return content

        except Exception as e:
            if tracer and span_ctx:
                span.set_attribute("credit_dossier.result", "error")
                span.set_attribute("credit_dossier.error", str(e))
                span_ctx.__exit__(type(e), e, e.__traceback__)
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
        tracer = get_tracer()

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

        # Start telemetry span for accuracy evaluation
        span_ctx = None
        span = None
        if tracer:
            span_ctx = tracer.start_as_current_span("evaluate_accuracy")
            span = span_ctx.__enter__()
            set_span_attributes(span,
                operation="evaluate_accuracy",
                section_title=section_title,
                content_length=str(len(generated_content)),
            )
            set_gen_ai_attributes(span,
                system="mistral",
                request_model=settings.MISTRAL_MODEL,
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

            # Record accuracy result in span
            if span:
                set_span_attributes(span,
                    accuracy_score=str(score),
                    grounded_claims=str(accuracy["grounded_claims"]),
                    unsupported_claims=str(accuracy["unsupported_claims"]),
                    result="success",
                )

            logger.info(
                f"Accuracy for {section_title}: score={accuracy['score']}%, "
                f"grounded={accuracy['grounded_claims']}, "
                f"inferred={accuracy['inferred_claims']}, "
                f"unsupported={accuracy['unsupported_claims']}"
            )

            if span_ctx:
                span_ctx.__exit__(None, None, None)
            return accuracy

        except json.JSONDecodeError as e:
            logger.warning(f"Accuracy evaluator returned invalid JSON: {e}")
            if span:
                span.set_attribute("credit_dossier.result", "json_error")
            if span_ctx:
                span_ctx.__exit__(type(e), e, e.__traceback__)
            return {
                "score": 0,
                "grounded_claims": 0,
                "inferred_claims": 0,
                "unsupported_claims": 0,
                "summary": "Accuracy assessment failed — could not parse evaluator response.",
            }
        except Exception as e:
            logger.error(f"Accuracy evaluation failed for {section_title}: {e}")
            if span:
                set_span_attributes(span, result="error", error=str(e))
            if span_ctx:
                span_ctx.__exit__(type(e), e, e.__traceback__)
            return {
                "score": 0,
                "grounded_claims": 0,
                "inferred_claims": 0,
                "unsupported_claims": 0,
                "summary": f"Accuracy assessment error: {str(e)}",
            }
