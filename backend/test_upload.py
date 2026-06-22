import asyncio
from mistralai.client import Mistral
import os
from dotenv import load_dotenv

load_dotenv()
client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

async def test():
    for purpose in ['ocr', 'code_interpreter', 'evaluation', 'playground']:
        print(f"Testing purpose: {purpose}")
        try:
            uploaded = await client.files.upload_async(
                file={"file_name": "test.txt", "content": b"Hello world"},
                purpose=purpose,
            )
            print(f"Success! file_id: {uploaded.id}")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
