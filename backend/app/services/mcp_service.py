import asyncio
import json
import logging
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.shared.exceptions import McpError

from app.config import settings

logger = logging.getLogger(__name__)


# ── Typed Responses ────────────────────────────────────────────────

@dataclass
class DocumentSummary:
    """Parsed document summary from MCP server."""
    title: str
    doc_type: str = ""
    summary: str = ""
    company_name: str = ""


class MCPClientService:
    _session: Optional[ClientSession] = None
    _exit_stack: Optional[AsyncExitStack] = None
    is_connected: bool = False

    # ── TTL Cache for document summaries ────────────────────────
    _summary_cache: Dict[str, tuple[str, float]] = {}  # key → (data, timestamp)

    # ── Circuit Breaker ────────────────────────────────────────
    _consecutive_failures: int = 0
    _circuit_open_until: float = 0.0  # timestamp

    @classmethod
    def _is_circuit_open(cls) -> bool:
        if cls._circuit_open_until > 0 and time.time() < cls._circuit_open_until:
            return True
        if cls._circuit_open_until > 0 and time.time() >= cls._circuit_open_until:
            # Reset circuit breaker — allow retry
            cls._circuit_open_until = 0.0
            cls._consecutive_failures = 0
        return False

    @classmethod
    def _record_failure(cls) -> None:
        cls._consecutive_failures += 1
        if cls._consecutive_failures >= settings.MCP_MAX_FAILURES:
            cls._circuit_open_until = time.time() + settings.MCP_CIRCUIT_BREAKER_SECONDS
            logger.warning(
                f"MCP circuit breaker OPEN — {cls._consecutive_failures} consecutive failures. "
                f"Will retry after {settings.MCP_CIRCUIT_BREAKER_SECONDS}s."
            )

    @classmethod
    def _record_success(cls) -> None:
        cls._consecutive_failures = 0
        cls._circuit_open_until = 0.0

    # ── Connection Management ──────────────────────────────────

    @classmethod
    async def connect(cls) -> None:
        if cls.is_connected:
            return
        logger.info("Connecting to MCP SSE server...")
        try:
            cls._exit_stack = AsyncExitStack()
            sse_transport = await cls._exit_stack.enter_async_context(
                sse_client("https://companydocmcpserver-production.up.railway.app/sse")
            )
            cls._session = await cls._exit_stack.enter_async_context(
                ClientSession(sse_transport[0], sse_transport[1])
            )
            await cls._session.initialize()
            cls.is_connected = True
            cls._record_success()
            logger.info("Connected to MCP server successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            cls.is_connected = False
            cls._record_failure()
            if cls._exit_stack:
                await cls._exit_stack.aclose()
                cls._exit_stack = None
            cls._session = None

    @classmethod
    async def disconnect(cls) -> None:
        if cls._exit_stack:
            await cls._exit_stack.aclose()
        cls._exit_stack = None
        cls._session = None
        cls.is_connected = False
        cls._summary_cache.clear()
        logger.info("Disconnected from MCP server.")

    @classmethod
    def _mark_disconnected(cls) -> None:
        """Mark the connection as dead (SSE dropped). Next call will auto-reconnect."""
        cls.is_connected = False
        cls._session = None
        # Don't close _exit_stack here — the SSE reader already errored out
        cls._exit_stack = None

    @classmethod
    async def _call_with_reconnect(cls, tool_name: str, arguments: dict) -> Any:
        """
        Call an MCP tool with automatic reconnection on SSE drops.

        If the SSE connection was dropped by Railway (RemoteProtocolError),
        this will:
        1. Mark the connection as dead
        2. Attempt one reconnection
        3. Retry the tool call
        """
        import httpx

        try:
            result = await cls._session.call_tool(tool_name, arguments=arguments)
            cls._record_success()
            return result
        except (httpx.RemoteProtocolError, httpx.ReadError,
                ConnectionError, OSError, BrokenPipeError) as e:
            logger.warning(
                f"MCP SSE connection dropped during {tool_name}: "
                f"{type(e).__name__}: {e}. Attempting reconnection..."
            )
            cls._mark_disconnected()
            cls._record_failure()

            # Attempt reconnection
            try:
                await cls.connect()
                if cls.is_connected and cls._session:
                    logger.info(f"MCP reconnected. Retrying {tool_name}...")
                    result = await cls._session.call_tool(tool_name, arguments=arguments)
                    cls._record_success()
                    return result
                else:
                    raise ConnectionError("Reconnection succeeded but session is None")
            except Exception as reconnect_err:
                logger.error(
                    f"MCP reconnection failed for {tool_name}: {reconnect_err}"
                )
                cls._record_failure()
                raise
        except Exception as e:
            # Non-connection errors (e.g. McpError from bad tool call)
            logger.error(f"MCP tool call {tool_name} failed: {e}")
            cls._record_failure()
            raise

    # ── Core Tool Calls ────────────────────────────────────────

    @classmethod
    async def list_companies(cls) -> List[Dict[str, Any]]:
        if not cls.is_connected or not cls._session:
            logger.warning("MCP client not connected. Returning empty company list.")
            return []
        if cls._is_circuit_open():
            logger.warning("MCP circuit breaker is OPEN. Skipping list_companies.")
            return []
        try:
            result = await cls._call_with_reconnect("list_companies", {})
            if result and result.content:
                text = result.content[0].text
                data = json.loads(text)
                if isinstance(data, dict) and "companies" in data:
                    return data["companies"]
                return data
            return []
        except Exception as e:
            logger.error(f"Error in list_companies (after reconnect attempt): {e}")
            return []

    @classmethod
    async def get_documents(cls, company_name: str) -> List[Dict[str, Any]]:
        if not cls.is_connected or not cls._session:
            return []
        if cls._is_circuit_open():
            return []
        try:
            result = await cls._call_with_reconnect(
                "retrieve_company_documents", {"company_name": company_name}
            )
            if result and result.content:
                text = result.content[0].text
                data = json.loads(text)
                if isinstance(data, dict) and "documents" in data:
                    return data["documents"]
                return data
            return []
        except Exception as e:
            logger.error(f"Error in get_documents for {company_name}: {e}")
            return []

    @classmethod
    async def get_company_details(cls, company_name: str) -> Dict[str, Any]:
        if not cls.is_connected or not cls._session:
            return {}
        if cls._is_circuit_open():
            return {}
        try:
            result = await cls._call_with_reconnect(
                "retrieve_company_details", {"company_name": company_name}
            )
            if result and result.content:
                text = result.content[0].text
                return json.loads(text)
            return {}
        except Exception as e:
            logger.error(f"Error in get_company_details for {company_name}: {e}")
            return {}

    @classmethod
    async def get_document_summaries(cls, company_name: str) -> str:
        if not cls.is_connected or not cls._session:
            return "MCP server disconnected. Summaries unavailable."
        if cls._is_circuit_open():
            return "MCP circuit breaker open. Summaries temporarily unavailable."
        try:
            result = await cls._call_with_reconnect(
                "retrieve_company_document_summaries",
                {"company_name": company_name},
            )
            if result and result.content:
                return result.content[0].text
            return "No summaries returned."
        except Exception as e:
            logger.error(f"Error calling retrieve_company_document_summaries for {company_name}: {e}")
            cls._record_failure()
            return f"Error: {e}"

    # ── Cached Document Summaries ──────────────────────────────

    @classmethod
    async def get_document_summaries_cached(
        cls,
        company_name: str,
        ttl_seconds: int | None = None,
    ) -> str:
        """
        Fetch document summaries with TTL caching.

        During draft-all, this is called 16 times (once per section) but
        the MCP server is only hit once. Subsequent calls return cached data.

        Args:
            company_name: Company to fetch summaries for
            ttl_seconds: Cache TTL override (defaults to settings.MCP_CACHE_TTL_SECONDS)

        Returns:
            Document summaries text (raw string from MCP)
        """
        ttl = ttl_seconds or settings.MCP_CACHE_TTL_SECONDS
        cache_key = company_name.lower().strip()
        now = time.time()

        # Check cache
        if cache_key in cls._summary_cache:
            cached_data, cached_at = cls._summary_cache[cache_key]
            if now - cached_at < ttl:
                logger.debug(f"MCP summary cache HIT for '{company_name}'")
                return cached_data

        # Cache miss — fetch fresh
        logger.info(f"MCP summary cache MISS for '{company_name}' — fetching fresh")
        summaries = await cls.get_document_summaries(company_name)

        # Only cache successful responses
        if not summaries.startswith(("Error:", "MCP")):
            cls._summary_cache[cache_key] = (summaries, now)

        return summaries

    @classmethod
    def invalidate_cache(cls, company_name: str | None = None) -> None:
        """Invalidate summary cache. Pass None to clear all."""
        if company_name:
            cls._summary_cache.pop(company_name.lower().strip(), None)
        else:
            cls._summary_cache.clear()

    @classmethod
    def get_health_status(cls) -> Dict[str, Any]:
        """Return MCP health info for the /api/health endpoint."""
        return {
            "connected": cls.is_connected,
            "circuit_breaker_open": cls._is_circuit_open(),
            "consecutive_failures": cls._consecutive_failures,
            "cache_entries": len(cls._summary_cache),
        }
