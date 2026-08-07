"""
Deals API router — CRUD operations for deals.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
import pypdf
import io

from app.database import get_db
from app.agents.theme_agent import extract_theme_from_document_bytes
from app.schemas.deal import (
    DealCreate, DealUpdate, DealResponse, DealListResponse,
)
from app.services.deal_service import DealService
from app.services.mistral_library_service import MistralLibraryService
from app.services.mcp_service import MCPClientService
from app.services.library_sync_service import LibrarySyncService
from app.auth import get_current_user, require_deal_owner, require_relationship_manager
from app.models.user import User
import httpx
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/deals", tags=["deals"])


@router.get("", response_model=list[DealListResponse])
def list_deals(
    status: str | None = Query(None, description="Filter by status"),
    search: str | None = Query(None, description="Search by customer name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all deals with optional status and search filters."""
    deals = DealService.list_deals(db, current_user, status=status, search=search)
    result = []
    for deal in deals:
        mandatory = [s for s in deal.sections if not s.optional]
        ready = sum(1 for s in mandatory if s.state == "ready")
        result.append(DealListResponse(
            id=deal.id,
            customer=deal.customer,
            customer_type=deal.customer_type,
            industry=deal.industry,
            segment=deal.segment,
            geography=deal.geography,
            city=deal.city,
            sector=deal.sector,
            kyc=deal.kyc,
            facility=deal.facility,
            currency=deal.currency,
            amount=deal.amount,
            tenure=deal.tenure,
            pricing=deal.pricing,
            repayment=deal.repayment,
            collateral=deal.collateral,
            due=deal.due,
            owner=deal.owner,
            status=deal.status,
            created_at=deal.created_at,
            updated_at=deal.updated_at,
            sections_ready=ready,
            sections_total=len(mandatory),
            versions_count=len(deal.versions),
        ))
    return result


@router.get("/{deal_id}", response_model=DealResponse, dependencies=[Depends(require_deal_owner)])
def get_deal(deal_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Get a single deal with all sections, audit entries, and versions."""
    deal = DealService.get_deal(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    # Resolve a new deal once. Subsequent refreshes are explicit, preventing
    # frontend polling from continuously restarting the same remote operation.
    if deal.library_sync_status == "not_started":
        background_tasks.add_task(LibrarySyncService.check_for_new_documents, deal.id)
        
    return deal


@router.post("/{deal_id}/library/sync", status_code=202, dependencies=[Depends(require_deal_owner)])
def sync_mcp_documents(deal_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Refresh direct references to the company's Mistral Library."""
    deal = DealService.get_deal(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    
    background_tasks.add_task(LibrarySyncService.sync_mcp_documents, deal.id)
    return {"message": "Company library refresh started", "status": "syncing"}

@router.get("/{deal_id}/library/sync-status", dependencies=[Depends(require_deal_owner)])
def get_library_sync_status(deal_id: str, db: Session = Depends(get_db)):
    """Get the current sync status and timeline of logs."""
    deal = DealService.get_deal(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    
    logs = [
        {
            "id": log.id,
            "doc_title": log.doc_title,
            "doc_url": log.doc_url,
            "status": log.status,
            "error": log.error,
            "file_size": log.file_size,
            "created_at": log.created_at,
            "started_at": log.started_at,
            "completed_at": log.completed_at
        }
        for log in sorted(deal.sync_logs, key=lambda x: x.created_at)
    ]
    
    return {
        "library_sync_status": deal.library_sync_status,
        "logs": logs
    }


@router.post("", response_model=DealResponse, status_code=201)
def create_deal(data: DealCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(require_relationship_manager)):
    """Create a new deal with 16 default sections."""
    deal = DealService.create_deal(db, data.model_dump(), current_user.id)
    
    background_tasks.add_task(LibrarySyncService.sync_mcp_documents, deal.id)
    
    # Re-fetch with full relations
    full_deal = DealService.get_deal(db, deal.id)
    return full_deal


@router.patch("/{deal_id}", response_model=DealResponse, dependencies=[Depends(require_deal_owner)])
def update_deal(deal_id: str, data: DealUpdate, db: Session = Depends(get_db)):
    """Update deal metadata."""
    deal = DealService.update_deal(db, deal_id, data.model_dump(exclude_unset=True))
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    full_deal = DealService.get_deal(db, deal.id)
    return full_deal


@router.post("/{deal_id}/theme/extract", response_model=DealResponse, dependencies=[Depends(require_deal_owner)])
async def extract_theme_from_document(deal_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a document (like an Annual Report) to extract and apply the brand theme."""
    deal = DealService.get_deal(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    try:
        content = await file.read()
        text = ""
        if file.filename and file.filename.lower().endswith(".pdf"):
            reader = pypdf.PdfReader(io.BytesIO(content))
            for page in reader.pages[:10]:  # Read first 10 pages for theme
                text += page.extract_text() + "\n"
        else:
            text = content.decode("utf-8", errors="ignore")
            
        theme_resp = extract_theme_from_document_bytes(content, file.filename or "doc.pdf")
        if theme_resp:
            import json
            deal = DealService.update_deal(
                db, 
                deal_id, 
                {
                    "primary_color": theme_resp.primary_color,
                    "secondary_color": theme_resp.secondary_color,
                    "theme_palette": json.dumps(theme_resp.theme_palette)
                }
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to extract theme colors")
            
        full_deal = DealService.get_deal(db, deal.id)
        return full_deal
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{deal_id}", status_code=204, dependencies=[Depends(require_deal_owner)])
def delete_deal(deal_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Delete a deal and all related data, including the Mistral library."""
    deal = DealService.get_deal(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    library_id = deal.mistral_library_id
    
    if not DealService.delete_deal(db, deal_id):
        raise HTTPException(status_code=404, detail="Deal not found")
        
    if library_id:
        background_tasks.add_task(MistralLibraryService.delete_library, library_id)
