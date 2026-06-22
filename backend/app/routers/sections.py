"""
Sections API router — section management, narrative generation, and template management.
"""

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas.deal import SectionResponse, SectionUpdate
from app.schemas.narrative import NarrativeRequest, NarrativeResponse, DraftAllResponse
from app.services.deal_service import DealService
from app.services.narrative_service import NarrativeService
from app.services.ingestion_service import extract_text_preview

router = APIRouter(prefix="/api/deals/{deal_id}/sections", tags=["sections"])


@router.get("", response_model=list[SectionResponse])
def list_sections(deal_id: str, db: Session = Depends(get_db)):
    """List all sections for a deal."""
    deal = DealService.get_deal(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal.sections


@router.patch("/{section_id}", response_model=SectionResponse)
def update_section(
    deal_id: str,
    section_id: str,
    data: SectionUpdate,
    db: Session = Depends(get_db),
):
    """Update section expected output, custom instructions, output template, or state."""
    section = DealService.update_section(db, section_id, data.model_dump(exclude_unset=True))
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    DealService.update_deal_status_from_sections(db, deal_id)
    return section


@router.post("/{section_id}/generate", response_model=NarrativeResponse)
async def generate_narrative(
    deal_id: str,
    section_id: str,
    body: NarrativeRequest | None = None,
    db: Session = Depends(get_db),
):
    """Generate AI narrative for a single section using its dedicated Mistral agent."""
    custom_instructions = body.custom_instructions if body else None
    section = await NarrativeService.generate_section(
        db, deal_id, section_id, custom_instructions
    )
    if not section:
        raise HTTPException(status_code=404, detail="Deal or section not found")
    return NarrativeResponse(
        section_id=section.id,
        section_key=section.section_key,
        title=section.title,
        generated_content=section.generated_content or "",
        state=section.state,
    )


@router.post("/generate-all", response_model=DraftAllResponse)
async def draft_all_sections(deal_id: str, db: Session = Depends(get_db)):
    """
    Generate narratives for ALL sections in parallel.
    Each section has its own dedicated Mistral agent.
    All agents run concurrently via asyncio.gather().
    """
    results = await NarrativeService.draft_all(db, deal_id)
    if not results:
        raise HTTPException(status_code=404, detail="Deal not found")

    succeeded = sum(1 for r in results if r.get("success"))
    return DraftAllResponse(
        results=[
            NarrativeResponse(
                section_id=r["section_id"],
                section_key=r["section_key"],
                title=r["title"],
                generated_content=r["generated_content"],
                state=r["state"],
            )
            for r in results
        ],
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )


# ── Template Management ────────────────────────────────────────

SUPPORTED_TEMPLATE_EXTENSIONS = {".md", ".txt", ".docx", ".doc"}


@router.post("/{section_id}/template", response_model=SectionResponse)
async def upload_template(
    deal_id: str,
    section_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload an output template file for a section.
    Supports .md, .txt, and .docx files.
    The template content is extracted and stored as markdown text
    that the AI agent will follow when generating the narrative.
    """
    section = DealService.get_section(db, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    # Validate file extension
    filename = file.filename or "template"
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_TEMPLATE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported template format: {ext}. "
                   f"Supported: {', '.join(SUPPORTED_TEMPLATE_EXTENSIONS)}"
        )

    file_bytes = await file.read()

    # Save template file to disk
    template_dir = settings.upload_path / deal_id / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    file_path = template_dir / safe_name

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # Extract text content from the template file
    template_text = extract_text_preview(file_bytes, filename)

    # Update section with template
    section.output_template = template_text
    section.template_file_path = str(file_path)
    db.commit()
    db.refresh(section)

    return section


@router.delete("/{section_id}/template", response_model=SectionResponse)
def delete_template(
    deal_id: str,
    section_id: str,
    db: Session = Depends(get_db),
):
    """Remove the output template from a section."""
    section = DealService.get_section(db, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    # Delete template file from disk
    if section.template_file_path and os.path.exists(section.template_file_path):
        try:
            os.remove(section.template_file_path)
        except Exception:
            pass

    section.output_template = None
    section.template_file_path = None
    db.commit()
    db.refresh(section)

    return section
