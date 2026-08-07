"""
Versions API router — submit and approve versions.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import (
    require_credit_analyst,
    require_deal_owner,
    require_relationship_manager,
)
from app.models.user import User
from app.schemas.deal import VersionCreate, VersionResponse, VersionReviewRequest
from app.services.deal_service import DealService

router = APIRouter(prefix="/api/deals/{deal_id}/versions", tags=["versions"], dependencies=[Depends(require_deal_owner)])


@router.post("", response_model=VersionResponse, status_code=201)
def submit_version(
    deal_id: str,
    data: VersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_relationship_manager),
):
    """Submit current draft as a frozen version for review."""
    version = DealService.create_version(db, deal_id, data.notes, current_user.user_id)
    if not version:
        raise HTTPException(status_code=404, detail="Deal not found")
    return version


@router.patch("/{version_id}/approve", response_model=VersionResponse)
def approve_version(
    deal_id: str,
    version_id: str,
    data: VersionReviewRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_credit_analyst),
):
    """Approve a submitted version. Changes deal status to Approved."""
    version = DealService.approve_version(
        db,
        deal_id,
        version_id,
        current_user.user_id,
        data.comments if data else "",
    )
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


@router.patch("/{version_id}/deny", response_model=VersionResponse)
def deny_version(
    deal_id: str,
    version_id: str,
    data: VersionReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_credit_analyst),
):
    """Deny a submitted version and return review comments to the RM."""
    comments = data.comments.strip()
    if not comments:
        raise HTTPException(
            status_code=400,
            detail="Review comments are required when denying a version.",
        )
    version = DealService.deny_version(
        db, deal_id, version_id, current_user.user_id, comments
    )
    if not version:
        raise HTTPException(
            status_code=404,
            detail="Submitted version not found.",
        )
    return version
