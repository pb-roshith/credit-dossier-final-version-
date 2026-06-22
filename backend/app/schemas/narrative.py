"""
Pydantic schemas for AI narrative generation.
"""

from typing import Optional
from pydantic import BaseModel


class NarrativeRequest(BaseModel):
    custom_instructions: Optional[str] = None


class NarrativeResponse(BaseModel):
    section_id: str
    section_key: str
    title: str
    generated_content: str
    state: str
    accuracy_score: Optional[float] = None
    accuracy_details: Optional[dict] = None


class DraftAllResponse(BaseModel):
    """Response when all sections are drafted in parallel."""
    results: list[NarrativeResponse]
    total: int
    succeeded: int
    failed: int

