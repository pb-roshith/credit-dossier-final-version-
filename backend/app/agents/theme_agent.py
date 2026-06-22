import json
import logging
import re
from typing import Optional
from pydantic import BaseModel

from mistralai.client import Mistral

from app.config import settings

logger = logging.getLogger(__name__)

class ThemeExtractionResponse(BaseModel):
    primary_color: str
    secondary_color: str

def extract_theme_from_text(document_text: str) -> Optional[ThemeExtractionResponse]:
    """
    Uses Mistral to extract the primary and secondary corporate hex colors 
    based on the brand/company identified in the text.
    """
    if not settings.MISTRAL_API_KEY:
        logger.warning("Mistral API key not configured, returning default theme.")
        return None

    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    
    system_prompt = (
        "You are an expert brand designer and data extractor. Your task is to identify "
        "the primary company or brand mentioned in the provided text. Based on your world "
        "knowledge of that brand, provide their 2 primary corporate hex colors.\n\n"
        "If you cannot identify the brand or their colors, return a default classic annual "
        "report theme (Primary: #002060, Secondary: #800020).\n\n"
        "Respond ONLY with a valid JSON object matching this schema:\n"
        "{\n"
        '  "primary_color": "#HEXCODE",\n'
        '  "secondary_color": "#HEXCODE"\n'
        "}\n"
    )

    truncated_text = document_text[:15000]

    try:
        response = client.chat.complete(
            model=settings.MISTRAL_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Document text:\n{truncated_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )
        
        content = response.choices[0].message.content
        logger.info(f"Theme extraction raw response: {content}")
        
        # Clean up any potential markdown code blocks
        clean_content = re.sub(r'```json\n?(.*?)\n?```', r'\1', content, flags=re.DOTALL).strip()
        data = json.loads(clean_content)
        
        primary = data.get("primary_color", "#002060")
        secondary = data.get("secondary_color", "#800020")
        
        # Simple validation
        if not re.match(r'^#[0-9a-fA-F]{6}$', primary): primary = "#002060"
        if not re.match(r'^#[0-9a-fA-F]{6}$', secondary): secondary = "#800020"
            
        return ThemeExtractionResponse(primary_color=primary, secondary_color=secondary)
    
    except Exception as e:
        logger.error(f"Error during theme extraction: {e}")
        return None
