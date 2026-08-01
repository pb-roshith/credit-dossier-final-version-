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
    orchestration_strategy: Optional[str] = None
    timing: Optional[dict] = None


class DraftAllResponse(BaseModel):
    """Response when all sections are drafted in parallel."""
    results: list[NarrativeResponse]
    total: int
    succeeded: int
    failed: int


class DraftSectionProgress(BaseModel):
    section_id: str
    title: str
    status: str
    stage: str


class DraftAllJobResponse(BaseModel):
    job_id: str
    deal_id: str
    status: str
    percent: int
    completed: int
    failed: int
    total: int
    sections: list[DraftSectionProgress]
    error: Optional[str] = None

