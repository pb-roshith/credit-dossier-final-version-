import asyncio
import json
import logging
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.shared.exceptions import McpError

logger = logging.getLogger(__name__)

class MCPClientService:
    _session: Optional[ClientSession] = None
    _exit_stack: Optional[AsyncExitStack] = None
    is_connected: bool = False
    
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
            logger.info("Connected to MCP server successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            cls.is_connected = False
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
        logger.info("Disconnected from MCP server.")
        
    @classmethod
    async def list_companies(cls) -> List[Dict[str, Any]]:
        if not cls.is_connected or not cls._session:
            logger.warning("MCP client not connected. Returning empty company list.")
            return []
        try:
            result = await cls._session.call_tool("list_companies", arguments={})
            if result and result.content:
                text = result.content[0].text
                data = json.loads(text)
                if isinstance(data, dict) and "companies" in data:
                    return data["companies"]
                return data
            return []
        except Exception as e:
            logger.error(f"Error calling list_companies on MCP: {e}")
            return []

    @classmethod
    async def get_documents(cls, company_name: str) -> List[Dict[str, Any]]:
        if not cls.is_connected or not cls._session:
            return []
        try:
            result = await cls._session.call_tool("retrieve_company_documents", arguments={"company_name": company_name})
            if result and result.content:
                text = result.content[0].text
                data = json.loads(text)
                if isinstance(data, dict) and "documents" in data:
                    return data["documents"]
                return data
            return []
        except Exception as e:
            logger.error(f"Error calling retrieve_company_documents for {company_name}: {e}")
            return []
            
    @classmethod
    async def get_company_details(cls, company_name: str) -> Dict[str, Any]:
        if not cls.is_connected or not cls._session:
            return {}
        try:
            result = await cls._session.call_tool("retrieve_company_details", arguments={"company_name": company_name})
            if result and result.content:
                text = result.content[0].text
                return json.loads(text)
            return {}
        except Exception as e:
            logger.error(f"Error calling retrieve_company_details for {company_name}: {e}")
            return {}
            
    @classmethod
    async def get_document_summaries(cls, company_name: str) -> str:
        if not cls.is_connected or not cls._session:
            return "MCP server disconnected. Summaries unavailable."
        try:
            result = await cls._session.call_tool("retrieve_company_document_summaries", arguments={"company_name": company_name})
            if result and result.content:
                return result.content[0].text
            return "No summaries returned."
        except Exception as e:
            logger.error(f"Error calling retrieve_company_document_summaries for {company_name}: {e}")
            return f"Error: {e}"
