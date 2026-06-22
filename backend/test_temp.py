import asyncio
from mistralai.client import Mistral
import os
from dotenv import load_dotenv

load_dotenv()
client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

async def test():
    print("creating agent")
    agent = await client.beta.agents.create_async(
        name="test_agent_temp",
        model="mistral-large-latest",
        completion_args={"temperature": 0.1},
    )
    print("agent created", agent.id)

if __name__ == "__main__":
    asyncio.run(test())
