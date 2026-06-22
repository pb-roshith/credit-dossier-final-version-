"""
Versions API router — submit and approve versions.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.deal import VersionCreate, VersionResponse
from app.services.deal_service import DealService

router = APIRouter(prefix="/api/deals/{deal_id}/versions", tags=["versions"])


@router.post("", response_model=VersionResponse, status_code=201)
def submit_version(deal_id: str, data: VersionCreate, db: Session = Depends(get_db)):
    """Submit current draft as a frozen version for review."""
    version = DealService.create_version(db, deal_id, data.notes)
    if not version:
        raise HTTPException(status_code=404, detail="Deal not found")
    return version


@router.patch("/{version_id}/approve", response_model=VersionResponse)
def approve_version(
    deal_id: str,
    version_id: str,
    db: Session = Depends(get_db),
):
    """Approve a submitted version. Changes deal status to Approved."""
    version = DealService.approve_version(db, deal_id, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version
