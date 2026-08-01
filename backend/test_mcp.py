import asyncio
import os
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

async def run():
    mcp_url = os.getenv("MCP_SSE_URL", "http://127.0.0.1:8001/sse")
    async with sse_client(mcp_url) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.list_tools()
            for t in res.tools:
                print(f"Tool: {t.name} - {t.description}")

asyncio.run(run())
