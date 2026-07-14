import asyncio
import json
import logging
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.shared.exceptions import McpError

from app.config import settings

logger = logging.getLogger(__name__)

# SSE endpoint for the remote MCP server
_MCP_SSE_URL = "https://companydocmcpserver-production.up.railway.app/sse"


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
    _keepalive_task: Optional[asyncio.Task] = None
    _connect_lock: asyncio.Lock = asyncio.Lock()

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
        """Connect to the remote MCP SSE server with lock to prevent races."""
        if cls.is_connected:
            return
        async with cls._connect_lock:
            # Double-check after acquiring lock
            if cls.is_connected:
                return
            logger.info("Connecting to MCP SSE server...")
            try:
                cls._exit_stack = AsyncExitStack()
                sse_transport = await cls._exit_stack.enter_async_context(
                    sse_client(_MCP_SSE_URL)
                )
                cls._session = await cls._exit_stack.enter_async_context(
                    ClientSession(sse_transport[0], sse_transport[1])
                )
                await cls._session.initialize()
                cls.is_connected = True
                cls._record_success()
                logger.info("Connected to MCP server successfully.")

                # Start background keepalive to prevent Railway idle timeout
                cls._start_keepalive()
            except Exception as e:
                logger.error(f"Failed to connect to MCP server: {e}")
                cls.is_connected = False
                cls._record_failure()
                if cls._exit_stack:
                    try:
                        await cls._exit_stack.aclose()
                    except Exception:
                        pass
                    cls._exit_stack = None
                cls._session = None

    @classmethod
    async def disconnect(cls) -> None:
        cls._stop_keepalive()
        if cls._exit_stack:
            try:
                await cls._exit_stack.aclose()
            except Exception:
                pass
        cls._exit_stack = None
        cls._session = None
        cls.is_connected = False
        cls._summary_cache.clear()
        logger.info("Disconnected from MCP server.")

    @classmethod
    def _mark_disconnected(cls) -> None:
        """Mark the connection as dead (SSE dropped). Next call will auto-reconnect."""
        cls._stop_keepalive()
        cls.is_connected = False
        cls._session = None
        # Don't close _exit_stack here — the SSE reader already errored out
        cls._exit_stack = None

    # ── Keepalive ──────────────────────────────────────────────

    @classmethod
    def _start_keepalive(cls) -> None:
        """Start a background task that pings the MCP server every 3 minutes.

        Railway kills idle SSE connections after ~5 min. This lightweight
        `list_companies` call keeps the connection warm without any side effects.
        """
        cls._stop_keepalive()  # cancel any prior task
        cls._keepalive_task = asyncio.create_task(cls._keepalive_loop())
        logger.info("MCP keepalive task started (interval=%ds)", settings.MCP_KEEPALIVE_INTERVAL)

    @classmethod
    def _stop_keepalive(cls) -> None:
        if cls._keepalive_task and not cls._keepalive_task.done():
            cls._keepalive_task.cancel()
            cls._keepalive_task = None

    @classmethod
    async def _keepalive_loop(cls) -> None:
        """Periodically send a lightweight MCP call to prevent SSE idle timeout."""
        interval = settings.MCP_KEEPALIVE_INTERVAL
        try:
            while True:
                await asyncio.sleep(interval)
                if not cls.is_connected or not cls._session:
                    logger.debug("MCP keepalive: not connected, skipping")
                    continue
                try:
                    # Use list_companies as a lightweight ping — it's a read-only call
                    await cls._session.call_tool("list_companies", arguments={})
                    logger.debug("MCP keepalive ping OK")
                except (httpx.RemoteProtocolError, httpx.ReadError,
                        ConnectionError, OSError, BrokenPipeError) as e:
                    logger.warning(
                        f"MCP keepalive detected dead connection: {type(e).__name__}: {e}. "
                        f"Will reconnect on next tool call."
                    )
                    cls._mark_disconnected()
                    cls._record_failure()
                    return  # exit loop; reconnect will restart keepalive
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.debug(f"MCP keepalive non-fatal error: {e}")
        except asyncio.CancelledError:
            logger.debug("MCP keepalive task cancelled")

    # ── Ensure Connected ───────────────────────────────────────

    @classmethod
    async def _ensure_connected(cls) -> bool:
        """Ensure the MCP connection is alive. Returns True if connected."""
        if cls.is_connected and cls._session:
            return True
        if cls._is_circuit_open():
            return False
        logger.info("MCP not connected — attempting auto-reconnect...")
        await cls.connect()
        return cls.is_connected and cls._session is not None

    @classmethod
    async def _call_with_reconnect(
        cls,
        tool_name: str,
        arguments: dict,
        max_retries: int = 2,
    ) -> Any:
        """
        Call an MCP tool with automatic reconnection on SSE drops.

        If the SSE connection was dropped by Railway (RemoteProtocolError),
        this will:
        1. Proactively ensure connection is alive
        2. Attempt the tool call
        3. On connection errors: mark disconnected, backoff, reconnect, retry
        4. Retry up to `max_retries` times with exponential backoff
        """
        # Proactive connection check
        if not await cls._ensure_connected():
            raise ConnectionError(
                f"MCP not connected and cannot reconnect (circuit breaker may be open)"
            )

        last_err: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                result = await cls._session.call_tool(tool_name, arguments=arguments)
                cls._record_success()
                return result
            except (httpx.RemoteProtocolError, httpx.ReadError,
                    ConnectionError, OSError, BrokenPipeError) as e:
                last_err = e
                logger.warning(
                    f"MCP SSE connection dropped during {tool_name} "
                    f"(attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}"
                )
                cls._mark_disconnected()
                cls._record_failure()

                if attempt < max_retries:
                    backoff = min(2 ** attempt, 8)  # 1s, 2s, capped at 8s
                    logger.info(
                        f"Backing off {backoff}s before reconnect attempt "
                        f"{attempt + 2}..."
                    )
                    await asyncio.sleep(backoff)
                    try:
                        await cls.connect()
                        if not cls.is_connected or not cls._session:
                            raise ConnectionError("Reconnection succeeded but session is None")
                        logger.info(f"MCP reconnected. Retrying {tool_name}...")
                    except Exception as reconnect_err:
                        logger.error(
                            f"MCP reconnection attempt {attempt + 2} failed: {reconnect_err}"
                        )
                        last_err = reconnect_err
            except Exception as e:
                # Non-connection errors (e.g. McpError from bad tool call) — don't retry
                logger.error(f"MCP tool call {tool_name} failed: {e}")
                cls._record_failure()
                raise

        # All retries exhausted
        logger.error(
            f"MCP tool call {tool_name} failed after {max_retries + 1} attempts"
        )
        raise last_err or ConnectionError(f"MCP call {tool_name} failed")

    # ── Core Tool Calls ────────────────────────────────────────

    @classmethod
    async def list_companies(cls) -> List[Dict[str, Any]]:
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
