"""
Uploads API router — file, URL, and text upload for section grounding.
"""


from typing import Annotated
from fastapi import Path as InputPath
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from pydantic import AfterValidator
from app.schemas.input_validation import validate_markdown_text, validate_source_url
from app.database import get_db
from app.schemas.upload import UploadResponse
from app.services.ingestion_service import IngestionService
from app.services.deal_service import DealService
from app.auth import get_current_user, require_deal_owner
from app.models.deal import Deal, Section
from app.models.upload import Upload
from app.models.user import User
from app.file_validation import read_uploaded_file, UploadValidationError, validate_uploaded_file

router = APIRouter(tags=["uploads"])


@router.post(
    "/api/deals/{deal_id}/sections/{section_id}/uploads",
    response_model=UploadResponse,
    status_code=201,
    dependencies=[Depends(require_deal_owner)],
)
async def create_upload(
    deal_id: Annotated[str, InputPath(min_length=1, max_length=128)],
    section_id: Annotated[str, InputPath(min_length=1, max_length=128)],
    source_type: Literal["file", "url", "text"] = Form(...),
    file: UploadFile | None = File(None),
    url: Annotated[str | None, Form(max_length=2048), AfterValidator(validate_source_url)] = None,
    text_content: Annotated[str | None, Form(max_length=500_000), AfterValidator(validate_markdown_text)] = None,
    note: Annotated[str | None, Form(max_length=4000), AfterValidator(validate_markdown_text)] = None,
    db: Session = Depends(get_db),
):
    """
    Upload a grounding input for a section.
    - source_type='file': upload a file (PDF, DOCX, XLSX, PPTX, CSV, TXT, etc.)
    - source_type='url': provide a URL to fetch content from
    - source_type='text': paste text directly
    
    Uploaded content is sent to Mistral's Document Library for managed RAG.
    Mistral handles OCR, chunking, embedding, and retrieval automatically.
    """
    # Validate section exists
    section = db.query(Section).filter(
        Section.id == section_id,
        Section.deal_id == deal_id,
    ).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    if source_type == "file":
        if not file:
            raise HTTPException(status_code=400, detail="File is required for source_type='file'")
        file_bytes = await read_uploaded_file(file)
        try:
            filename = validate_uploaded_file(file.filename, file_bytes)
        except UploadValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        upload = await IngestionService.process_file_upload(
            db, section_id, deal_id, file_bytes, filename, note
        )
    elif source_type == "url":
        if not url:
            raise HTTPException(status_code=400, detail="URL is required for source_type='url'")
        upload = await IngestionService.process_url_upload(db, section_id, deal_id, url, note)
    elif source_type == "text":
        if not text_content:
            raise HTTPException(status_code=400, detail="text_content is required for source_type='text'")
        upload = await IngestionService.process_text_upload(db, section_id, deal_id, text_content, note)
    else:
        raise HTTPException(status_code=400, detail="source_type must be 'file', 'url', or 'text'")

    return upload


@router.get(
    "/api/deals/{deal_id}/sections/{section_id}/uploads",
    response_model=list[UploadResponse],
    dependencies=[Depends(require_deal_owner)],
)
def list_uploads(deal_id: Annotated[str, InputPath(min_length=1, max_length=128)], section_id: Annotated[str, InputPath(min_length=1, max_length=128)], db: Session = Depends(get_db)):
    """List all uploads for a section."""
    section = db.query(Section).filter(
        Section.id == section_id,
        Section.deal_id == deal_id,
    ).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section.uploads


@router.delete("/api/uploads/{upload_id}", status_code=204)
def delete_upload(
    upload_id: Annotated[str, InputPath(min_length=1, max_length=128)],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an upload and its vector store entries."""
    query = (
        db.query(Upload)
        .join(Section, Upload.section_id == Section.id)
        .join(Deal, Section.deal_id == Deal.id)
        .filter(Upload.id == upload_id)
    )
    if current_user.role == "relationship_manager":
        query = query.filter(Deal.owner_user_id == current_user.id)
    elif current_user.role != "credit_analyst":
        raise HTTPException(status_code=403, detail="Your role cannot access uploads.")
    owned_upload = query.first()
    if not owned_upload or not IngestionService.delete_upload(db, upload_id):
        raise HTTPException(status_code=404, detail="Upload not found")
