"""
Uploads API router — file, URL, and text upload for section grounding.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.upload import UploadResponse
from app.services.ingestion_service import IngestionService
from app.services.deal_service import DealService

router = APIRouter(tags=["uploads"])


@router.post(
    "/api/deals/{deal_id}/sections/{section_id}/uploads",
    response_model=UploadResponse,
    status_code=201,
)
async def create_upload(
    deal_id: str,
    section_id: str,
    source_type: str = Form(..., description="file, url, or text"),
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    text_content: str | None = Form(None),
    note: str | None = Form(None),
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
    section = DealService.get_section(db, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    if source_type == "file":
        if not file:
            raise HTTPException(status_code=400, detail="File is required for source_type='file'")
        file_bytes = await file.read()
        upload = await IngestionService.process_file_upload(
            db, section_id, deal_id, file_bytes, file.filename or "uploaded_file", note
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
)
def list_uploads(deal_id: str, section_id: str, db: Session = Depends(get_db)):
    """List all uploads for a section."""
    section = DealService.get_section(db, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section.uploads


@router.delete("/api/uploads/{upload_id}", status_code=204)
def delete_upload(upload_id: str, db: Session = Depends(get_db)):
    """Delete an upload and its vector store entries."""
    if not IngestionService.delete_upload(db, upload_id):
        raise HTTPException(status_code=404, detail="Upload not found")
