import asyncio
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

async def run():
    async with sse_client('https://companydocmcpserver-production.up.railway.app/sse') as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.list_tools()
            for t in res.tools:
                print(f"Tool: {t.name} - {t.description}")

asyncio.run(run())
