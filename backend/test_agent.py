import asyncio
from mistralai.client import Mistral
import os
from dotenv import load_dotenv

load_dotenv()
client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

async def test():
    agent_id = "ag_019eef0f80e871ca86c1ccbb5811454e"
    messages = [
        {"role": "user", "content": "What is the revenue of Halfords?"}
    ]
    response = await client.agents.complete_async(
        agent_id=agent_id,
        messages=messages,
    )
    print(response)

if __name__ == "__main__":
    asyncio.run(test())
